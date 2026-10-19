"""Re-analyse and replace: the AI overwrites its own earlier tags, never a person's edits."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.ai_service import ClothingTags
from app.workers import tagging
from app.workers.tagging import _ai_may_set

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

EARLIER_GUESS = {
    "type": "t-shirt",
    "subtype": "crew",
    "primary_color": "white",
    "colors": ["white"],
    "pattern": "solid",
    "material": "cotton",
    "formality": "casual",
    "style": ["casual"],
    "season": ["summer"],
}

NEW_ANSWER = {
    "type": "shirt",
    "subtype": "oxford",
    "primary_color": "blue",
    "colors": ["blue", "white"],
    "pattern": "striped",
    "material": "linen",
    "formality": "smart-casual",
    "style": ["preppy"],
    "season": ["spring", "fall"],
    "fit": "slim",
}


async def _make_item(db_session: AsyncSession, test_user, image_path, **overrides) -> ClothingItem:
    columns = {**EARLIER_GUESS}
    tags = {k: v for k, v in EARLIER_GUESS.items() if k not in ("type", "subtype")}
    tags.update(overrides.pop("tags", {}))
    status = overrides.pop("status", ItemStatus.ready)
    columns.update(overrides)
    item = ClothingItem(
        user_id=test_user.id,
        image_path=str(image_path),
        status=status,
        tags=tags,
        **columns,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


class _StubAI:
    returns: ClothingTags = None

    def __init__(self, *args, **kwargs):
        pass

    async def analyze_image(self, path, *, locale):
        return type(self).returns


@pytest.fixture
def stub_ai(monkeypatch):
    def _install(**overrides):
        _StubAI.returns = ClothingTags(
            **{**NEW_ANSWER, "confidence": 0.9, "description": "A fresh description."},
            **overrides,
        )
        monkeypatch.setattr(tagging, "AIService", _StubAI)
        monkeypatch.setattr(tagging, "_tagging_call_budget", lambda _svc: 30)

    return _install


@pytest.fixture
def item_image(tmp_path):
    path = tmp_path / "item.jpg"
    Image.new("RGB", (64, 64), "black").save(path)
    return path


async def _analyse(db_session, item, image, *, replace: bool):
    with (
        patch("app.workers.tagging.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
    ):
        await tagging.tag_item_image({}, str(item.id), str(image), replace=replace)
    await db_session.refresh(item)
    return item


# --------------------------------------------------------------------------
# the decision
# --------------------------------------------------------------------------

NOBODY = frozenset()


class TestAiMaySet:
    @pytest.mark.parametrize(
        ("field", "current", "expected"),
        [
            ("pattern", None, True),
            ("pattern", "", True),
            ("style", [], True),
            ("pattern", "solid", False),
            ("style", ["casual"], False),
            ("type", "unknown", True),
            ("type", "shirt", False),
            ("primary_color", "unknown", True),
            ("primary_color", "navy", False),
            ("subtype", None, True),
            ("subtype", "oxford", False),
        ],
    )
    def test_a_normal_analysis_only_fills_what_is_empty(self, field, current, expected):
        assert _ai_may_set(field, current, "x", replace=False, kept=NOBODY) is expected

    @pytest.mark.parametrize(
        ("field", "current"),
        [("pattern", "solid"), ("style", ["casual"]), ("type", "shirt"), ("fit", "slim")],
    )
    def test_replacing_overwrites_the_earlier_answer(self, field, current):
        assert _ai_may_set(field, current, "x", replace=True, kept=NOBODY) is True

    def test_replacing_never_overwrites_an_edited_key(self):
        kept = frozenset({"pattern"})
        assert _ai_may_set("pattern", "solid", "striped", replace=True, kept=kept) is False
        assert _ai_may_set("fit", "slim", "relaxed", replace=True, kept=kept) is True

    @pytest.mark.parametrize("empty", [None, "", [], {}, "unknown"])
    def test_replacing_never_erases_with_nothing(self, empty):
        assert _ai_may_set("material", "cotton", empty, replace=True, kept=NOBODY) is False


# --------------------------------------------------------------------------
# the worker
# --------------------------------------------------------------------------


class TestReplaceInTheWorker:
    @pytest.mark.asyncio
    async def test_replaces_every_earlier_guess(self, db_session, test_user, stub_ai, item_image):
        item = await _make_item(db_session, test_user, item_image)
        stub_ai()

        await _analyse(db_session, item, item_image, replace=True)

        assert (item.type, item.subtype) == ("shirt", "oxford")
        assert item.primary_color == "blue"
        assert item.colors == ["blue", "white"]
        assert item.pattern == "striped"
        assert item.material == "linen"
        assert item.formality == "smart-casual"
        assert item.style == ["preppy"]
        assert item.season == ["spring", "fall"]
        assert item.tags["pattern"] == "striped"
        assert item.tags["fit"] == "slim"
        assert item.tags["colors"] == ["blue", "white"]

    @pytest.mark.asyncio
    async def test_a_normal_analysis_still_keeps_everything_that_is_set(
        self, db_session, test_user, stub_ai, item_image
    ):
        item = await _make_item(db_session, test_user, item_image)
        stub_ai()

        await _analyse(db_session, item, item_image, replace=False)

        assert (item.type, item.subtype) == ("t-shirt", "crew")
        assert item.pattern == "solid"
        assert item.primary_color == "white"
        assert item.tags["pattern"] == "solid"
        assert item.tags["fit"] == "slim", "an empty key is still filled"

    @pytest.mark.asyncio
    async def test_keeps_what_a_person_edited(self, db_session, test_user, stub_ai, item_image):
        item = await _make_item(
            db_session,
            test_user,
            item_image,
            type="polo",
            subtype="piqué",
            pattern="plaid",
            tags={
                "pattern": "plaid",
                "fit": "relaxed",
                "user_edited_keys": ["type", "subtype", "pattern", "fit"],
            },
        )
        stub_ai()

        await _analyse(db_session, item, item_image, replace=True)

        assert (item.type, item.subtype, item.pattern) == ("polo", "piqué", "plaid")
        assert item.tags["pattern"] == "plaid"
        assert item.tags["fit"] == "relaxed"
        # ...while the keys nobody edited were replaced
        assert item.material == "linen"
        assert item.style == ["preppy"]

    @pytest.mark.asyncio
    async def test_the_edit_list_and_user_owned_keys_survive(
        self, db_session, test_user, stub_ai, item_image
    ):
        item = await _make_item(
            db_session,
            test_user,
            item_image,
            tags={
                "size": "M",
                "care_instructions": "Wash cold",
                "source_url": "https://example.invalid/p/1",
                "user_edited_keys": ["fit"],
            },
        )
        stub_ai()

        await _analyse(db_session, item, item_image, replace=True)

        assert item.tags["size"] == "M"
        assert item.tags["care_instructions"] == "Wash cold"
        assert item.tags["source_url"] == "https://example.invalid/p/1"
        assert item.tags["user_edited_keys"] == ["fit"]

    @pytest.mark.asyncio
    async def test_an_empty_or_unknown_answer_does_not_erase(
        self, db_session, test_user, stub_ai, item_image
    ):
        item = await _make_item(db_session, test_user, item_image)
        stub_ai()
        _StubAI.returns = ClothingTags(
            type="unknown",
            primary_color="unknown",
            material=None,
            pattern=None,
            colors=[],
            style=[],
            season=[],
            confidence=0.1,
            description="Unclear.",
        )

        await _analyse(db_session, item, item_image, replace=True)

        assert item.type == "t-shirt"
        assert item.primary_color == "white"
        assert item.material == "cotton"
        assert item.pattern == "solid"
        assert item.colors == ["white"]
        assert item.style == ["casual"]
        assert item.tags["material"] == "cotton"

    @pytest.mark.asyncio
    async def test_a_chosen_primary_colour_stays_in_the_new_colour_list(
        self, db_session, test_user, stub_ai, item_image
    ):
        item = await _make_item(
            db_session,
            test_user,
            item_image,
            primary_color="navy",
            colors=["navy"],
            tags={"primary_color": "navy", "user_edited_keys": ["primary_color"]},
        )
        stub_ai()

        await _analyse(db_session, item, item_image, replace=True)

        assert item.primary_color == "navy"
        assert item.colors == ["navy", "blue", "white"]
        assert item.tags["primary_color"] == "navy"

    @pytest.mark.asyncio
    async def test_columns_and_tags_agree_afterwards(
        self, db_session, test_user, stub_ai, item_image
    ):
        item = await _make_item(
            db_session,
            test_user,
            item_image,
            tags={"pattern": "solid", "user_edited_keys": ["pattern"]},
        )
        stub_ai()

        await _analyse(db_session, item, item_image, replace=True)

        for key in ("pattern", "material", "formality", "style", "season"):
            assert item.tags[key] == getattr(item, key), key

    @pytest.mark.asyncio
    @pytest.mark.parametrize("replace", [False, True])
    async def test_the_description_and_confidence_always_refresh(
        self, db_session, test_user, stub_ai, item_image, replace
    ):
        item = await _make_item(db_session, test_user, item_image)
        stub_ai()

        await _analyse(db_session, item, item_image, replace=replace)

        assert item.ai_description == "A fresh description."
        assert item.status == ItemStatus.ready

    @pytest.mark.asyncio
    async def test_an_item_never_edited_before_the_feature_is_fully_replaced(
        self, db_session, test_user, stub_ai, item_image
    ):
        # No user_edited_keys at all (edited before they were recorded): nothing is protected.
        item = await _make_item(db_session, test_user, item_image, pattern="plaid")
        assert "user_edited_keys" not in item.tags
        stub_ai()

        await _analyse(db_session, item, item_image, replace=True)

        assert item.pattern == "striped"


# --------------------------------------------------------------------------
# the endpoint
# --------------------------------------------------------------------------


def _queue():
    redis = AsyncMock()
    job = MagicMock()
    job.job_id = "job-1"
    redis.enqueue_job.return_value = job
    return redis


class TestAnalyzeEndpoint:
    @pytest.mark.asyncio
    async def test_replace_is_passed_to_the_job(
        self, client: AsyncClient, test_user, auth_headers, db_session, item_image
    ):
        item = await _make_item(db_session, test_user, item_image)
        redis = _queue()

        with patch("app.api.items.create_pool", new_callable=AsyncMock, return_value=redis):
            response = await client.post(
                f"/api/v1/items/{item.id}/analyze?replace=true", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        _, kwargs = redis.enqueue_job.call_args
        assert kwargs["replace"] is True

    @pytest.mark.asyncio
    async def test_a_plain_analysis_enqueues_exactly_what_it_always_did(
        self, client: AsyncClient, test_user, auth_headers, db_session, item_image
    ):
        item = await _make_item(db_session, test_user, item_image)
        redis = _queue()

        with patch("app.api.items.create_pool", new_callable=AsyncMock, return_value=redis):
            response = await client.post(f"/api/v1/items/{item.id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        args, kwargs = redis.enqueue_job.call_args
        assert args[0] == "tag_item_image"
        assert "replace" not in kwargs

    @pytest.mark.asyncio
    async def test_replace_also_works_when_retrying_a_failed_item(
        self, client: AsyncClient, test_user, auth_headers, db_session, item_image
    ):
        item = await _make_item(
            db_session,
            test_user,
            item_image,
            status=ItemStatus.error,
            ai_failed_at=datetime.now(UTC) - timedelta(hours=1),
        )
        redis = _queue()

        with patch("app.api.items.create_pool", new_callable=AsyncMock, return_value=redis):
            response = await client.post(
                f"/api/v1/items/{item.id}/analyze?replace=true", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        _, kwargs = redis.enqueue_job.call_args
        assert kwargs["replace"] is True

    @pytest.mark.asyncio
    async def test_replace_must_be_a_boolean(
        self, client: AsyncClient, test_user, auth_headers, db_session, item_image
    ):
        item = await _make_item(db_session, test_user, item_image)

        response = await client.post(
            f"/api/v1/items/{item.id}/analyze?replace=maybe", headers=auth_headers
        )

        assert response.status_code == 422
