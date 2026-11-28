from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.schemas.item import RemoveBackgroundRequest
from app.services.image_service import ImageService
from app.workers.queues import IMAGE_QUEUE


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
        "status": ItemStatus.ready,
    }
    defaults.update(overrides)
    item = ClothingItem(**defaults)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _get_item(db_session: AsyncSession, item_id) -> ClothingItem:
    db_session.expire_all()
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return result.scalar_one()


def _redis(job_result=True) -> AsyncMock:
    redis = AsyncMock()
    if job_result:
        redis.enqueue_job.side_effect = lambda *args, **kwargs: MagicMock(job_id=kwargs["_job_id"])
    else:
        redis.enqueue_job.return_value = None
    return redis


async def _post(client: AsyncClient, headers, item_id, redis=None, **pool_kwargs):
    pool = AsyncMock(return_value=redis or _redis(), **pool_kwargs)
    provider = MagicMock()
    with (
        patch("app.api.items.create_pool", pool),
        patch("app.services.background_removal.get_provider", provider),
    ):
        response = await client.post(
            f"/api/v1/items/{item_id}/remove-background", json={}, headers=headers
        )
    provider.assert_not_called()
    return response


class TestRemoveBackgroundRequest:
    def test_default_white(self):
        req = RemoveBackgroundRequest()
        assert req.bg_color == "#FFFFFF"

    def test_valid_hex(self):
        req = RemoveBackgroundRequest(bg_color="#FF0000")
        assert req.bg_color == "#FF0000"

    def test_lowercase_hex(self):
        req = RemoveBackgroundRequest(bg_color="#aabbcc")
        assert req.bg_color == "#aabbcc"

    def test_rejects_short_hex(self):
        with pytest.raises(ValidationError):
            RemoveBackgroundRequest(bg_color="#FFF")

    def test_rejects_no_hash(self):
        with pytest.raises(ValidationError):
            RemoveBackgroundRequest(bg_color="FFFFFF")

    def test_rejects_invalid_chars(self):
        with pytest.raises(ValidationError):
            RemoveBackgroundRequest(bg_color="#GGGGGG")


class TestRemoveBackgroundEndpoint:
    @pytest.mark.asyncio
    async def test_item_not_found(self, client: AsyncClient, test_user, auth_headers):
        response = await _post(client, auth_headers, uuid4())
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_item_no_image(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        response = await _post(client, auth_headers, item.id)
        assert response.status_code == 400
        assert "no image" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_unauthenticated(self, client: AsyncClient):
        response = await client.post(
            f"/api/v1/items/{uuid4()}/remove-background",
            json={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_queues_the_job_on_the_image_worker(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user)
        item_id = item.id
        redis = _redis()

        response = await _post(client, auth_headers, item_id, redis)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "queued"
        redis.enqueue_job.assert_awaited_once_with(
            "remove_item_background_job",
            str(item_id),
            "#FFFFFF",
            _job_id=body["job_id"],
            _queue_name=IMAGE_QUEUE,
            final_status="ready",
        )
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.status == ItemStatus.processing
        assert refreshed.processing_kind == "background_removal"
        assert refreshed.ai_job_id == body["job_id"]
        assert refreshed.ai_started_at is None

    @pytest.mark.asyncio
    async def test_forwards_the_requested_colour(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user)
        redis = _redis()

        with patch("app.api.items.create_pool", AsyncMock(return_value=redis)):
            response = await client.post(
                f"/api/v1/items/{item.id}/remove-background",
                json={"bg_color": "#000000"},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert redis.enqueue_job.await_args.args[2] == "#000000"

    @pytest.mark.parametrize(
        "state",
        [
            {"ai_job_id": "live-removal", "processing_kind": "background_removal"},
            {"ai_job_id": "live-tagging", "processing_kind": None},
            {"ai_job_id": None, "processing_kind": None},
        ],
        ids=["live image job", "pending tagging", "orphaned tagging"],
    )
    @pytest.mark.asyncio
    async def test_busy_items_are_refused(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, state
    ):
        item = await _make_item(db_session, test_user, status=ItemStatus.processing, **state)
        item_id = item.id
        redis = _redis()

        response = await _post(client, auth_headers, item_id, redis)

        assert response.status_code == 409
        assert response.json()["error_code"] == "ITEM_BUSY"
        redis.enqueue_job.assert_not_awaited()
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.status == ItemStatus.processing
        assert refreshed.ai_job_id == state["ai_job_id"]
        assert refreshed.processing_kind == state["processing_kind"]

    @pytest.mark.asyncio
    async def test_a_click_after_the_claim_is_committed_is_refused(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user)
        item_id = item.id
        second: dict = {}

        async def enqueue(*args, **kwargs):
            second["response"] = await client.post(
                f"/api/v1/items/{item_id}/remove-background", json={}, headers=auth_headers
            )
            return MagicMock(job_id=kwargs["_job_id"])

        redis = AsyncMock()
        redis.enqueue_job.side_effect = enqueue

        first = await _post(client, auth_headers, item_id, redis)

        assert first.status_code == 200
        assert second["response"].status_code == 409
        assert second["response"].json()["error_code"] == "ITEM_BUSY"
        assert redis.enqueue_job.await_count == 1
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.ai_job_id == first.json()["job_id"]

    @pytest.mark.parametrize("status", [ItemStatus.archived, ItemStatus.error])
    @pytest.mark.asyncio
    async def test_archived_items_are_refused(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, status
    ):
        item = await _make_item(db_session, test_user, status=status, is_archived=True)
        item_id = item.id
        redis = _redis()

        response = await _post(client, auth_headers, item_id, redis)

        assert response.status_code == 409
        assert response.json()["error_code"] == "ITEM_ARCHIVED"
        redis.enqueue_job.assert_not_awaited()
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.status == status
        assert refreshed.processing_kind is None

    @pytest.mark.parametrize(
        ("state", "final_status"),
        [
            ({"status": ItemStatus.processing, "processing_kind": "rotate"}, "ready"),
            (
                {"status": ItemStatus.processing, "processing_kind": "background_removal"},
                "ready",
            ),
            ({"status": ItemStatus.error, "processing_kind": "background_removal"}, "ready"),
            ({"status": ItemStatus.error, "processing_kind": "rotate"}, "ready"),
            ({"status": ItemStatus.error, "processing_kind": None}, "error"),
        ],
        ids=[
            "orphaned rotate",
            "orphaned removal",
            "failed removal",
            "failed rotate",
            "failed tagging",
        ],
    )
    @pytest.mark.asyncio
    async def test_queues_again_with_the_status_to_finish_on(
        self,
        client: AsyncClient,
        test_user,
        auth_headers,
        db_session: AsyncSession,
        state,
        final_status,
    ):
        item = await _make_item(db_session, test_user, ai_job_id=None, **state)
        item_id = item.id
        redis = _redis()

        response = await _post(client, auth_headers, item_id, redis)

        assert response.status_code == 200
        assert redis.enqueue_job.await_args.kwargs["final_status"] == final_status
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.status == ItemStatus.processing
        assert refreshed.processing_kind == "background_removal"

    @pytest.mark.parametrize(
        "state",
        [
            {"status": ItemStatus.ready, "processing_kind": None},
            {"status": ItemStatus.error, "processing_kind": None},
            {"status": ItemStatus.error, "processing_kind": "background_removal"},
            {"status": ItemStatus.processing, "processing_kind": "rotate"},
        ],
        ids=["ready", "failed tagging", "failed removal", "orphaned rotate"],
    )
    @pytest.mark.parametrize(
        "pool_kwargs",
        [{"side_effect": OSError("no redis")}, {}],
        ids=["redis down", "enqueue refused"],
    )
    @pytest.mark.asyncio
    async def test_a_failed_enqueue_puts_the_item_back(
        self,
        client: AsyncClient,
        test_user,
        auth_headers,
        db_session: AsyncSession,
        state,
        pool_kwargs,
    ):
        item = await _make_item(db_session, test_user, ai_job_id=None, **state)
        item_id = item.id

        response = await _post(client, auth_headers, item_id, _redis(False), **pool_kwargs)

        assert response.status_code == 500
        assert response.json()["error_code"] == "JOB_QUEUE_UNAVAILABLE"
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.status == state["status"]
        assert refreshed.processing_kind == state["processing_kind"]
        assert refreshed.ai_job_id is None

    @pytest.mark.asyncio
    async def test_a_failed_enqueue_keeps_an_item_archived_meanwhile(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user)
        item_id = item.id

        async def enqueue(*args, **kwargs):
            row = await _get_item(db_session, item_id)
            row.is_archived = True
            await db_session.commit()
            return None

        redis = AsyncMock()
        redis.enqueue_job.side_effect = enqueue

        response = await _post(client, auth_headers, item_id, redis)

        assert response.status_code == 500
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.status == ItemStatus.archived
        assert refreshed.processing_kind is None

    @pytest.mark.asyncio
    async def test_another_users_item_is_not_found(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        other_id = uuid4()
        other = User(
            id=other_id,
            external_id=f"other-{other_id}",
            email=f"other-{other_id}@example.com",
            display_name="Other",
            timezone="UTC",
            is_active=True,
            onboarding_completed=False,
        )
        db_session.add(other)
        await db_session.commit()
        item = await _make_item(db_session, other)
        item_id = item.id

        response = await _post(client, auth_headers, item_id)

        assert response.status_code == 404
        refreshed = await _get_item(db_session, item_id)
        assert refreshed.status == ItemStatus.ready


class TestHealthFeatures:
    @pytest.mark.asyncio
    async def test_features_endpoint(self, client: AsyncClient):
        response = await client.get("/api/v1/health/features")
        assert response.status_code == 200
        data = response.json()
        assert "background_removal" in data
        assert isinstance(data["background_removal"], bool)
