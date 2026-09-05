from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import items as items_api
from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService
from app.services.item_service import ItemService


def _jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (60, 90), (10, 200, 30)).save(buf, format="JPEG")
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
        "status": ItemStatus.ready,
    }
    defaults.update(overrides)
    item = ClothingItem(**defaults)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest.fixture
def cap_of_two(monkeypatch):
    monkeypatch.setattr(items_api.settings, "max_bulk_action_count", 2)
    return 2


@pytest.fixture
def fake_redis():
    with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
        redis = AsyncMock()
        redis.enqueue_job.return_value.job_id = "job-id"
        mock_create_pool.return_value = redis
        yield redis


class TestGetIdsByFilterCursor:
    @pytest.mark.asyncio
    async def test_orders_by_id_so_a_walk_is_stable(
        self, db_session: AsyncSession, test_user: User
    ):
        for _ in range(5):
            await _make_item(db_session, test_user)
        service = ItemService(db_session)

        ids = await service.get_ids_by_filter(user_id=test_user.id)

        assert ids == sorted(ids)

    @pytest.mark.asyncio
    async def test_limit_truncates_the_result(self, db_session: AsyncSession, test_user: User):
        for _ in range(5):
            await _make_item(db_session, test_user)
        service = ItemService(db_session)

        assert len(await service.get_ids_by_filter(user_id=test_user.id, limit=3)) == 3

    @pytest.mark.asyncio
    async def test_after_id_resumes_past_the_cursor(
        self, db_session: AsyncSession, test_user: User
    ):
        for _ in range(5):
            await _make_item(db_session, test_user)
        service = ItemService(db_session)
        every_id = await service.get_ids_by_filter(user_id=test_user.id)

        resumed = await service.get_ids_by_filter(user_id=test_user.id, after_id=every_id[1])

        assert resumed == every_id[2:]

    @pytest.mark.asyncio
    async def test_walking_in_batches_covers_every_item_exactly_once(
        self, db_session: AsyncSession, test_user: User
    ):
        for _ in range(7):
            await _make_item(db_session, test_user)
        service = ItemService(db_session)

        seen: list = []
        cursor = None
        while True:
            batch = await service.get_ids_by_filter(user_id=test_user.id, after_id=cursor, limit=3)
            if not batch:
                break
            seen.extend(batch)
            cursor = batch[-1]

        assert len(seen) == 7
        assert len(set(seen)) == 7


class TestExplicitIdListIsCapped:
    @pytest.mark.asyncio
    async def test_oversized_explicit_list_is_rejected_with_the_limit(
        self, client: AsyncClient, auth_headers, cap_of_two
    ):
        response = await client.post(
            "/api/v1/items/bulk/delete",
            headers=auth_headers,
            json={"item_ids": [str(uuid4()) for _ in range(3)]},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Maximum 2 items per bulk action"

    @pytest.mark.asyncio
    async def test_a_list_at_the_cap_is_accepted(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user, cap_of_two
    ):
        first = await _make_item(db_session, test_user)
        second = await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/delete",
            headers=auth_headers,
            json={"item_ids": [str(first.id), str(second.id)]},
        )

        assert response.status_code == 200
        assert response.json()["deleted"] == 2

    @pytest.mark.parametrize(
        "path,payload",
        [
            ("delete", {}),
            ("analyze", {}),
            ("cancel-analysis", {}),
            ("rotate", {"direction": "cw"}),
            ("remove-background", {}),
        ],
    )
    @pytest.mark.asyncio
    async def test_every_bulk_endpoint_enforces_the_cap(
        self, client: AsyncClient, auth_headers, cap_of_two, path, payload
    ):
        response = await client.post(
            f"/api/v1/items/bulk/{path}",
            headers=auth_headers,
            json={"item_ids": [str(uuid4()) for _ in range(3)], **payload},
        )

        assert response.status_code == 400
        assert "Maximum 2 items per bulk action" in response.json()["detail"]


class TestSelectAllIsWalkedInBatches:
    @pytest.mark.asyncio
    async def test_select_all_stops_at_the_cap_and_reports_a_cursor(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user, cap_of_two
    ):
        for _ in range(5):
            await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/delete",
            headers=auth_headers,
            json={"select_all": True},
        )

        body = response.json()
        assert response.status_code == 200
        assert body["deleted"] == 2
        assert body["has_more"] is True
        assert body["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_following_the_cursor_deletes_every_item(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user, cap_of_two
    ):
        for _ in range(5):
            await _make_item(db_session, test_user)

        deleted = 0
        cursor = None
        for _ in range(10):
            response = await client.post(
                "/api/v1/items/bulk/delete",
                headers=auth_headers,
                json={"select_all": True, "after_id": cursor},
            )
            body = response.json()
            deleted += body["deleted"]
            if not body["has_more"]:
                break
            cursor = body["next_cursor"]

        assert deleted == 5
        remaining = await db_session.execute(
            select(ClothingItem).where(ClothingItem.user_id == test_user.id)
        )
        assert remaining.scalars().all() == []

    @pytest.mark.asyncio
    async def test_last_batch_reports_no_cursor(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user, cap_of_two
    ):
        await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/delete",
            headers=auth_headers,
            json={"select_all": True},
        )

        body = response.json()
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_rotate_select_all_only_queues_up_to_the_cap(
        self,
        client: AsyncClient,
        auth_headers,
        db_session: AsyncSession,
        test_user,
        cap_of_two,
        fake_redis,
    ):
        for _ in range(5):
            await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/rotate",
            headers=auth_headers,
            json={"select_all": True, "direction": "cw"},
        )

        body = response.json()
        assert body["queued"] == 2
        assert body["has_more"] is True
        assert fake_redis.enqueue_job.await_count == 2

    @pytest.mark.asyncio
    async def test_remove_background_select_all_only_queues_up_to_the_cap(
        self,
        client: AsyncClient,
        auth_headers,
        db_session: AsyncSession,
        test_user,
        cap_of_two,
        fake_redis,
    ):
        for _ in range(5):
            await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/remove-background",
            headers=auth_headers,
            json={"select_all": True},
        )

        body = response.json()
        assert body["queued"] == 2
        assert body["has_more"] is True
        assert fake_redis.enqueue_job.await_count == 2

    @pytest.mark.asyncio
    async def test_explicit_ids_never_report_a_cursor(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user, cap_of_two
    ):
        item = await _make_item(db_session, test_user)

        response = await client.post(
            "/api/v1/items/bulk/delete",
            headers=auth_headers,
            json={"item_ids": [str(item.id)]},
        )

        body = response.json()
        assert body["has_more"] is False
        assert body["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_cursor_walk_respects_excluded_ids(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user, cap_of_two
    ):
        items = [await _make_item(db_session, test_user) for _ in range(5)]
        spared = sorted(items, key=lambda i: i.id)[0]

        deleted = 0
        cursor = None
        for _ in range(10):
            response = await client.post(
                "/api/v1/items/bulk/delete",
                headers=auth_headers,
                json={
                    "select_all": True,
                    "after_id": cursor,
                    "excluded_ids": [str(spared.id)],
                },
            )
            body = response.json()
            deleted += body["deleted"]
            if not body["has_more"]:
                break
            cursor = body["next_cursor"]

        assert deleted == 4
        survivors = await db_session.execute(
            select(ClothingItem.id).where(ClothingItem.user_id == test_user.id)
        )
        assert survivors.scalars().all() == [spared.id]
