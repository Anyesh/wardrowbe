"""Tests for tag-preservation across updates and AI re-analysis.

Covers three related fixes:

1. ``ItemTags`` carries user-owned keys (size, care_instructions, source_url)
   that the AI never emits.
2. ``ItemService.update`` merges the tags JSONB instead of replacing it, and
   the column mirror follows what the caller actually sent, so clearing a tag
   also clears its column.
3. ``tagging.tag_item_image`` merges rather than replaces, drops empty AI
   values so a null cannot erase a real one, and re-syncs mirrored columns
   into the JSONB so the two cannot disagree.

Split these classes into test_items.py (1 and 2) and test_tagging_worker.py
(3) if you'd rather not add a file.
"""

from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.schemas.item import ItemTags, ItemUpdate
from app.services.ai_service import ClothingTags
from app.services.item_service import ItemService
from app.workers import tagging

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


async def _make_item(db_session: AsyncSession, test_user, **kwargs) -> ClothingItem:
    item = ClothingItem(
        user_id=test_user.id,
        type=kwargs.pop("type", "sweater"),
        image_path=kwargs.pop("image_path", "test/image.jpg"),
        status=kwargs.pop("status", ItemStatus.ready),
        tags=kwargs.pop("tags", {}),
        **kwargs,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


def _ai_tags(**overrides) -> ClothingTags:
    """A ClothingTags the stub AI returns. Trim fields if the model differs."""
    base = {
        "type": "sweater",
        "subtype": "turtleneck",
        "primary_color": "black",
        "colors": ["black"],
        "pattern": "solid",
        # the AI often cannot tell fibre content from a photo
        "material": None,
        "style": ["classic"],
        "season": ["all-season"],
        "formality": "casual",
        "fit": None,
        "confidence": 0.9,
        "description": "A black turtleneck sweater.",
    }
    base.update(overrides)
    return ClothingTags(**base)


class _StubAI:
    """Stands in for AIService; returns fixed tags without calling a model."""

    returns: ClothingTags = None  # set per test

    def __init__(self, *args, **kwargs):
        pass

    async def analyze_image(self, path):
        return type(self).returns


@pytest.fixture
def stub_ai(monkeypatch):
    def _install(tags: ClothingTags):
        _StubAI.returns = tags
        monkeypatch.setattr(tagging, "AIService", _StubAI)
        # the real budget helper inspects the service's endpoints
        monkeypatch.setattr(tagging, "_tagging_call_budget", lambda _svc: 30)

    return _install


@pytest.fixture
def item_image(tmp_path):
    p = tmp_path / "item.jpg"
    Image.new("RGB", (64, 64), "black").save(p)
    return p


# --------------------------------------------------------------------------
# 1. schema
# --------------------------------------------------------------------------


class TestItemTagsUserFields:
    def test_accepts_user_owned_keys(self):
        tags = ItemTags(
            material="100% Cotton",
            size="L",
            care_instructions="Machine wash cold, lay flat",
            source_url="https://example.invalid/product/1",
        )
        assert tags.size == "L"
        assert tags.care_instructions == "Machine wash cold, lay flat"
        assert tags.source_url == "https://example.invalid/product/1"

    def test_user_keys_are_optional(self):
        tags = ItemTags(material="100% Wool")
        assert tags.size is None
        assert tags.care_instructions is None


# --------------------------------------------------------------------------
# 2. ItemService.update
# --------------------------------------------------------------------------


class TestTagsMergeOnUpdate:
    @pytest.mark.asyncio
    async def test_update_preserves_keys_not_sent(self, db_session, test_user):
        item = await _make_item(
            db_session,
            test_user,
            tags={"size": "L", "care_instructions": "Hand wash", "material": "100% Cotton"},
        )
        service = ItemService(db_session)

        updated = await service.update(item, ItemUpdate(tags=ItemTags(pattern="solid")))

        assert updated.tags["size"] == "L"
        assert updated.tags["care_instructions"] == "Hand wash"
        assert updated.tags["material"] == "100% Cotton"
        assert updated.tags["pattern"] == "solid"

    @pytest.mark.asyncio
    async def test_update_overwrites_keys_that_are_sent(self, db_session, test_user):
        item = await _make_item(db_session, test_user, tags={"material": "100% Cotton"})
        service = ItemService(db_session)

        updated = await service.update(item, ItemUpdate(tags=ItemTags(material="100% Linen")))

        assert updated.tags["material"] == "100% Linen"

    @pytest.mark.asyncio
    async def test_explicit_null_clears_one_key(self, db_session, test_user):
        item = await _make_item(
            db_session,
            test_user,
            tags={"size": "L", "pattern": "striped"},
            pattern="striped",
        )
        service = ItemService(db_session)

        updated = await service.update(item, ItemUpdate.model_validate({"tags": {"pattern": None}}))

        assert "pattern" not in updated.tags
        assert updated.tags["size"] == "L", "clearing one key must not drop the others"

    @pytest.mark.asyncio
    async def test_clearing_a_tag_clears_its_column(self, db_session, test_user):
        """The mirror follows what was sent, not the merged result."""
        item = await _make_item(
            db_session,
            test_user,
            tags={"pattern": "striped"},
            pattern="striped",
        )
        service = ItemService(db_session)

        updated = await service.update(item, ItemUpdate.model_validate({"tags": {"pattern": None}}))

        assert updated.pattern is None

    @pytest.mark.asyncio
    async def test_setting_a_tag_sets_its_column(self, db_session, test_user):
        item = await _make_item(db_session, test_user)
        service = ItemService(db_session)

        updated = await service.update(item, ItemUpdate(tags=ItemTags(material="100% Silk")))

        assert updated.material == "100% Silk"
        assert updated.tags["material"] == "100% Silk"


# --------------------------------------------------------------------------
# 3. tagging worker
# --------------------------------------------------------------------------


class TestTagsMergeOnAnalysis:
    @pytest.mark.asyncio
    async def test_analysis_preserves_user_tag_keys(
        self, db_session, test_user, stub_ai, item_image
    ):
        item = await _make_item(
            db_session,
            test_user,
            image_path=str(item_image),
            tags={"size": "L", "care_instructions": "Hand wash cold"},
        )
        stub_ai(_ai_tags())

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await tagging.tag_item_image({}, str(item.id), str(item_image))

        await db_session.refresh(item)
        assert item.tags["size"] == "L"
        assert item.tags["care_instructions"] == "Hand wash cold"
        assert item.tags["pattern"] == "solid", "AI values must still be written"

    @pytest.mark.asyncio
    async def test_empty_ai_value_does_not_erase_existing(
        self, db_session, test_user, stub_ai, item_image
    ):
        """The model returns material=None; a real material must survive it."""
        item = await _make_item(
            db_session,
            test_user,
            image_path=str(item_image),
            tags={"material": "100% Leather"},
            material="100% Leather",
        )
        stub_ai(_ai_tags(material=None))

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await tagging.tag_item_image({}, str(item.id), str(item_image))

        await db_session.refresh(item)
        assert item.material == "100% Leather"
        assert item.tags["material"] == "100% Leather"

    @pytest.mark.asyncio
    async def test_tags_and_columns_agree_after_analysis(
        self, db_session, test_user, stub_ai, item_image
    ):
        """A user-set column is kept; the JSONB must reflect the kept value."""
        item = await _make_item(
            db_session,
            test_user,
            image_path=str(item_image),
            tags={"style": ["casual"]},
            style=["casual"],
        )
        stub_ai(_ai_tags(style=["modern"]))

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await tagging.tag_item_image({}, str(item.id), str(item_image))

        await db_session.refresh(item)
        assert list(item.style) == ["casual"], "column guard must keep the user's style"
        assert list(item.tags["style"]) == ["casual"], "tags must hold the kept value, not the AI's"

    @pytest.mark.asyncio
    async def test_analysis_fills_empty_fields(self, db_session, test_user, stub_ai, item_image):
        """The merge must not stop the AI populating genuinely empty fields."""
        item = await _make_item(db_session, test_user, image_path=str(item_image))
        stub_ai(_ai_tags())

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await tagging.tag_item_image({}, str(item.id), str(item_image))

        await db_session.refresh(item)
        assert item.pattern == "solid"
        assert item.formality == "casual"
        assert item.tags["pattern"] == "solid"
        assert item.ai_processed is True

    @pytest.mark.asyncio
    async def test_reanalysis_is_idempotent_for_user_keys(
        self, db_session, test_user, stub_ai, item_image
    ):
        """Running analysis twice must not erode user keys on the second pass."""
        item = await _make_item(
            db_session,
            test_user,
            image_path=str(item_image),
            tags={"size": "M", "care_instructions": "Dry clean"},
        )
        stub_ai(_ai_tags())

        for _ in range(2):
            with (
                patch("app.workers.tagging.get_db_session", return_value=db_session),
                patch.object(db_session, "close", new_callable=AsyncMock),
            ):
                await tagging.tag_item_image({}, str(item.id), str(item_image))
            await db_session.refresh(item)

        assert item.tags["size"] == "M"
        assert item.tags["care_instructions"] == "Dry clean"

    @pytest.mark.asyncio
    async def test_user_set_fit_survives_analysis(self, db_session, test_user, stub_ai, item_image):
        """`fit` has no mirrored column, so only the JSONB merge protects it."""
        item = await _make_item(
            db_session, test_user, image_path=str(item_image), tags={"fit": "relaxed"}
        )
        stub_ai(_ai_tags(fit="slim"))

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await tagging.tag_item_image({}, str(item.id), str(item_image))

        await db_session.refresh(item)
        assert item.tags["fit"] == "relaxed"
