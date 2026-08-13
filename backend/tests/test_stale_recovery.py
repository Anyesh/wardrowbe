from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from arq.jobs import JobStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.workers import worker as worker_module
from app.workers.worker import recover_stale_processing_items

# A never-None sentinel is enough for tests whose own fixture never reaches
# Job(...) - but the sweep scans the whole table, and this suite's db_session
# fixture doesn't roll back between tests, so leftover `processing` rows with a
# real ai_job_id from earlier tests can still be candidates. Pair the sentinel
# with a default-not_found fake Job so those leftovers don't crash the sweep.
_FAKE_REDIS = object()


class _DefaultNotFoundJob:
    def __init__(self, job_id, redis, _queue_name=None):
        self.job_id = job_id

    async def status(self):
        return JobStatus.not_found


class TestRecoverStaleProcessingItems:
    @pytest.mark.asyncio
    async def test_marks_stale_items_as_error(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        monkeypatch.setattr(worker_module, "Job", _DefaultNotFoundJob)
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/stale.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        # Pretend it's 3 hours in the future so the item looks stale
        future = datetime.now(UTC) + timedelta(hours=3)
        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch("app.workers.worker.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = future
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            # No ai_job_id on this fixture, so `lost=True` short-circuits before
            # any Job(...) call - the sentinel is only used for the redis-present check.
            await recover_stale_processing_items({"redis": _FAKE_REDIS})

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.error
        assert updated.ai_raw_response == {"error": "Job lost or timed out"}

    @pytest.mark.asyncio
    async def test_does_not_touch_recent_processing(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        monkeypatch.setattr(worker_module, "Job", _DefaultNotFoundJob)
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/recent.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            # Still exercises the redis-present path: a recent item just doesn't
            # match either candidate window, so it never reaches Job(...) either.
            await recover_stale_processing_items({"redis": _FAKE_REDIS})

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.processing

    @pytest.mark.asyncio
    async def test_does_not_touch_ready_items(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        monkeypatch.setattr(worker_module, "Job", _DefaultNotFoundJob)
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/ready.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        # Even if we pretend it's the future, ready items should not be touched
        future = datetime.now(UTC) + timedelta(hours=3)
        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch("app.workers.worker.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = future
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await recover_stale_processing_items({"redis": _FAKE_REDIS})

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.ready

    @pytest.mark.asyncio
    async def test_no_op_without_redis_in_ctx(self, db_session: AsyncSession, test_user):
        # Never blind-condemn: an empty ctx (no redis) must be a safe no-op, even
        # for an item that would otherwise be a clear candidate.
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/no-redis.jpg",
            status=ItemStatus.processing,
            updated_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await recover_stale_processing_items({})

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.processing


class TestRecoverStaleProcessingItemsJobStatus:
    """The never-started branch is gated on real job status in Redis, not just
    elapsed time - a large batch can legitimately queue for a long time."""

    def _fake_job_class(self, status: JobStatus):
        class _FakeJob:
            def __init__(self, job_id, redis, _queue_name=None):
                self.job_id = job_id

            async def status(self_inner):
                return status

        return _FakeJob

    @pytest.mark.asyncio
    async def test_never_started_condemned_when_job_not_found(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        monkeypatch.setattr(worker_module, "Job", self._fake_job_class(JobStatus.not_found))
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/lost.jpg",
            status=ItemStatus.processing,
            ai_job_id="fake-job-id",
            updated_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await recover_stale_processing_items({"redis": _FAKE_REDIS})

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.error

    @pytest.mark.asyncio
    async def test_never_started_condemned_when_job_complete(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        monkeypatch.setattr(worker_module, "Job", self._fake_job_class(JobStatus.complete))
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/complete-but-processing.jpg",
            status=ItemStatus.processing,
            ai_job_id="fake-job-id",
            updated_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await recover_stale_processing_items({"redis": _FAKE_REDIS})

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.error

    @pytest.mark.asyncio
    async def test_never_started_left_alone_when_still_queued(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        monkeypatch.setattr(worker_module, "Job", self._fake_job_class(JobStatus.queued))
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/big-batch.jpg",
            status=ItemStatus.processing,
            ai_job_id="fake-job-id",
            # Old enough that a blind time-based condemn would have killed this -
            # a huge batch can legitimately queue this long.
            updated_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await recover_stale_processing_items({"redis": _FAKE_REDIS})

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.processing

    @pytest.mark.asyncio
    async def test_never_started_left_alone_when_deferred(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        monkeypatch.setattr(worker_module, "Job", self._fake_job_class(JobStatus.deferred))
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/retry-backoff.jpg",
            status=ItemStatus.processing,
            ai_job_id="fake-job-id",
            updated_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await recover_stale_processing_items({"redis": _FAKE_REDIS})

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.processing

    @pytest.mark.asyncio
    async def test_started_past_cutoff_left_alone_when_still_in_progress(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        # The scenario a blind time-based "started" branch would have gotten
        # wrong: past the cutoff, but the worker is still genuinely on it.
        monkeypatch.setattr(worker_module, "Job", self._fake_job_class(JobStatus.in_progress))
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/slow-but-alive.jpg",
            status=ItemStatus.processing,
            ai_job_id="fake-job-id",
            ai_started_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await recover_stale_processing_items({"redis": _FAKE_REDIS})

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.processing

    @pytest.mark.asyncio
    async def test_started_past_cutoff_condemned_when_job_not_found(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        monkeypatch.setattr(worker_module, "Job", self._fake_job_class(JobStatus.not_found))
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/crashed-worker.jpg",
            status=ItemStatus.processing,
            ai_job_id="fake-job-id",
            ai_started_at=datetime.now(UTC) - timedelta(hours=2),
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await recover_stale_processing_items({"redis": _FAKE_REDIS})

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.error
