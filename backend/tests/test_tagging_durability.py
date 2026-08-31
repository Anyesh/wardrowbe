import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from arq import Retry
from httpx import AsyncClient
from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services import ai_service as ai_service_module
from app.services.ai_service import AIService, ClothingTags
from app.workers import tagging as tagging_module
from app.workers.tagging import tag_item_image
from app.workers.worker import WorkerSettings, stale_processing_cutoff_seconds


def _image_bytes(i: int = 0) -> bytes:
    # phash keys off low-frequency DCT structure, so noise and fine detail all
    # collapse to one hash. Encode the index as a coarse block grid instead so
    # each generated image gets a distinct hash and clears duplicate detection.
    img = Image.new("RGB", (128, 128), (15, 15, 20))
    d = ImageDraw.Draw(img)
    for bit in range(16):
        if (i >> bit) & 1:
            cx, cy = (bit % 4) * 32, (bit // 4) * 32
            d.rectangle([cx, cy, cx + 30, cy + 30], fill=(235, 235, 240))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class _OrderRecorder:
    def __init__(self):
        self.events: list[str] = []

    def redis(self):
        async def enqueue_job(*args, **kwargs):
            self.events.append("enqueue")
            job = AsyncMock()
            job.job_id = str(uuid4())
            return job

        pool = AsyncMock()
        pool.enqueue_job.side_effect = enqueue_job
        return pool


def _patch_commit(recorder: _OrderRecorder):
    original = AsyncSession.commit

    async def recording_commit(self):
        recorder.events.append("commit")
        return await original(self)

    return patch.object(AsyncSession, "commit", recording_commit)


class TestEnqueueHappensAfterCommit:
    """The worker runs in a separate process against its own connection, so a job
    enqueued before the row is committed can dequeue against an invisible row."""

    @pytest.mark.asyncio
    async def test_single_upload_commits_before_enqueue(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        rec = _OrderRecorder()
        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as pool,
            _patch_commit(rec),
        ):
            pool.return_value = rec.redis()
            resp = await client.post(
                "/api/v1/items",
                files={"image": ("a.jpg", _image_bytes(1), "image/jpeg")},
                headers=auth_headers,
            )

        assert resp.status_code == 201
        assert "enqueue" in rec.events
        assert rec.events.index("commit") < rec.events.index("enqueue"), rec.events

    @pytest.mark.asyncio
    async def test_bulk_upload_commits_before_every_enqueue(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        rec = _OrderRecorder()
        files = [("images", (f"i{i}.jpg", _image_bytes(i + 2), "image/jpeg")) for i in range(3)]
        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as pool,
            _patch_commit(rec),
        ):
            pool.return_value = rec.redis()
            resp = await client.post("/api/v1/items/bulk", files=files, headers=auth_headers)

        assert resp.status_code == 201
        assert resp.json()["successful"] == 3
        assert rec.events.count("enqueue") == 3
        for idx, event in enumerate(rec.events):
            if event == "enqueue":
                assert "commit" in rec.events[:idx], f"enqueue at {idx} with no prior commit"


class TestWorkerFailsLoudly:
    @pytest.mark.asyncio
    async def test_raises_when_item_not_visible(self, db_session: AsyncSession):
        """A missing row means the producer's transaction has not landed yet.
        Raising lets arq retry; returning would silently strand the item."""
        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch.object(AIService, "analyze_image", new_callable=AsyncMock) as analyze,
        ):
            analyze.return_value = type(
                "T", (), {"type": "top", "primary_color": "blue", "raw_response": None}
            )()
            # Surfaced as Retry so arq reschedules: arq only reschedules on
            # Retry, a plain raise would fail the job outright.
            with pytest.raises(Retry):
                await tag_item_image({"job_try": 1}, str(uuid4()), __file__)

    @pytest.mark.asyncio
    async def test_reraises_ai_errors_so_arq_can_retry(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="t/x.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch.object(AIService, "analyze_image", new_callable=AsyncMock) as analyze,
        ):
            analyze.side_effect = RuntimeError("upstream 500")
            with pytest.raises(Retry):
                await tag_item_image({"job_try": 1}, str(item.id), __file__)

        # Still processing: arq has retries left, so the item must not be
        # condemned until the final attempt is spent.
        await db_session.refresh(item)
        assert item.status == ItemStatus.processing

    @pytest.mark.asyncio
    async def test_marks_error_on_final_attempt(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="t/y.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch.object(AIService, "analyze_image", new_callable=AsyncMock) as analyze,
        ):
            analyze.side_effect = RuntimeError("upstream 500")
            with pytest.raises(RuntimeError):
                await tag_item_image({"job_try": WorkerSettings.max_tries}, str(item.id), __file__)

        await db_session.refresh(item)
        assert item.status == ItemStatus.error
        assert "upstream 500" in item.ai_raw_response["error"]


class TestAiStartedAtLifecycle:
    @pytest.mark.asyncio
    async def test_sets_ai_started_at_on_attempt(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="t/started.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch.object(AIService, "analyze_image", new_callable=AsyncMock) as analyze,
        ):
            analyze.return_value = ClothingTags(
                type="shirt", primary_color="blue", colors=["blue"], confidence=0.9
            )
            await tag_item_image({"job_try": 1}, str(item.id), __file__)

        await db_session.refresh(item)
        assert item.ai_started_at is not None

    @pytest.mark.asyncio
    async def test_clears_ai_started_at_before_non_final_retry(
        self, db_session: AsyncSession, test_user
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="t/retry.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch.object(AIService, "analyze_image", new_callable=AsyncMock) as analyze,
        ):
            analyze.side_effect = RuntimeError("upstream 500")
            with pytest.raises(Retry):
                await tag_item_image({"job_try": 1}, str(item.id), __file__)

        await db_session.refresh(item)
        assert item.status == ItemStatus.processing
        assert item.ai_started_at is None

    @pytest.mark.asyncio
    async def test_cancelled_error_clears_marker_not_status(
        self, db_session: AsyncSession, test_user
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="t/cancel.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch.object(AIService, "analyze_image", new_callable=AsyncMock) as analyze,
        ):
            analyze.side_effect = asyncio.CancelledError()
            with pytest.raises(asyncio.CancelledError):
                await tag_item_image({"job_try": 1}, str(item.id), __file__)

        await db_session.refresh(item)
        # Not `error` - cancel_item_analysis owns the terminal state for a
        # cancelled job via its own guarded update; this must not race it.
        assert item.status == ItemStatus.processing
        assert item.ai_started_at is None

    @pytest.mark.asyncio
    async def test_hung_ai_call_trips_budget_and_retries_normally(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="t/hung.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        monkeypatch.setattr(tagging_module, "_tagging_call_budget", lambda ai_service: 0.05)

        async def _hang(self, path):
            await asyncio.sleep(10)

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch.object(AIService, "analyze_image", _hang),
        ):
            with pytest.raises(Retry):
                await tag_item_image({"job_try": 1}, str(item.id), __file__)

        await db_session.refresh(item)
        # A budget timeout goes through the normal retry path - unlike arq's own
        # job_timeout kill, which does not retry at all.
        assert item.status == ItemStatus.processing
        assert item.ai_started_at is None


class TestStaleCutoffCannotCondemnLiveJobs:
    def test_cutoff_exceeds_job_timeout(self):
        assert stale_processing_cutoff_seconds() > WorkerSettings.job_timeout


class TestRetryBackoff:
    @pytest.mark.asyncio
    async def test_sleeps_between_failed_attempts(self):
        service = AIService()
        slept: list[float] = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        class _Resp:
            status_code = 500

            def raise_for_status(self):
                raise httpx.HTTPStatusError("boom", request=None, response=self)

        with (
            patch("app.services.ai_service.asyncio.sleep", side_effect=fake_sleep),
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post,
        ):
            post.return_value = _Resp()
            content, err, _ = await service._call_with_fallback([], "tags")

        assert content is None
        assert err is not None
        assert slept, "expected backoff between retries, got none"
        assert slept == sorted(slept), f"backoff should not shrink: {slept}"


class TestFailureReasonReachesTheApi:
    @pytest.mark.asyncio
    async def test_error_reason_exposed_on_item_response(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="t/z.jpg",
            status=ItemStatus.error,
            ai_raw_response={"error": "AI endpoint returned 404"},
        )
        db_session.add(item)
        await db_session.commit()

        resp = await client.get(f"/api/v1/items/{item.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ai_error"] == "AI endpoint returned 404"


class TestTaggingQueueProgress:
    @pytest.mark.asyncio
    async def test_reports_counts_across_whole_wardrobe(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        for i in range(3):
            db_session.add(
                ClothingItem(
                    user_id=test_user.id,
                    type="unknown",
                    image_path=f"t/p{i}.jpg",
                    status=ItemStatus.processing,
                )
            )
        db_session.add(
            ClothingItem(
                user_id=test_user.id,
                type="shirt",
                image_path="t/r.jpg",
                status=ItemStatus.ready,
            )
        )
        db_session.add(
            ClothingItem(
                user_id=test_user.id,
                type="shirt",
                image_path="t/e.jpg",
                status=ItemStatus.error,
            )
        )
        await db_session.commit()

        resp = await client.get("/api/v1/items/tagging-progress", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["processing"] == 3
        assert body["failed"] == 1
        assert body["total"] == 5
        assert body["completed"] == 1
        # None of the processing items ever started, so they're all queued.
        assert body["queued"] == 3
        assert body["analyzing"] == 0

    @pytest.mark.asyncio
    async def test_splits_queued_from_analyzing(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        from datetime import UTC, datetime

        db_session.add(
            ClothingItem(
                user_id=test_user.id,
                type="unknown",
                image_path="t/queued.jpg",
                status=ItemStatus.processing,
            )
        )
        db_session.add(
            ClothingItem(
                user_id=test_user.id,
                type="unknown",
                image_path="t/analyzing.jpg",
                status=ItemStatus.processing,
                ai_started_at=datetime.now(UTC),
            )
        )
        await db_session.commit()

        resp = await client.get("/api/v1/items/tagging-progress", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["processing"] == 2
        assert body["queued"] == 1
        assert body["analyzing"] == 1


class TestTaggingConcurrencySetting:
    def test_ai_tagging_concurrency_setting_is_respected(self):
        from app.config import Settings

        assert Settings(ai_tagging_concurrency=2).ai_tagging_concurrency == 2

    def test_ai_tagging_concurrency_requires_at_least_one(self):
        from pydantic import ValidationError

        from app.config import Settings

        with pytest.raises(ValidationError):
            Settings(ai_tagging_concurrency=0)

    def test_worker_max_jobs_matches_setting(self):
        from app.config import get_settings

        # Regression guard against the concurrency ceiling silently reverting to
        # a hardcoded literal - both sides read the same cached settings at
        # import time, so this isn't a behavioral proof, just a tripwire.
        assert WorkerSettings.max_jobs == get_settings().ai_tagging_concurrency

    @staticmethod
    def _reset_request_semaphore() -> None:
        ai_service_module._ai_request_semaphore = None
        ai_service_module._ai_request_semaphore_size = None

    class _OkResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrent_ai_requests(self):
        # ai_tagging_concurrency only bounds arq's job pool, not real concurrent
        # AI HTTP calls (there is no semaphore anywhere else) - this proves the
        # semaphore in ai_service.py is what actually caps concurrency.
        self._reset_request_semaphore()
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_concurrent_requests": 2})

        in_flight = 0
        max_in_flight = 0

        async def fake_post(*args, **kwargs):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.05)
            in_flight -= 1
            return self._OkResponse()

        with patch("httpx.AsyncClient.post", side_effect=fake_post):
            await asyncio.gather(*[service._call_with_fallback([], "tags") for _ in range(6)])

        assert max_in_flight == 2

    @pytest.mark.asyncio
    async def test_semaphore_avoids_client_side_timeouts_against_a_serial_backend(self):
        # Simulates a single-threaded local Ollama: only one request is actually
        # processed at a time. Without the semaphore, every caller opens its
        # request (and starts its own ai_timeout clock) at once, so whoever
        # ends up queued behind another request in the backend's own serial
        # processing blows past ai_timeout and errors - the retry-into-the-
        # same-overload pileup from the bug report. With the semaphore capping
        # real concurrency to 1, callers wait their turn before even starting
        # their request, so no request's timeout clock starts before the
        # backend is actually free to serve it.
        backend_lock = asyncio.Lock()
        backend_delay = 0.1
        ai_timeout = 0.15

        def make_fake_post(client_timeout: float):
            async def fake_post(*args, **kwargs):
                start = asyncio.get_event_loop().time()
                async with backend_lock:
                    waited = asyncio.get_event_loop().time() - start
                    if waited > client_timeout:
                        raise httpx.ReadTimeout("simulated client timeout", request=None)
                    await asyncio.sleep(backend_delay)
                return self._OkResponse()

            return fake_post

        async def run(max_concurrent: int) -> list[Exception | None]:
            self._reset_request_semaphore()
            service = AIService()
            service.settings = service.settings.model_copy(
                update={
                    "ai_max_concurrent_requests": max_concurrent,
                    "ai_timeout": ai_timeout,
                    "ai_max_retries": 1,
                }
            )
            with patch("httpx.AsyncClient.post", side_effect=make_fake_post(ai_timeout)):
                results = await asyncio.gather(
                    *[service._call_with_fallback([], "tags") for _ in range(3)]
                )
            return [err for _content, err, _logprobs in results]

        unbounded_errors = await run(max_concurrent=3)
        bounded_errors = await run(max_concurrent=1)

        assert any(err is not None for err in unbounded_errors), (
            "expected the unthrottled run to reproduce the queued-then-timeout pileup"
        )
        assert all(err is None for err in bounded_errors)
