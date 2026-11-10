import json
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.selfie_service import parse_matches


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (400, 600), (90, 90, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


class TestParseMatches:
    def test_reads_json_and_ignores_numbers_outside_the_list(self):
        assert parse_matches('Sure! {"matches": [2, 9, 2, 1]}', 3) == [1, 0]

    def test_falls_back_to_a_bare_list_of_numbers(self):
        assert parse_matches("3, 1", 3) == [2, 0]
        assert parse_matches("matches: [3, 1]", 3) == [2, 0]

    def test_numbers_in_prose_are_not_matches(self):
        assert parse_matches("It is 2 pm and I see 1 shirt", 3) == []

    def test_empty_answer(self):
        assert parse_matches('{"matches": []}', 5) == []

    def test_an_empty_json_answer_is_final(self):
        assert parse_matches('Item 2 looks close, but {"matches": []}', 5) == []

    @pytest.mark.parametrize(
        "answer",
        ['{"matches": 3}', '{"matches": [true, 1.5, "x", null]}', '{"matches": {"a": 1}}'],
    )
    def test_malformed_matches_are_ignored(self, answer):
        assert parse_matches(answer, 5) == []

    def test_numeric_strings_still_count(self):
        assert parse_matches('{"matches": ["2", 3]}', 5) == [1, 2]


class TestSelfieApi:
    @pytest.mark.asyncio
    async def test_returns_the_recognised_items(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        items = [
            ClothingItem(
                user_id=test_user.id,
                type=item_type,
                primary_color=color,
                image_path=f"{item_type}.jpg",
                status=ItemStatus.ready,
            )
            for item_type, color in (("jeans", "blue"), ("t-shirt", "white"), ("coat", "black"))
        ]
        db_session.add_all(items)
        await db_session.commit()

        async def fake_call(self, messages, task_name, **kwargs):
            # The photo itself must reach the model, next to the listing.
            image_part = messages[1]["content"][1]
            assert image_part["type"] == "image_url"
            assert image_part["image_url"]["url"] == "data:image/jpeg;base64,aGk="
            listing = messages[1]["content"][0]["text"]
            wanted = [line.split(".")[0] for line in listing.splitlines()[1:] if "coat" not in line]
            return json.dumps({"matches": [int(n) for n in wanted]}), None, None

        with (
            patch("app.services.ai_service.AIService._call_with_fallback", fake_call),
            patch("app.services.ai_service.AIService._preprocess_image", return_value="aGk="),
        ):
            response = await client.post(
                "/api/v1/selfie",
                files={"image": ("me.jpg", _jpeg(), "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["considered"] == 3
        assert sorted(i["type"] for i in data["matches"]) == ["jeans", "t-shirt"]

    @pytest.mark.asyncio
    async def test_ai_failure_is_a_clear_error(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        db_session.add(
            ClothingItem(
                user_id=test_user.id, type="jeans", image_path="j.jpg", status=ItemStatus.ready
            )
        )
        await db_session.commit()
        with (
            patch(
                "app.services.ai_service.AIService._call_with_fallback",
                AsyncMock(return_value=(None, RuntimeError("down"), None)),
            ),
            patch("app.services.ai_service.AIService._preprocess_image", return_value="aGk="),
        ):
            response = await client.post(
                "/api/v1/selfie",
                files={"image": ("me.jpg", _jpeg(), "image/jpeg")},
                headers=auth_headers,
            )
        assert response.status_code == 502
        assert (
            response.json()["detail"] == "The AI could not read the photo. Try again in a moment."
        )

    @pytest.mark.asyncio
    async def test_no_photo_is_sent_while_vision_is_off(
        self, client: AsyncClient, test_user, auth_headers
    ):
        call = AsyncMock()
        with (
            patch("app.api.selfie.get_settings") as settings,
            patch("app.services.ai_service.AIService._call_with_fallback", call),
        ):
            settings.return_value.effective_ai_vision_enabled = False
            response = await client.post(
                "/api/v1/selfie",
                files={"image": ("me.jpg", _jpeg(), "image/jpeg")},
                headers=auth_headers,
            )
        assert response.status_code == 503
        call.assert_not_called()

    @pytest.mark.asyncio
    async def test_photos_over_the_pixel_ceiling_are_refused(
        self, client: AsyncClient, test_user, auth_headers
    ):
        call = AsyncMock()
        with (
            patch("app.api.selfie.get_settings") as settings,
            patch("app.services.ai_service.AIService._call_with_fallback", call),
        ):
            settings.return_value.effective_ai_vision_enabled = True
            settings.return_value.max_upload_size_mb = 10
            settings.return_value.max_image_megapixels = 0.1
            response = await client.post(
                "/api/v1/selfie",
                files={"image": ("me.jpg", _jpeg(), "image/jpeg")},
                headers=auth_headers,
            )
        assert response.status_code == 413
        call.assert_not_called()

    @pytest.mark.asyncio
    async def test_considered_counts_only_what_the_model_saw(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        db_session.add_all(
            ClothingItem(
                user_id=test_user.id, type="t-shirt", image_path=f"{n}.jpg", status=ItemStatus.ready
            )
            for n in range(4)
        )
        await db_session.commit()
        with (
            patch("app.services.selfie_service.MAX_CANDIDATES", 2),
            patch(
                "app.services.ai_service.AIService._call_with_fallback",
                AsyncMock(return_value=('{"matches": []}', None, None)),
            ),
            patch("app.services.ai_service.AIService._preprocess_image", return_value="aGk="),
        ):
            response = await client.post(
                "/api/v1/selfie",
                files={"image": ("me.jpg", _jpeg(), "image/jpeg")},
                headers=auth_headers,
            )
        assert response.status_code == 200, response.json()
        assert response.json()["considered"] == 2
