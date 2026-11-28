import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService
from app.workers.background_removal import remove_item_background_job
from app.workers.image_worker import ImageWorkerSettings
from app.workers.queues import IMAGE_QUEUE, TAGGING_QUEUE, queue_for_kind
from app.workers.rotation import rotate_item_image_job
from app.workers.worker import WorkerSettings

JOB_ID = "image-job-id"
CTX = {"job_id": JOB_ID}


def _jpeg_bytes(size: tuple[int, int] = (400, 600)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (10, 200, 30)).save(buf, format="JPEG")
    return buf.getvalue()


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
        "status": ItemStatus.processing,
        "processing_kind": "rotate",
        "ai_job_id": JOB_ID,
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


def _job_on(db_session: AsyncSession):
    return (
        patch("app.workers.rotation.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
    )


class TestQueueRouting:
    def test_image_kinds_route_to_the_image_queue(self):
        assert queue_for_kind("rotate") == IMAGE_QUEUE
        assert queue_for_kind("background_removal") == IMAGE_QUEUE

    def test_tagging_and_unknown_kinds_route_to_the_tagging_queue(self):
        assert queue_for_kind(None) == TAGGING_QUEUE
        assert queue_for_kind("tagging") == TAGGING_QUEUE

    def test_the_two_queues_are_distinct(self):
        assert IMAGE_QUEUE != TAGGING_QUEUE


class TestWorkerSplit:
    def test_image_worker_serves_the_image_queue(self):
        assert ImageWorkerSettings.queue_name == IMAGE_QUEUE

    def test_image_worker_carries_both_image_jobs(self):
        assert set(ImageWorkerSettings.functions) == {
            rotate_item_image_job,
            remove_item_background_job,
        }

    def test_tagging_worker_no_longer_runs_image_jobs(self):
        # Leaving these on arq:tagging is the starvation this split exists to
        # fix: one bulk batch blocks every AI tagging job behind it.
        assert rotate_item_image_job not in WorkerSettings.functions
        assert remove_item_background_job not in WorkerSettings.functions

    def test_image_worker_can_abort_jobs(self):
        # cancel-analysis aborts a queued rotate or background removal.
        assert ImageWorkerSettings.allow_abort_jobs is True


class TestRotateItemImageJob:
    @pytest.mark.asyncio
    async def test_success_rotates_on_disk_and_returns_the_item_to_ready(
        self, db_session: AsyncSession, test_user: User
    ):
        item = await _make_item(db_session, test_user)
        svc = ImageService()
        assert Image.open(svc.get_image_path(item.image_path)).size == (400, 600)

        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            result = await rotate_item_image_job(CTX, str(item.id), "cw")

        assert result["status"] == "success"
        assert Image.open(svc.get_image_path(item.image_path)).size == (600, 400)
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.processing_kind is None
        assert refreshed.ai_started_at is None

    @pytest.mark.asyncio
    async def test_regenerates_every_size(self, db_session: AsyncSession, test_user: User):
        item = await _make_item(db_session, test_user)
        svc = ImageService()

        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            await rotate_item_image_job(CTX, str(item.id), "cw")

        medium = Image.open(svc.get_image_path(item.medium_path)).size
        thumb = Image.open(svc.get_image_path(item.thumbnail_path)).size
        assert medium[0] > medium[1]
        assert thumb[0] > thumb[1]

    @pytest.mark.asyncio
    async def test_sets_ai_started_at_before_the_rotation_runs(
        self, db_session: AsyncSession, test_user: User
    ):
        item = await _make_item(db_session, test_user)
        seen: dict = {}
        original = ImageService.rotate_image

        def _rotate(self, image_path, direction="cw"):
            # Reads the same ORM object the job mutated (shared identity map on
            # db_session), proving the started-at write is committed before the
            # thread-offloaded rotation, not after.
            seen["ai_started_at"] = item.ai_started_at
            return original(self, image_path, direction)

        get_db, close_db = _job_on(db_session)
        with get_db, close_db, patch.object(ImageService, "rotate_image", _rotate):
            await rotate_item_image_job(CTX, str(item.id), "cw")

        assert seen["ai_started_at"] is not None

    @pytest.mark.asyncio
    async def test_failure_marks_error_and_keeps_the_kind(
        self, db_session: AsyncSession, test_user: User
    ):
        # The kind has to survive so the grid labels the failure as a rotate and
        # the retry path re-runs a rotate rather than an AI analysis.
        item = await _make_item(db_session, test_user, image_path="nobody/missing.jpg")

        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            result = await rotate_item_image_job(CTX, str(item.id), "cw")

        assert result["status"] == "error"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.error
        assert refreshed.processing_kind == "rotate"
        assert refreshed.ai_started_at is None

    @pytest.mark.asyncio
    async def test_failure_leaves_ai_bookkeeping_untouched(
        self, db_session: AsyncSession, test_user: User
    ):
        # ai_failed_at drives the AI retry cooldown, so a rotate failure must
        # not start one.
        item = await _make_item(db_session, test_user, image_path="nobody/missing.jpg")

        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            await rotate_item_image_job(CTX, str(item.id), "cw")

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.ai_failed_at is None
        assert refreshed.ai_raw_response is None

    @pytest.mark.asyncio
    async def test_missing_item_returns_an_error_without_raising(self, db_session: AsyncSession):
        get_db, close_db = _job_on(db_session)
        with get_db, close_db:
            result = await rotate_item_image_job(CTX, str(uuid4()), "cw")

        assert result["status"] == "error"


def _bg_provider():
    provider = MagicMock()
    provider.remove.side_effect = lambda img: Image.new("RGBA", img.size, (0, 0, 255, 255))
    return provider


async def _run(kind: str, db_session: AsyncSession, item_id, provider=None, **kwargs) -> dict:
    with (
        patch("app.workers.rotation.get_db_session", return_value=db_session),
        patch("app.workers.background_removal.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
        patch(
            "app.services.background_removal.get_provider", return_value=provider or _bg_provider()
        ),
    ):
        if kind == "rotate":
            return await rotate_item_image_job(CTX, str(item_id), "cw", **kwargs)
        return await remove_item_background_job(CTX, str(item_id), "#FFFFFF", **kwargs)


async def _reload(db_session: AsyncSession, item_id) -> ClothingItem:
    db_session.expire_all()
    return await _get_item(db_session, item_id)


IMAGE_KINDS = ["rotate", "background_removal"]


class TestImageJobFinish:
    @pytest.mark.parametrize("kind", IMAGE_KINDS)
    @pytest.mark.parametrize("final_status", ["ready", "error"])
    @pytest.mark.asyncio
    async def test_success_ends_on_the_status_chosen_at_queue_time(
        self, db_session: AsyncSession, test_user: User, kind, final_status
    ):
        item = await _make_item(db_session, test_user, processing_kind=kind)

        result = await _run(kind, db_session, item.id, final_status=final_status)

        assert result["status"] == "success"
        refreshed = await _reload(db_session, item.id)
        assert refreshed.status == ItemStatus(final_status)
        assert refreshed.processing_kind is None
        assert refreshed.ai_job_id is None
        assert refreshed.ai_started_at is None

    @pytest.mark.parametrize("kind", IMAGE_KINDS)
    @pytest.mark.asyncio
    async def test_a_job_queued_without_a_final_status_ends_ready(
        self, db_session: AsyncSession, test_user: User, kind
    ):
        item = await _make_item(db_session, test_user, processing_kind=kind)

        await _run(kind, db_session, item.id)

        assert (await _reload(db_session, item.id)).status == ItemStatus.ready

    @pytest.mark.parametrize("kind", IMAGE_KINDS)
    @pytest.mark.parametrize("fails", [False, True], ids=["success", "failure"])
    @pytest.mark.asyncio
    async def test_an_item_archived_during_the_job_stays_archived(
        self, db_session: AsyncSession, test_user: User, kind, fails
    ):
        overrides = {"image_path": "nobody/missing.jpg"} if fails else {}
        item = await _make_item(
            db_session,
            test_user,
            processing_kind=kind,
            is_archived=True,
            status=ItemStatus.archived,
            **overrides,
        )

        result = await _run(kind, db_session, item.id, final_status="ready")

        assert result["status"] == ("error" if fails else "success")
        refreshed = await _reload(db_session, item.id)
        assert refreshed.status == ItemStatus.archived
        assert refreshed.processing_kind is None
        assert refreshed.ai_job_id is None

    @pytest.mark.parametrize("kind", IMAGE_KINDS)
    @pytest.mark.asyncio
    async def test_failure_keeps_the_kind_and_clears_the_job(
        self, db_session: AsyncSession, test_user: User, kind
    ):
        item = await _make_item(
            db_session, test_user, processing_kind=kind, image_path="nobody/missing.jpg"
        )

        result = await _run(kind, db_session, item.id, final_status="error")

        assert result["status"] == "error"
        refreshed = await _reload(db_session, item.id)
        assert refreshed.status == ItemStatus.error
        assert refreshed.processing_kind == kind
        assert refreshed.ai_job_id is None
        assert refreshed.ai_started_at is None

    @pytest.mark.asyncio
    async def test_a_removal_cancelled_mid_job_leaves_the_row_but_records_the_backup(
        self, db_session: AsyncSession, test_user: User
    ):
        item = await _make_item(db_session, test_user, processing_kind="background_removal")
        item_id = item.id
        real_to_thread = asyncio.to_thread

        async def _work_then_cancel(fn, *args):
            out = await real_to_thread(fn, *args)
            await db_session.execute(
                update(ClothingItem)
                .where(ClothingItem.id == item_id)
                .values(status=ItemStatus.ready, ai_job_id=None, processing_kind=None)
            )
            await db_session.commit()
            return out

        with patch("app.workers.background_removal.asyncio.to_thread", _work_then_cancel):
            result = await _run("background_removal", db_session, item_id, final_status="error")

        assert result["status"] == "success"
        refreshed = await _reload(db_session, item_id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.processing_kind is None
        assert refreshed.original_image_path is not None

    @pytest.mark.parametrize("kind", IMAGE_KINDS)
    @pytest.mark.asyncio
    async def test_a_job_whose_item_was_cancelled_before_it_started_does_nothing(
        self, db_session: AsyncSession, test_user: User, kind
    ):
        item = await _make_item(
            db_session, test_user, status=ItemStatus.ready, processing_kind=None, ai_job_id=None
        )
        svc = ImageService()
        size = Image.open(svc.get_image_path(item.image_path)).size

        result = await _run(kind, db_session, item.id, final_status="ready")

        assert result["status"] == "cancelled"
        assert Image.open(svc.get_image_path(item.image_path)).size == size
        refreshed = await _reload(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.ai_started_at is None
        assert refreshed.original_image_path is None
