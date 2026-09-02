"""Tests for POST /items/bulk/rotate, POST /items/bulk/remove-background,
and the remove_item_background_job worker function.
"""

from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService
from app.workers.background_removal import remove_item_background_job

BLUE = (0, 0, 255)


def _jpeg_bytes(size: tuple[int, int] = (400, 600)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (10, 200, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def _mock_provider():
    provider = MagicMock()
    provider.remove.side_effect = lambda img: Image.new("RGBA", img.size, (*BLUE, 255))
    return provider


async def _make_item(db_session: AsyncSession, user: User, **overrides) -> ClothingItem:
    svc = ImageService()
    paths = await svc.process_and_store(
        user_id=user.id, image_data=_jpeg_bytes(), original_filename="test.jpg"
    )
    defaults = {
        "user_id": user.id,
        "type": "shirt",
        "image_path": paths["image_path"],
        "medium_path": paths["medium_path"],
        "thumbnail_path": paths["thumbnail_path"],
        "image_hash": paths["image_hash"],
        "status": ItemStatus.ready,
    }
    defaults.update(overrides)
    item = ClothingItem(**defaults)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _get_item(db_session: AsyncSession, item_id) -> ClothingItem:
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return result.scalar_one()


class TestBulkRotate:
    @pytest.mark.asyncio
    async def test_rotates_selected_items(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await _make_item(db_session, test_user)
        svc = ImageService()
        before_size = Image.open(svc.get_image_path(item.image_path)).size

        response = await client.post(
            "/api/v1/items/bulk/rotate",
            headers=auth_headers,
            json={"item_ids": [str(item.id)], "direction": "cw"},
        )

        assert response.status_code == 200
        assert response.json() == {"rotated": 1, "failed": 0, "skipped": 0, "errors": []}
        after_size = Image.open(svc.get_image_path(item.image_path)).size
        assert after_size == (before_size[1], before_size[0])

    @pytest.mark.asyncio
    async def test_defaults_to_clockwise(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/rotate",
            headers=auth_headers,
            json={"item_ids": [str(item.id)]},
        )

        assert response.status_code == 200
        assert response.json()["rotated"] == 1

    @pytest.mark.asyncio
    async def test_rejects_invalid_direction(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/rotate",
            headers=auth_headers,
            json={"item_ids": [str(item.id)], "direction": "sideways"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_item_counts_as_failed(
        self, client: AsyncClient, auth_headers, test_user
    ):
        response = await client.post(
            "/api/v1/items/bulk/rotate",
            headers=auth_headers,
            json={"item_ids": [str(uuid4())], "direction": "cw"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["rotated"] == 0
        assert body["failed"] == 1
        assert len(body["errors"]) == 1

    @pytest.mark.asyncio
    async def test_item_without_image_counts_as_failed(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = ClothingItem(
            user_id=test_user.id, type="shirt", image_path="", status=ItemStatus.ready
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        response = await client.post(
            "/api/v1/items/bulk/rotate",
            headers=auth_headers,
            json={"item_ids": [str(item.id)], "direction": "cw"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["rotated"] == 0
        assert body["failed"] == 1

    @pytest.mark.asyncio
    async def test_select_all_rotates_every_item(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        await _make_item(db_session, test_user)
        await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/rotate",
            headers=auth_headers,
            json={"select_all": True, "direction": "ccw"},
        )

        assert response.status_code == 200
        assert response.json()["rotated"] == 2

    @pytest.mark.asyncio
    async def test_skips_items_currently_processing(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # A background-removal job may still be writing image_path/medium_path/
        # thumbnail_path for this item - rotating it now would race that writer.
        processing_item = await _make_item(db_session, test_user, status=ItemStatus.processing)
        ready_item = await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/rotate",
            headers=auth_headers,
            json={"item_ids": [str(processing_item.id), str(ready_item.id)], "direction": "cw"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["rotated"] == 1
        assert body["skipped"] == 1
        assert body["failed"] == 0


class TestBulkRemoveBackground:
    @pytest.mark.asyncio
    async def test_queues_selected_items_and_clears_stale_ai_started_at(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # A previously-tagged item carries a real, old ai_started_at - this is a
        # regression test for reusing item.status=processing for a bg-removal
        # job leaking a stale tagging timestamp into the frontend's "elapsed
        # analyzing time" display (it showed nonsense figures like "54m").
        item = await _make_item(
            db_session,
            test_user,
            ai_started_at=datetime.now(UTC) - timedelta(hours=2),
        )
        item_id = item.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/remove-background",
                headers=auth_headers,
                json={"item_ids": [str(item_id)]},
            )

        assert response.status_code == 200
        assert response.json() == {
            "queued": 1,
            "failed": 0,
            "skipped": 0,
            "already_done": 0,
            "errors": [],
        }
        mock_redis.enqueue_job.assert_called_once_with(
            "remove_item_background_job",
            str(item_id),
            "#FFFFFF",
            _queue_name="arq:tagging",
        )

        db_session.expire_all()
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.status == ItemStatus.processing
        assert refreshed.ai_started_at is None
        assert refreshed.ai_job_id == "fake-job-id"
        assert refreshed.processing_kind == "background_removal"

    @pytest.mark.asyncio
    async def test_skips_items_already_processing(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # ai_job_id set - a genuinely live job, which is what makes this item
        # skip-worthy rather than a stuck row from a previously-failed enqueue.
        already_processing = await _make_item(
            db_session, test_user, status=ItemStatus.processing, ai_job_id="live-job-id"
        )
        ready_item = await _make_item(db_session, test_user)

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/remove-background",
                headers=auth_headers,
                json={"item_ids": [str(already_processing.id), str(ready_item.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 1
        assert body["skipped"] == 1
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_stuck_processing_item_with_no_job_is_retried(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # status=processing with no ai_job_id - a previously-failed enqueue, not
        # a live job - must be retried rather than skipped forever.
        stuck = await _make_item(db_session, test_user, status=ItemStatus.processing)

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/remove-background",
                headers=auth_headers,
                json={"item_ids": [str(stuck.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 1
        assert body["skipped"] == 0
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_failure_marks_touched_items_error(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await _make_item(db_session, test_user)
        item_id = item.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.side_effect = Exception("no redis")
            response = await client.post(
                "/api/v1/items/bulk/remove-background",
                headers=auth_headers,
                json={"item_ids": [str(item_id)]},
            )

        assert response.status_code == 500
        db_session.expire_all()
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.status == ItemStatus.error

    @pytest.mark.asyncio
    async def test_already_done_items_are_skipped_and_reported(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # original_image_path set means a previous run already flattened this
        # item's background - re-running the provider over it would stomp the
        # backup with a background-removed image of a background-removed image.
        done = await _make_item(db_session, test_user, original_image_path="test/orig.jpg")
        fresh = await _make_item(db_session, test_user)

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/remove-background",
                headers=auth_headers,
                json={"item_ids": [str(done.id), str(fresh.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 1
        assert body["already_done"] == 1
        assert body["skipped"] == 0
        mock_redis.enqueue_job.assert_called_once_with(
            "remove_item_background_job",
            str(fresh.id),
            "#FFFFFF",
            _queue_name="arq:tagging",
        )

    @pytest.mark.asyncio
    async def test_second_identical_call_queues_nothing(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await _make_item(db_session, test_user)
        item_id = item.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis

            first = await client.post(
                "/api/v1/items/bulk/remove-background",
                headers=auth_headers,
                json={"item_ids": [str(item_id)]},
            )
        assert first.json()["queued"] == 1

        # Simulate the job's own success write, since it never runs here.
        db_session.expire_all()
        refreshed = await _get_item(db_session, item_id)
        refreshed.status = ItemStatus.ready
        refreshed.processing_kind = None
        refreshed.original_image_path = "test/orig.jpg"
        await db_session.commit()

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis

            second = await client.post(
                "/api/v1/items/bulk/remove-background",
                headers=auth_headers,
                json={"item_ids": [str(item_id)]},
            )

        assert second.status_code == 200
        body = second.json()
        assert body["queued"] == 0
        assert body["already_done"] == 1
        mock_redis.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_restored_item_is_queued_again(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # original_image_path cleared (restored) means there's no backup to
        # protect - eligible for a fresh removal run.
        restored = await _make_item(db_session, test_user, original_image_path=None)

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/remove-background",
                headers=auth_headers,
                json={"item_ids": [str(restored.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 1
        assert body["already_done"] == 0
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_bg_color_is_forwarded_to_job(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await _make_item(db_session, test_user)

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/remove-background",
                headers=auth_headers,
                json={"item_ids": [str(item.id)], "bg_color": "#000000"},
            )

        assert response.status_code == 200
        mock_redis.enqueue_job.assert_called_once_with(
            "remove_item_background_job",
            str(item.id),
            "#000000",
            _queue_name="arq:tagging",
        )


class TestRemoveItemBackgroundJob:
    @pytest.mark.asyncio
    async def test_success_sets_ready_and_backup_path(self, db_session: AsyncSession, test_user):
        item = await _make_item(
            db_session,
            test_user,
            status=ItemStatus.processing,
            ai_job_id="live-job-id",
            processing_kind="background_removal",
        )

        with (
            patch("app.workers.background_removal.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch("app.services.background_removal.get_provider", return_value=_mock_provider()),
        ):
            result = await remove_item_background_job({}, str(item.id), "#FFFFFF")

        assert result["status"] == "success"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.original_image_path is not None
        assert refreshed.original_image_path.endswith("_orig.jpg")
        assert refreshed.processing_kind is None
        assert refreshed.ai_started_at is None

    @pytest.mark.asyncio
    async def test_sets_ai_started_at_before_provider_runs(
        self, db_session: AsyncSession, test_user
    ):
        item = await _make_item(
            db_session,
            test_user,
            status=ItemStatus.processing,
            ai_job_id="live-job-id",
            processing_kind="background_removal",
        )
        seen: dict = {}

        def _remove(img):
            # Reads the same ORM object the job mutated (shared identity map on
            # db_session), proving the started-at write and its commit happen
            # before the (thread-offloaded) provider call, not after.
            seen["ai_started_at"] = item.ai_started_at
            return Image.new("RGBA", img.size, (*BLUE, 255))

        provider = MagicMock()
        provider.remove.side_effect = _remove

        with (
            patch("app.workers.background_removal.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch("app.services.background_removal.get_provider", return_value=provider),
        ):
            await remove_item_background_job({}, str(item.id), "#FFFFFF")

        assert seen["ai_started_at"] is not None

    @pytest.mark.asyncio
    async def test_provider_failure_sets_error_status(self, db_session: AsyncSession, test_user):
        stale_failed_at = datetime.now(UTC) - timedelta(days=1)
        item = await _make_item(
            db_session,
            test_user,
            status=ItemStatus.processing,
            ai_job_id="live-job-id",
            processing_kind="background_removal",
            ai_raw_response={"unrelated": "prior tagging failure"},
            ai_failed_at=stale_failed_at,
        )

        failing_provider = MagicMock()
        failing_provider.remove.side_effect = RuntimeError("boom")

        with (
            patch("app.workers.background_removal.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch("app.services.background_removal.get_provider", return_value=failing_provider),
        ):
            result = await remove_item_background_job({}, str(item.id), "#FFFFFF")

        assert result["status"] == "error"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.error
        # Kind is kept on failure so the grid can label and retry it as a
        # background-removal failure, not a generic "Analysis failed".
        assert refreshed.processing_kind == "background_removal"
        assert refreshed.ai_started_at is None
        # A background-removal job never touches AI tagging's own failure
        # bookkeeping - clobbering it here would start a bogus AI retry cooldown.
        assert refreshed.ai_raw_response == {"unrelated": "prior tagging failure"}
        assert refreshed.ai_failed_at == stale_failed_at

    @pytest.mark.asyncio
    async def test_missing_item_returns_error_without_raising(self, db_session: AsyncSession):
        with (
            patch("app.workers.background_removal.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await remove_item_background_job({}, str(uuid4()), "#FFFFFF")

        assert result == {"status": "error", "error": "Item not found"}


async def _make_other_user(db_session: AsyncSession) -> User:
    other_id = uuid4()
    other_user = User(
        id=other_id,
        external_id=f"other-{other_id}",
        email=f"other-{other_id}@example.com",
        display_name="Other",
        timezone="UTC",
        is_active=True,
        onboarding_completed=False,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)
    return other_user


class TestBulkEndpointsAuthBoundary:
    @pytest.mark.asyncio
    async def test_bulk_rotate_skips_other_users_item(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        other_user = await _make_other_user(db_session)
        other_item = await _make_item(db_session, other_user)
        other_item_id = other_item.id
        original_updated_at = other_item.updated_at

        response = await client.post(
            "/api/v1/items/bulk/rotate",
            headers=auth_headers,
            json={"item_ids": [str(other_item_id)], "direction": "cw"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["rotated"] == 0
        assert body["failed"] == 1
        assert str(other_item_id) in body["errors"][0]

        db_session.expire_all()
        refreshed = await _get_item(db_session, other_item_id)
        assert refreshed.updated_at == original_updated_at

    @pytest.mark.asyncio
    async def test_bulk_remove_background_skips_other_users_item(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        other_user = await _make_other_user(db_session)
        other_item = await _make_item(db_session, other_user)
        other_item_id = other_item.id

        response = await client.post(
            "/api/v1/items/bulk/remove-background",
            headers=auth_headers,
            json={"item_ids": [str(other_item_id)]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 0
        assert body["failed"] == 1
        assert str(other_item_id) in body["errors"][0]

        db_session.expire_all()
        refreshed = await _get_item(db_session, other_item_id)
        assert refreshed.status == ItemStatus.ready
