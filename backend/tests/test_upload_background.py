"""Uploads that ask for the background to be removed: the image worker cleans the photo and then
queues the tagging itself, also when the removal fails."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService
from app.workers.background_removal import remove_item_background_job


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (400, 600), (10, 200, 30)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _redis(job_id: str = "job-1") -> AsyncMock:
    redis = AsyncMock()
    redis.enqueue_job.return_value = MagicMock(job_id=job_id)
    return redis


async def _stored_item(db_session: AsyncSession, user: User) -> ClothingItem:
    paths = await ImageService().process_and_store(
        user_id=user.id, image_data=_jpeg(), original_filename="t.jpg"
    )
    item = ClothingItem(
        user_id=user.id,
        type="unknown",
        image_path=paths["image_path"],
        thumbnail_path=paths["thumbnail_path"],
        medium_path=paths["medium_path"],
        status=ItemStatus.processing,
        processing_kind="background_removal",
    )
    db_session.add(item)
    await db_session.commit()
    return item


class TestUploadQueuesRemovalFirst:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "endpoint,field", [("/api/v1/items", "image"), ("/api/v1/items/bulk", "images")]
    )
    async def test_removal_then_tagging(self, client: AsyncClient, auth_headers, endpoint, field):
        redis = _redis()
        with patch("app.api.items.create_pool", AsyncMock(return_value=redis)):
            response = await client.post(
                endpoint,
                files=[(field, ("shirt.jpg", _jpeg(), "image/jpeg"))],
                data={"remove_background": "true"},
                headers=auth_headers,
            )
        assert response.status_code == 201, response.json()
        name, item_id, color, path = redis.enqueue_job.call_args.args
        assert name == "remove_item_background_job"
        assert color == "#FFFFFF"
        assert path.endswith(".jpg")
        assert redis.enqueue_job.call_args.kwargs["_queue_name"] == "arq:images"

    @pytest.mark.asyncio
    async def test_without_the_option_only_tags(self, client: AsyncClient, auth_headers):
        redis = _redis()
        with patch("app.api.items.create_pool", AsyncMock(return_value=redis)):
            response = await client.post(
                "/api/v1/items/bulk",
                files=[("images", ("shirt.jpg", _jpeg(), "image/jpeg"))],
                headers=auth_headers,
            )
        assert response.status_code == 201
        redis.enqueue_job.assert_called_once()
        name, _, path = redis.enqueue_job.call_args.args
        assert name == "tag_item_image"
        assert path.endswith(".jpg")
        assert redis.enqueue_job.call_args.kwargs["_queue_name"] == "arq:tagging"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "endpoint,field", [("/api/v1/items", "image"), ("/api/v1/items/bulk", "images")]
    )
    async def test_removal_runs_without_tagging(
        self, client: AsyncClient, auth_headers, endpoint, field
    ):
        # Tagging skipped: the background still goes, and the worker is told not to tag.
        redis = _redis()
        with patch("app.api.items.create_pool", AsyncMock(return_value=redis)):
            response = await client.post(
                endpoint,
                files=[(field, ("shirt.jpg", _jpeg(), "image/jpeg"))],
                data={"remove_background": "true", "skip_ai": "true"},
                headers=auth_headers,
            )
        assert response.status_code == 201, response.json()
        redis.enqueue_job.assert_called_once()
        name, _, _, then_tag = redis.enqueue_job.call_args.args
        assert name == "remove_item_background_job"
        assert then_tag is None


class TestWorkerChainsTagging:
    @pytest.mark.asyncio
    async def test_success_queues_tagging(self, db_session: AsyncSession, test_user):
        item = await _stored_item(db_session, test_user)
        redis = _redis("tag-job")
        provider = MagicMock()
        provider.remove.side_effect = lambda img: Image.new("RGBA", img.size, (0, 0, 255, 255))
        with (
            patch("app.workers.background_removal.get_db_session", return_value=db_session),
            patch.object(db_session, "close", AsyncMock()),
            patch("app.services.background_removal.get_provider", return_value=provider),
        ):
            result = await remove_item_background_job(
                {"redis": redis}, str(item.id), "#FFFFFF", "/data/x.jpg"
            )
        assert result["status"] == "success" and result["tagging"] is True
        redis.enqueue_job.assert_called_once_with(
            "tag_item_image", str(item.id), "/data/x.jpg", _queue_name="arq:tagging"
        )
        refreshed = await db_session.scalar(select(ClothingItem).where(ClothingItem.id == item.id))
        assert refreshed.status == ItemStatus.processing
        assert refreshed.processing_kind is None
        assert refreshed.ai_job_id == "tag-job"
        assert refreshed.original_image_path

    @pytest.mark.asyncio
    async def test_failed_removal_still_tags(self, db_session: AsyncSession, test_user):
        item = await _stored_item(db_session, test_user)
        redis = _redis("tag-job")
        provider = MagicMock()
        provider.remove.side_effect = RuntimeError("model missing")
        with (
            patch("app.workers.background_removal.get_db_session", return_value=db_session),
            patch.object(db_session, "close", AsyncMock()),
            patch("app.services.background_removal.get_provider", return_value=provider),
        ):
            result = await remove_item_background_job(
                {"redis": redis}, str(item.id), "#FFFFFF", "/data/x.jpg"
            )
        assert result["status"] == "error" and result["tagging"] is True
        assert redis.enqueue_job.call_args.args[0] == "tag_item_image"
        refreshed = await db_session.scalar(select(ClothingItem).where(ClothingItem.id == item.id))
        assert refreshed.status == ItemStatus.processing
        assert refreshed.original_image_path is None
