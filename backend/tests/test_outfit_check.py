import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.ai_service import AIDisabledError
from app.services.outfit_check_service import (
    ALTERNATIVE_OFFSET,
    OutfitCheckError,
    parse_check,
)

URL = "/api/v1/outfits/check"


def _item(user: User | None = None, type_: str = "shirt", **fields) -> ClothingItem:
    return ClothingItem(
        id=uuid4(),
        user_id=user.id if user else uuid4(),
        type=type_,
        image_path=f"test/{uuid4()}.jpg",
        status=ItemStatus.ready,
        **fields,
    )


class TestParseCheck:
    def setup_method(self):
        self.shirt, self.jeans = _item(name="Shirt"), _item(type_="jeans", name="Jeans")
        self.chinos = _item(type_="pants", name="Chinos")
        self.outfit = {1: self.shirt, 2: self.jeans}
        self.alternatives = {ALTERNATIVE_OFFSET: self.chinos}

    def parse(self, answer: object):
        content = answer if isinstance(answer, str) else json.dumps(answer)
        return parse_check(content, self.outfit, self.alternatives)

    def test_reads_a_full_answer(self):
        check = self.parse(
            {
                "rating": 7,
                "verdict": "Good base",
                "opinion": "Works for a casual dinner.",
                "strengths": ["Clean colors"],
                "improvements": ["Jeans are a bit heavy"],
                "suggestions": [
                    {
                        "action": "replace",
                        "title": "Lighter trousers",
                        "target_item_num": 2,
                        "replacement_item_num": ALTERNATIVE_OFFSET,
                        "description": "Swap the jeans for the chinos.",
                        "reason": "Lighter for the evening heat.",
                    }
                ],
            }
        )
        assert (check.rating, check.verdict) == (7, "Good base")
        assert check.strengths == ["Clean colors"]
        [swap] = check.suggestions
        assert swap.action == "replace"
        assert swap.target is self.jeans
        assert swap.replacement is self.chinos

    @pytest.mark.parametrize(
        ("rating", "expected"),
        [("8/10", 8), (8.6, 9), ("12", 10), (0, 1), ("great", 5), (None, 5), (True, 5)],
    )
    def test_rating_is_read_leniently_and_clamped(self, rating, expected):
        assert self.parse({"rating": rating}).rating == expected

    def test_reads_json_inside_prose_and_code_fences(self):
        check = self.parse('Here you go:\n```json\n{"rating": 9, "verdict": "Sharp"}\n```')
        assert (check.rating, check.verdict) == (9, "Sharp")

    def test_unreadable_answer_raises_a_coded_error(self):
        with pytest.raises(OutfitCheckError) as raised:
            self.parse("I love this outfit!")
        assert raised.value.code == "AI_RESPONSE_UNUSABLE"

    def test_suggestions_that_cannot_be_applied_become_styling_tips(self):
        check = self.parse(
            {
                "suggestions": [
                    # An outfit number is not a wardrobe alternative.
                    {
                        "action": "replace",
                        "title": "a",
                        "target_item_num": 1,
                        "replacement_item_num": 2,
                    },
                    {"action": "add", "title": "b", "replacement_item_num": 999},
                    {"action": "remove", "title": "c", "target_item_num": ALTERNATIVE_OFFSET},
                    {"action": "teleport", "title": "d"},
                ]
            }
        )
        assert [s.action for s in check.suggestions] == ["styling_tip"] * 4
        assert all(s.target is None and s.replacement is None for s in check.suggestions)

    def test_item_numbers_echoed_as_labels_still_resolve(self):
        check = self.parse(
            {
                "suggestions": [
                    {"action": "remove", "title": "Drop it", "target_item_num": "[1]"},
                    {
                        "action": "add",
                        "title": "Add",
                        "replacement_item_num": f"{ALTERNATIVE_OFFSET}",
                    },
                ]
            }
        )
        remove, add = check.suggestions
        assert (remove.action, remove.target) == ("remove", self.shirt)
        assert (add.action, add.target, add.replacement) == ("add", None, self.chinos)

    def test_skips_malformed_entries_and_caps_lengths(self):
        check = self.parse(
            {
                "opinion": "x" * 10_000,
                "strengths": "not a list",
                "improvements": ["", "  ", "ok", 3],
                "suggestions": ["nope", {}, {"title": "Tuck in"}],
            }
        )
        assert len(check.opinion) == 3000
        assert check.strengths == []
        assert check.improvements == ["ok"]
        assert [s.title for s in check.suggestions] == ["Tuck in"]


def _answer(**overrides) -> str:
    answer = {
        "rating": 6,
        "verdict": "Too casual",
        "opinion": "Fine, but the venue is dressier.",
        "strengths": ["Good fit"],
        "improvements": ["Needs a sharper top"],
        "suggestions": [],
    }
    return json.dumps({**answer, **overrides})


async def _add(db: AsyncSession, *items: ClothingItem) -> list[ClothingItem]:
    db.add_all(items)
    await db.commit()
    return list(items)


class TestCheckEndpoint:
    @pytest.mark.asyncio
    async def test_reviews_the_outfit_and_links_suggested_items(
        self, client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession
    ):
        test_user.locale = "fr"
        tee, jeans, shirt, washing, archived = await _add(
            db_session,
            _item(test_user, "t-shirt", name="Grey tee"),
            _item(test_user, "jeans", name="Blue jeans"),
            _item(test_user, "shirt", name="Oxford shirt", thumbnail_path="thumbs/oxford.jpg"),
            _item(test_user, "shirt", name="In the wash", needs_wash=True),
            _item(test_user, "shirt", name="Archived", is_archived=True),
        )
        ai = AsyncMock()

        async def generate_text(prompt: str, system_prompt: str) -> str:
            number = next(
                line.split("]")[0].strip("[")
                for line in prompt.splitlines()
                if "Oxford shirt" in line
            )
            return _answer(
                suggestions=[
                    {
                        "action": "replace",
                        "title": "Sharper top",
                        "target_item_num": 1,
                        "replacement_item_num": int(number),
                        "description": "Wear the oxford instead.",
                        "reason": "The rooftop has a smart dress code.",
                    }
                ]
            )

        ai.generate_text.side_effect = generate_text
        with patch("app.services.outfit_check_service.AIService", return_value=ai):
            response = await client.post(
                URL,
                json={
                    "items": [str(tee.id), str(jeans.id)],
                    "destination": "  Rooftop dinner  ",
                    "occasion": "date",
                },
                headers=auth_headers,
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rating"] == 6
        [suggestion] = body["suggestions"]
        assert suggestion["action"] == "replace"
        assert suggestion["target_item_id"] == str(tee.id)
        assert suggestion["replacement_item"]["id"] == str(shirt.id)
        assert "thumbs/oxford.jpg" in suggestion["replacement_item"]["thumbnail_url"]

        prompt = ai.generate_text.call_args.kwargs["prompt"]
        assert "Rooftop dinner\n" in prompt
        assert "OCCASION: date" in prompt
        assert "Write every text field in French." in prompt
        assert '[1] "Grey tee"' in prompt
        for unavailable in ("In the wash", "Archived"):
            assert unavailable not in prompt

    @pytest.mark.asyncio
    async def test_rejects_items_the_user_does_not_own(
        self, client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession
    ):
        uid = uuid4()
        stranger = User(
            id=uid, external_id=f"x-{uid}", email=f"{uid}@example.com", display_name="Stranger"
        )
        db_session.add(stranger)
        await db_session.commit()
        [theirs] = await _add(db_session, _item(stranger))

        with patch("app.services.outfit_check_service.AIService") as ai:
            response = await client.post(
                URL,
                json={"items": [str(theirs.id)], "destination": "Office", "occasion": "office"},
                headers=auth_headers,
            )

        assert response.status_code == 403
        assert response.json()["error_code"] == "OUTFIT_ITEM_OWNERSHIP"
        ai.assert_not_called()

    @pytest.mark.asyncio
    async def test_reports_disabled_ai_with_its_own_code(
        self, client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession
    ):
        [tee] = await _add(db_session, _item(test_user, "t-shirt"))
        with patch(
            "app.services.outfit_check_service.require_internal_ai",
            side_effect=AIDisabledError("off"),
        ):
            response = await client.post(
                URL,
                json={"items": [str(tee.id)], "destination": "Park", "occasion": "casual"},
                headers=auth_headers,
            )

        assert response.status_code == 503
        assert response.json()["error_code"] == "AI_STYLIST_DISABLED"

    @pytest.mark.asyncio
    async def test_an_unreadable_answer_is_a_coded_503(
        self, client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession
    ):
        [tee] = await _add(db_session, _item(test_user, "t-shirt"))
        ai = AsyncMock()
        ai.generate_text.return_value = "Looks great to me!"
        with patch("app.services.outfit_check_service.AIService", return_value=ai):
            response = await client.post(
                URL,
                json={"items": [str(tee.id)], "destination": "Park", "occasion": "casual"},
                headers=auth_headers,
            )

        assert response.status_code == 503
        assert response.json()["error_code"] == "AI_RESPONSE_UNUSABLE"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [
            {"items": [], "destination": "Park", "occasion": "casual"},
            {"items": ["{id}"], "destination": " ", "occasion": "casual"},
            {"items": ["{id}"], "destination": "Park", "occasion": "moon-landing"},
        ],
    )
    async def test_validates_the_request(
        self, client: AsyncClient, test_user: User, auth_headers, db_session: AsyncSession, payload
    ):
        [tee] = await _add(db_session, _item(test_user, "t-shirt"))
        payload = {**payload, "items": [i.format(id=tee.id) for i in payload["items"]]}
        response = await client.post(URL, json=payload, headers=auth_headers)
        assert response.status_code == 422
