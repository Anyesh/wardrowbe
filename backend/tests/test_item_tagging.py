"""Tests for the external-agent tagging lifecycle (tagging_status/tagged_by/tagged_at):
create/bulk-create/bulk-analyze gating when vision is off or skip_ai is set, the
pending filter, the write-back guard on PATCH, retag, tag-to-column projection, and
the worker's origin stamping. Includes regressions for two review-caught bugs: the
write-back guard missing emptiness *inside* a nested tags dict, and the worker
reverting a manual origin back to auto when a queued job lands after a write-back.
"""

from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.item import ClothingItem, ItemStatus, TaggedBy, TaggingStatus
from app.schemas.item import ItemCreate, ItemTags, ItemUpdate
from app.services.ai_service import ClothingTags
from app.services.item_service import ItemService
from app.workers import tagging


def _make_test_image_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), (120, 80, 40)).save(buf, format="JPEG")
    return buf.getvalue()


async def _get_item(db_session: AsyncSession, item_id) -> ClothingItem:
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return result.scalar_one()


class TestTaggingDefaults:
    @pytest.mark.asyncio
    async def test_new_item_defaults_to_pending(self, db_session: AsyncSession, test_user):
        service = ItemService(db_session)
        item = await service.create(
            user_id=test_user.id,
            item_data=ItemCreate(type="shirt"),
            image_paths={"image_path": "test/defaults.jpg"},
        )
        assert item.tagging_status == TaggingStatus.pending
        assert item.tagged_by is None
        assert item.tagged_at is None


class TestCreateGating:
    @pytest.mark.asyncio
    async def test_default_enqueues_and_stays_pending(self, client: AsyncClient, auth_headers):
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "job-1"
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items",
                files={"image": ("shirt.jpg", _make_test_image_bytes(), "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["status"] == "processing"
        assert data["tagging_status"] == "pending"
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_ai_marks_ready_and_pending(self, client: AsyncClient, auth_headers):
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items",
                files={"image": ("shirt.jpg", _make_test_image_bytes(), "image/jpeg")},
                data={"skip_ai": "true"},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["status"] == "ready"
        assert data["tagging_status"] == "pending"
        mock_redis.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_vision_disabled_marks_ready_and_pending(
        self, client: AsyncClient, auth_headers, monkeypatch
    ):
        monkeypatch.setattr("app.api.items.settings", Settings(ai_vision_enabled=False))
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            response = await client.post(
                "/api/v1/items",
                files={"image": ("shirt.jpg", _make_test_image_bytes(), "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["status"] == "ready"
        assert data["tagging_status"] == "pending"
        mock_create_pool.assert_not_called()


class TestBulkCreateGating:
    @pytest.mark.asyncio
    async def test_skip_ai_marks_ready_and_pending_without_pool(
        self, client: AsyncClient, auth_headers
    ):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                data={"skip_ai": "true"},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["results"][0]["item"]["status"] == "ready"
        assert data["results"][0]["item"]["tagging_status"] == "pending"
        mock_create_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_vision_disabled_marks_ready_and_pending_without_pool(
        self, client: AsyncClient, auth_headers, monkeypatch
    ):
        monkeypatch.setattr("app.api.items.settings", Settings(ai_vision_enabled=False))
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["results"][0]["item"]["status"] == "ready"
        assert data["results"][0]["item"]["tagging_status"] == "pending"
        mock_create_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_queues_and_stays_pending(self, client: AsyncClient, auth_headers):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "job-1"
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["results"][0]["item"]["status"] == "processing"
        assert data["results"][0]["item"]["tagging_status"] == "pending"
        mock_redis.enqueue_job.assert_called_once()


class TestBulkAnalyzeGating:
    @pytest.mark.asyncio
    async def test_vision_disabled_resets_items_and_reports_zero_queued(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession, monkeypatch
    ):
        monkeypatch.setattr("app.api.items.settings", Settings(ai_vision_enabled=False))

        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/bulk-analyze.jpg",
            status=ItemStatus.ready,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.auto,
            tagged_at=datetime.now(UTC),
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        response = await client.post(
            "/api/v1/items/bulk/analyze",
            json={"item_ids": [str(item.id)]},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["queued"] == 0
        assert data["failed"] == 0

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.tagging_status == TaggingStatus.pending
        assert refreshed.tagged_by is None
        assert refreshed.tagged_at is None


class TestPendingFilter:
    @pytest.mark.asyncio
    async def test_filters_to_pending_only(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        pending_item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/pending.jpg",
            status=ItemStatus.ready,
        )
        tagged_item = ClothingItem(
            user_id=test_user.id,
            type="pants",
            image_path="test/tagged.jpg",
            status=ItemStatus.ready,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.auto,
            tagged_at=datetime.now(UTC),
        )
        db_session.add_all([pending_item, tagged_item])
        await db_session.commit()

        response = await client.get(
            "/api/v1/items", params={"tagging_status": "pending"}, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        ids = {item["id"] for item in data["items"]}
        assert ids == {str(pending_item.id)}


class TestWriteBack:
    @pytest.mark.asyncio
    async def test_real_tag_content_flips_to_tagged_manual(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/writeback.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"tags": {"colors": ["blue"], "primary_color": "blue"}},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["tagging_status"] == "tagged"
        assert data["tagged_by"] == "manual"
        assert data["tagged_at"] is not None
        assert data["colors"] == ["blue"]

    @pytest.mark.asyncio
    async def test_flat_empty_values_stay_pending(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/writeback-empty.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"colors": []},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["tagging_status"] == "pending"
        assert data["tagged_by"] is None

    @pytest.mark.asyncio
    async def test_empty_nested_tags_dict_stays_pending(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/writeback-nested-empty.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"tags": {"colors": []}},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["tagging_status"] == "pending"
        assert data["tagged_by"] is None

    @pytest.mark.asyncio
    async def test_body_cannot_forge_tagged_by(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/writeback-forge.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"tagged_by": "manual", "tagging_status": "tagged", "name": "Same Name"},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["tagging_status"] == "pending"
        assert data["tagged_by"] is None

    @pytest.mark.asyncio
    async def test_already_tagged_item_not_restamped_by_unrelated_update(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        original_tagged_at = datetime.now(UTC) - timedelta(hours=1)
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/writeback-restamp.jpg",
            status=ItemStatus.ready,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.auto,
            tagged_at=original_tagged_at,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"name": "Renamed Shirt"},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.tagging_status == TaggingStatus.tagged
        assert refreshed.tagged_by == TaggedBy.auto
        assert refreshed.tagged_at == original_tagged_at


class TestRetag:
    @pytest.mark.asyncio
    async def test_resets_to_pending_without_touching_status(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/retag.jpg",
            status=ItemStatus.ready,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.manual,
            tagged_at=datetime.now(UTC),
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.post(f"/api/v1/items/{item.id}/retag", headers=auth_headers)

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["status"] == "ready"
        assert data["tagging_status"] == "pending"
        assert data["tagged_by"] is None
        assert data["tagged_at"] is None

    @pytest.mark.asyncio
    async def test_404_for_missing_item(self, client: AsyncClient, auth_headers):
        response = await client.post(f"/api/v1/items/{uuid4()}/retag", headers=auth_headers)
        assert response.status_code == 404


class TestTagsToColumnsProjection:
    @pytest.mark.asyncio
    async def test_update_projects_nested_tag_fields_onto_columns(
        self, db_session: AsyncSession, test_user
    ):
        service = ItemService(db_session)
        item = await service.create(
            user_id=test_user.id,
            item_data=ItemCreate(type="unknown"),
            image_paths={"image_path": "test/projection.jpg"},
        )

        updated = await service.update(
            item,
            ItemUpdate(
                tags=ItemTags(
                    colors=["red"],
                    primary_color="red",
                    pattern="striped",
                    material="cotton",
                    style=["casual"],
                    season=["summer"],
                    formality="casual",
                )
            ),
        )

        assert updated.colors == ["red"]
        assert updated.primary_color == "red"
        assert updated.pattern == "striped"
        assert updated.material == "cotton"
        assert updated.style == ["casual"]
        assert updated.season == ["summer"]
        assert updated.formality == "casual"


class TestWorkerTaggingOrigin:
    @pytest.mark.asyncio
    async def test_happy_path_stamps_auto(self, db_session: AsyncSession, test_user, monkeypatch):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/worker-auto.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        stub_tags = ClothingTags(
            type="shirt", primary_color="blue", colors=["blue"], confidence=0.9
        )

        class _StubAI:
            def __init__(self, *args, **kwargs):
                pass

            async def analyze_image(self, path):
                return stub_tags

        monkeypatch.setattr(tagging, "AIService", _StubAI)

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await tagging.tag_item_image({}, str(item.id), __file__)

        assert result["status"] == "success"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.tagging_status == TaggingStatus.tagged
        assert refreshed.tagged_by == TaggedBy.auto
        assert refreshed.tagged_at is not None
        assert refreshed.status == ItemStatus.ready

    @pytest.mark.asyncio
    async def test_manual_origin_survives_late_worker_completion(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        manual_tagged_at = datetime.now(UTC) - timedelta(minutes=5)
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/worker-race.jpg",
            status=ItemStatus.processing,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.manual,
            tagged_at=manual_tagged_at,
        )
        db_session.add(item)
        await db_session.commit()

        stub_tags = ClothingTags(
            type="pants", primary_color="black", colors=["black"], confidence=0.7
        )

        class _StubAI:
            def __init__(self, *args, **kwargs):
                pass

            async def analyze_image(self, path):
                return stub_tags

        monkeypatch.setattr(tagging, "AIService", _StubAI)

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await tagging.tag_item_image({}, str(item.id), __file__)

        assert result["status"] == "success"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.tagging_status == TaggingStatus.tagged
        assert refreshed.tagged_by == TaggedBy.manual
        assert refreshed.tagged_at == manual_tagged_at
        assert refreshed.ai_processed is True
        assert refreshed.status == ItemStatus.ready


class TestMarkItemTaggingSkipped:
    @pytest.mark.asyncio
    async def test_resets_tagging_status_to_pending(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/skip.jpg",
            status=ItemStatus.processing,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.auto,
        )
        db_session.add(item)
        await db_session.commit()

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await tagging.mark_item_tagging_skipped({}, str(item.id))

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.tagging_status == TaggingStatus.pending
