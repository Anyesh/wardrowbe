import asyncio
from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.item import ClothingItem, ItemStatus
from app.schemas.item import ItemCreate, ItemFilter
from app.services.item_service import ItemService
from app.workers.tagging import update_item_status_to_error


def _make_test_image_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), (100, 150, 200)).save(buf, format="JPEG")
    return buf.getvalue()


class TestItemList:
    """Tests for item listing endpoint."""

    @pytest.mark.asyncio
    async def test_list_items_empty(self, client: AsyncClient, test_user, auth_headers):
        """Test listing items when none exist."""
        response = await client.get("/api/v1/items", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_items_with_items(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        """Test listing items when items exist."""
        # Create some test items
        for i in range(3):
            item = ClothingItem(
                user_id=test_user.id,
                type="shirt",
                image_path=f"test/{i}.jpg",
                status=ItemStatus.ready,
            )
            db_session.add(item)
        await db_session.commit()

        response = await client.get("/api/v1/items", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_list_items_pagination(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        """Test item listing pagination."""
        # Create 25 test items
        for i in range(25):
            item = ClothingItem(
                user_id=test_user.id,
                type="shirt",
                image_path=f"test/{i}.jpg",
                status=ItemStatus.ready,
            )
            db_session.add(item)
        await db_session.commit()

        # First page
        response = await client.get(
            "/api/v1/items", params={"page": 1, "page_size": 10}, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 25
        assert data["has_more"] is True

        # Last page
        response = await client.get(
            "/api/v1/items", params={"page": 3, "page_size": 10}, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_items_filter_by_type(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        """Test filtering items by type."""
        # Create items of different types
        for item_type in ["shirt", "shirt", "pants"]:
            item = ClothingItem(
                user_id=test_user.id,
                type=item_type,
                image_path=f"test/{uuid4()}.jpg",
                status=ItemStatus.ready,
            )
            db_session.add(item)
        await db_session.commit()

        response = await client.get("/api/v1/items", params={"type": "shirt"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert all(item["type"] == "shirt" for item in data["items"])


class TestItemCRUD:
    """Tests for item CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_item_not_found(self, client: AsyncClient, test_user, auth_headers):
        """Test getting a non-existent item."""
        response = await client.get(f"/api/v1/items/{uuid4()}", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_item_success(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        """Test getting an existing item."""
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            name="Test Shirt",
            image_path="test/item.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        response = await client.get(f"/api/v1/items/{item.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(item.id)
        assert data["name"] == "Test Shirt"

    @pytest.mark.asyncio
    async def test_update_item(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        """Test updating an item."""
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            name="Old Name",
            image_path="test/item.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"name": "New Name", "brand": "Test Brand"},
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Unexpected error: {response.json()}"
        data = response.json()
        assert data["name"] == "New Name"
        assert data["brand"] == "Test Brand"

    @pytest.mark.asyncio
    async def test_update_item_not_found(self, client: AsyncClient, test_user, auth_headers):
        """Test updating a non-existent item."""
        response = await client.patch(
            f"/api/v1/items/{uuid4()}",
            json={"name": "New Name"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_item(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        """Test deleting an item."""
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/item.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        item_id = item.id

        response = await client.delete(f"/api/v1/items/{item_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify item is deleted
        response = await client.get(f"/api/v1/items/{item_id}", headers=auth_headers)
        assert response.status_code == 404


class TestItemArchive:
    """Tests for item archive/restore functionality."""

    @pytest.mark.asyncio
    async def test_archive_item(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        """Test archiving an item."""
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/item.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        response = await client.post(
            f"/api/v1/items/{item.id}/archive",
            json={"reason": "No longer fits"},
            headers=auth_headers,
        )
        assert response.status_code == 200, f"Unexpected error: {response.json()}"
        data = response.json()
        assert data["is_archived"] is True
        assert data["archive_reason"] == "No longer fits"

    @pytest.mark.asyncio
    async def test_restore_item(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        """Test restoring an archived item."""
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/item.jpg",
            status=ItemStatus.archived,
            is_archived=True,
            archive_reason="Testing",
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        response = await client.post(f"/api/v1/items/{item.id}/restore", headers=auth_headers)
        assert response.status_code == 200, f"Unexpected error: {response.json()}"
        data = response.json()
        assert data["is_archived"] is False
        assert data["archive_reason"] is None


class TestItemService:
    """Tests for ItemService business logic."""

    @pytest.mark.asyncio
    async def test_get_ready_item_count(self, db_session: AsyncSession, test_user):
        ready_item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path=f"test/{uuid4()}.jpg",
            status=ItemStatus.ready,
        )
        processing_item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path=f"test/{uuid4()}.jpg",
            status=ItemStatus.processing,
        )
        archived_item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path=f"test/{uuid4()}.jpg",
            status=ItemStatus.ready,
            is_archived=True,
        )

        db_session.add_all([ready_item, processing_item, archived_item])
        await db_session.commit()

        service = ItemService(db_session)
        assert await service.get_ready_item_count(test_user.id) == 1

    @pytest.mark.asyncio
    async def test_get_item_types(self, db_session: AsyncSession, test_user):
        """Test getting item type counts."""
        # Create items of different types
        types = ["shirt", "shirt", "pants", "jacket", "jacket", "jacket"]
        for item_type in types:
            item = ClothingItem(
                user_id=test_user.id,
                type=item_type,
                image_path=f"test/{uuid4()}.jpg",
                status=ItemStatus.ready,
            )
            db_session.add(item)
        await db_session.commit()

        service = ItemService(db_session)
        type_counts = await service.get_item_types(test_user.id)

        # Should be ordered by count descending
        assert type_counts[0]["type"] == "jacket"
        assert type_counts[0]["count"] == 3
        assert type_counts[1]["type"] == "shirt"
        assert type_counts[1]["count"] == 2

    @pytest.mark.asyncio
    async def test_get_color_distribution(self, db_session: AsyncSession, test_user):
        """Test getting color distribution."""
        # Create items with colors
        items_data = [
            {"colors": ["black", "white"]},
            {"colors": ["black", "navy"]},
            {"colors": ["black"]},
        ]
        for data in items_data:
            item = ClothingItem(
                user_id=test_user.id,
                type="shirt",
                image_path=f"test/{uuid4()}.jpg",
                colors=data["colors"],
                status=ItemStatus.ready,
            )
            db_session.add(item)
        await db_session.commit()

        service = ItemService(db_session)
        color_dist = await service.get_color_distribution(test_user.id)

        # Black should be most common
        assert color_dist[0]["color"] == "black"
        assert color_dist[0]["count"] == 3

    @pytest.mark.asyncio
    async def test_get_list_orders_ties_deterministically(
        self, db_session: AsyncSession, test_user
    ):
        tied_created_at = datetime(2026, 1, 1, tzinfo=UTC)
        items = [
            ClothingItem(
                user_id=test_user.id,
                type="shirt",
                image_path=f"test/{uuid4()}.jpg",
                status=ItemStatus.ready,
                created_at=tied_created_at,
            )
            for _ in range(5)
        ]
        db_session.add_all(items)
        await db_session.commit()

        service = ItemService(db_session)
        filters = ItemFilter(sort_by="created_at", sort_order="desc")

        first_ids = [item.id for item in (await service.get_list(test_user.id, filters))[0]]
        second_ids = [item.id for item in (await service.get_list(test_user.id, filters))[0]]

        assert first_ids == second_ids == sorted(first_ids)


class TestBulkCreateUploadKeyIdempotency:
    """upload_key lets a retried/duplicated bulk-upload chunk from the durable
    frontend queue be replayed safely - covers both the fast-path pre-check and
    the DB-constraint conflict path a race would actually hit."""

    @pytest.mark.asyncio
    async def test_first_upload_with_key_creates_item(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                data={"upload_keys": "key-1"},
                headers=auth_headers,
            )

        assert response.status_code == 201
        result = response.json()["results"][0]
        assert result["success"] is True
        assert result["duplicate"] is False
        item_id = UUID(result["item"]["id"])
        db_item = (
            await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        ).scalar_one()
        assert db_item.upload_key == "key-1"

    @pytest.mark.asyncio
    async def test_retry_with_same_key_is_reported_as_duplicate_not_recreated(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis

            first = await client.post(
                "/api/v1/items/bulk",
                files=files,
                data={"upload_keys": "key-retry"},
                headers=auth_headers,
            )
            retry = await client.post(
                "/api/v1/items/bulk",
                files=[("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))],
                data={"upload_keys": "key-retry"},
                headers=auth_headers,
            )

        first_item_id = first.json()["results"][0]["item"]["id"]
        retry_result = retry.json()["results"][0]
        assert retry_result["success"] is True
        assert retry_result["duplicate"] is True
        assert retry_result["existing_item_id"] == first_item_id

        count = (
            await db_session.execute(
                select(func.count())
                .select_from(ClothingItem)
                .where(
                    ClothingItem.user_id == test_user.id,
                    ClothingItem.upload_key == "key-retry",
                )
            )
        ).scalar_one()
        assert count == 1

    @pytest.mark.asyncio
    async def test_concurrent_race_hits_db_constraint_not_a_second_row(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        """Simulates two concurrent drains racing on the same queued record: the
        pre-check sees no existing row (patched to always miss), but the row is
        already committed by the time create() flushes, so the real unique index
        must catch it - this exercises the IntegrityError branch, not the fast path."""
        test_user_id = test_user.id
        item_service = ItemService(db_session)
        image_paths = {"image_path": "seed.jpg", "image_hash": "seedhash1234abcd"}
        winner = await item_service.create(
            user_id=test_user_id,
            item_data=ItemCreate(type="unknown"),
            image_paths=image_paths,
            upload_key="key-race",
        )
        await db_session.commit()
        winner_id = winner.id

        # Miss only on the first call (the pre-check racing the winner's commit);
        # a real second call must hit the actual DB so the post-conflict lookup
        # in the except branch is exercised for real, not also silenced by the mock.
        real_find_by_upload_key = ItemService.find_by_upload_key
        call_count = {"n": 0}

        async def flaky_find_by_upload_key(self, user_id, upload_key):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None
            return await real_find_by_upload_key(self, user_id, upload_key)

        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool,
            patch(
                "app.api.items.ItemService.find_by_upload_key",
                new=flaky_find_by_upload_key,
            ),
        ):
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                data={"upload_keys": "key-race"},
                headers=auth_headers,
            )

        assert response.status_code == 201
        result = response.json()["results"][0]
        assert result["success"] is True
        assert result["duplicate"] is True
        assert result["existing_item_id"] == str(winner_id)

        count = (
            await db_session.execute(
                select(func.count())
                .select_from(ClothingItem)
                .where(
                    ClothingItem.user_id == test_user_id,
                    ClothingItem.upload_key == "key-race",
                )
            )
        ).scalar_one()
        assert count == 1

    @pytest.mark.asyncio
    async def test_no_upload_keys_behaves_exactly_as_before(
        self, client: AsyncClient, auth_headers
    ):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                headers=auth_headers,
            )

        assert response.status_code == 201
        result = response.json()["results"][0]
        assert result["success"] is True
        assert result["duplicate"] is False
        assert result["existing_item_id"] is None

    @pytest.mark.asyncio
    async def test_mismatched_upload_keys_length_rejected(self, client: AsyncClient, auth_headers):
        files = [
            ("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg")),
            ("images", ("pants.jpg", _make_test_image_bytes(), "image/jpeg")),
        ]
        response = await client.post(
            "/api/v1/items/bulk",
            files=files,
            data={"upload_keys": "only-one-key"},
            headers=auth_headers,
        )
        assert response.status_code == 400


class TestBulkCreateSkipAI:
    @pytest.mark.asyncio
    async def test_skip_ai_marks_items_ready_without_queueing(
        self, client: AsyncClient, auth_headers
    ):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                data={"skip_ai": "true"},
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["successful"] == 1, data["results"][0].get("error")
        assert data["results"][0]["item"]["status"] == "ready"
        mock_redis.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_queues_ai_tagging(self, client: AsyncClient, auth_headers):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["successful"] == 1
        assert data["results"][0]["item"]["status"] == "processing"
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_queues_persists_ai_job_id(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fake-job-id"
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                headers=auth_headers,
            )

        assert response.status_code == 201
        item_id = UUID(response.json()["results"][0]["item"]["id"])
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        assert result.scalar_one().ai_job_id == "fake-job-id"


class TestCancelAnalysis:
    async def _create_item(
        self,
        db_session: AsyncSession,
        test_user,
        status: ItemStatus = ItemStatus.processing,
        ai_job_id: str | None = None,
    ) -> ClothingItem:
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/cancel.jpg",
            status=status,
            ai_job_id=ai_job_id,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        return item

    @pytest.mark.asyncio
    async def test_cancel_flips_processing_item_to_ready_and_aborts_job(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, ai_job_id="job-123")

        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool,
            patch("app.api.items.Job") as mock_job_cls,
        ):
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis
            mock_job = mock_job_cls.return_value
            mock_job.abort = AsyncMock(return_value=True)

            response = await client.post(
                f"/api/v1/items/{item.id}/cancel-analysis", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        mock_job_cls.assert_called_once_with("job-123", mock_redis, _queue_name="arq:tagging")
        mock_job.abort.assert_awaited_once_with(timeout=5)
        mock_redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancel_without_job_id_skips_job_construction(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, ai_job_id=None)

        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool,
            patch("app.api.items.Job") as mock_job_cls,
        ):
            response = await client.post(
                f"/api/v1/items/{item.id}/cancel-analysis", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        mock_create_pool.assert_not_called()
        mock_job_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_still_flips_to_ready_when_abort_raises(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, ai_job_id="job-456")

        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool,
            patch("app.api.items.Job") as mock_job_cls,
        ):
            mock_create_pool.return_value = AsyncMock()
            mock_job_cls.return_value.abort = AsyncMock(side_effect=Exception("job gone"))

            response = await client.post(
                f"/api/v1/items/{item.id}/cancel-analysis", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    @pytest.mark.asyncio
    async def test_cancel_still_flips_to_ready_when_abort_times_out(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, ai_job_id="job-789")

        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool,
            patch("app.api.items.Job") as mock_job_cls,
        ):
            mock_create_pool.return_value = AsyncMock()
            mock_job_cls.return_value.abort = AsyncMock(side_effect=TimeoutError())

            response = await client.post(
                f"/api/v1/items/{item.id}/cancel-analysis", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    @pytest.mark.asyncio
    async def test_cancel_unknown_item_404(self, client: AsyncClient, auth_headers):
        response = await client.post(
            f"/api/v1/items/{uuid4()}/cancel-analysis", headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_already_ready_item_is_noop(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(
            db_session, test_user, status=ItemStatus.ready, ai_job_id="job-stale"
        )

        with patch("app.api.items.Job") as mock_job_cls:
            response = await client.post(
                f"/api/v1/items/{item.id}/cancel-analysis", headers=auth_headers
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        mock_job_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_already_error_item_stays_error(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, status=ItemStatus.error)

        response = await client.post(
            f"/api/v1/items/{item.id}/cancel-analysis", headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json()["status"] == "error"


class TestBulkCancelAnalysis:
    async def _create_item(
        self,
        db_session: AsyncSession,
        test_user,
        status: ItemStatus = ItemStatus.processing,
        ai_job_id: str | None = None,
    ) -> ClothingItem:
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/bulk-cancel.jpg",
            status=status,
            ai_job_id=ai_job_id,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        return item

    @pytest.mark.asyncio
    async def test_bulk_cancel_flips_processing_items_and_aborts_jobs(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        first = await self._create_item(db_session, test_user, ai_job_id="job-1")
        second = await self._create_item(db_session, test_user, ai_job_id="job-2")

        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool,
            patch("app.api.items.Job") as mock_job_cls,
        ):
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis
            mock_job_cls.return_value.abort = AsyncMock(return_value=True)

            response = await client.post(
                "/api/v1/items/bulk/cancel-analysis",
                headers=auth_headers,
                json={"item_ids": [str(first.id), str(second.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["cancelled"] == 2
        assert body["skipped"] == 0
        assert mock_job_cls.call_count == 2
        mock_redis.aclose.assert_awaited_once()

        for item_id in (first.id, second.id):
            result = await db_session.execute(
                select(ClothingItem).where(ClothingItem.id == item_id)
            )
            item = result.scalar_one()
            assert item.status == ItemStatus.ready
            assert item.ai_job_id is None

    @pytest.mark.asyncio
    async def test_bulk_cancel_skips_non_processing_items(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        processing = await self._create_item(db_session, test_user, ai_job_id="job-1")
        ready = await self._create_item(db_session, test_user, status=ItemStatus.ready)

        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool,
            patch("app.api.items.Job") as mock_job_cls,
        ):
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis
            mock_job_cls.return_value.abort = AsyncMock(return_value=True)

            response = await client.post(
                "/api/v1/items/bulk/cancel-analysis",
                headers=auth_headers,
                json={"item_ids": [str(processing.id), str(ready.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["cancelled"] == 1
        assert body["skipped"] == 1
        mock_job_cls.assert_called_once_with("job-1", mock_redis, _queue_name="arq:tagging")

    @pytest.mark.asyncio
    async def test_bulk_cancel_select_all_respects_excluded_ids(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        keep_running = await self._create_item(db_session, test_user, ai_job_id="job-keep")
        to_cancel = await self._create_item(db_session, test_user, ai_job_id="job-cancel")

        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool,
            patch("app.api.items.Job") as mock_job_cls,
        ):
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis
            mock_job_cls.return_value.abort = AsyncMock(return_value=True)

            response = await client.post(
                "/api/v1/items/bulk/cancel-analysis",
                headers=auth_headers,
                json={"select_all": True, "excluded_ids": [str(keep_running.id)]},
            )

        assert response.status_code == 200
        assert response.json()["cancelled"] == 1
        mock_job_cls.assert_called_once_with("job-cancel", mock_redis, _queue_name="arq:tagging")

        result = await db_session.execute(
            select(ClothingItem).where(ClothingItem.id == keep_running.id)
        )
        assert result.scalar_one().status == ItemStatus.processing

        result = await db_session.execute(
            select(ClothingItem).where(ClothingItem.id == to_cancel.id)
        )
        assert result.scalar_one().status == ItemStatus.ready

    @pytest.mark.asyncio
    async def test_bulk_cancel_still_flips_to_ready_when_abort_raises(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, ai_job_id="job-flaky")

        with (
            patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool,
            patch("app.api.items.Job") as mock_job_cls,
        ):
            mock_create_pool.return_value = AsyncMock()
            mock_job_cls.return_value.abort = AsyncMock(side_effect=Exception("job gone"))

            response = await client.post(
                "/api/v1/items/bulk/cancel-analysis",
                headers=auth_headers,
                json={"item_ids": [str(item.id)]},
            )

        assert response.status_code == 200
        assert response.json()["cancelled"] == 1

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item.id))
        assert result.scalar_one().status == ItemStatus.ready

    @pytest.mark.asyncio
    async def test_bulk_cancel_redis_connect_failure_leaves_items_untouched(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, ai_job_id="job-1")

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.side_effect = Exception("no redis")

            response = await client.post(
                "/api/v1/items/bulk/cancel-analysis",
                headers=auth_headers,
                json={"item_ids": [str(item.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["cancelled"] == 0
        assert body["errors"]

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item.id))
        assert result.scalar_one().status == ItemStatus.processing

    @pytest.mark.asyncio
    async def test_bulk_cancel_unknown_item_reported_in_errors(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.post(
            "/api/v1/items/bulk/cancel-analysis",
            headers=auth_headers,
            json={"item_ids": [str(uuid4())]},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["cancelled"] == 0
        assert body["skipped"] == 0
        assert body["errors"]

    @pytest.mark.asyncio
    async def test_bulk_cancel_rejects_item_ids_and_select_all_together(
        self, client: AsyncClient, auth_headers
    ):
        response = await client.post(
            "/api/v1/items/bulk/cancel-analysis",
            headers=auth_headers,
            json={"item_ids": [str(uuid4())], "select_all": True},
        )

        assert response.status_code == 422


class TestAnalysisIdempotency:
    async def _create_item(
        self,
        db_session: AsyncSession,
        test_user,
        status: ItemStatus = ItemStatus.processing,
        ai_job_id: str | None = None,
        processing_kind: str | None = None,
    ) -> ClothingItem:
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/idempotency.jpg",
            status=status,
            ai_job_id=ai_job_id,
            processing_kind=processing_kind,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        return item

    @pytest.mark.asyncio
    async def test_trigger_analysis_dedupes_when_already_processing_with_job(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, ai_job_id="existing-job")

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            response = await client.post(f"/api/v1/items/{item.id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"status": "already_queued", "job_id": "existing-job"}
        mock_create_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_analysis_enqueues_fresh_job_when_no_job_id(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, ai_job_id=None)

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "fresh-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(f"/api/v1/items/{item.id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"status": "queued", "job_id": "fresh-job-id"}
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_analyze_skips_already_processing_with_job(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        already_processing = await self._create_item(
            db_session, test_user, status=ItemStatus.processing, ai_job_id="live-job"
        )
        needs_queueing = await self._create_item(
            db_session, test_user, status=ItemStatus.ready, ai_job_id=None
        )

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "new-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/analyze",
                headers=auth_headers,
                json={"item_ids": [str(already_processing.id), str(needs_queueing.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 1
        assert body["skipped"] == 1
        assert body["failed"] == 0
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_analyze_stuck_item_with_no_job_gets_fresh_job(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        stuck = await self._create_item(
            db_session, test_user, status=ItemStatus.processing, ai_job_id=None
        )

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "recovery-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/analyze",
                headers=auth_headers,
                json={"item_ids": [str(stuck.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 1
        assert body["skipped"] == 0
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_analyze_resets_leftover_processing_kind(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # A stuck processing+no-job item can carry a leftover
        # processing_kind="background_removal" from a job that never got an
        # ai_job_id - re-queueing it for AI tagging must clear the kind, since
        # NULL means AI tagging (the invariant every entry point relies on).
        stuck = await self._create_item(
            db_session,
            test_user,
            status=ItemStatus.processing,
            ai_job_id=None,
            processing_kind="background_removal",
        )
        item_id = stuck.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "recovery-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/analyze",
                headers=auth_headers,
                json={"item_ids": [str(item_id)]},
            )

        assert response.status_code == 200
        assert response.json()["queued"] == 1

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        assert result.scalar_one().processing_kind is None

    @pytest.mark.asyncio
    async def test_bulk_analyze_redis_failure_only_errors_items_it_touched(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        already_processing = await self._create_item(
            db_session, test_user, status=ItemStatus.processing, ai_job_id="live-job"
        )
        needs_queueing = await self._create_item(
            db_session, test_user, status=ItemStatus.ready, ai_job_id=None
        )
        # Captured before the request: the endpoint's own commit (on the same
        # shared session) expires these ORM instances' attributes, and reading
        # `.id` off an expired instance afterward triggers an implicit lazy
        # load that fails outside an async context.
        already_processing_id = already_processing.id
        needs_queueing_id = needs_queueing.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.side_effect = Exception("no redis")
            response = await client.post(
                "/api/v1/items/bulk/analyze",
                headers=auth_headers,
                json={"item_ids": [str(already_processing_id), str(needs_queueing_id)]},
            )

        assert response.status_code == 500

        db_session.expire_all()
        result = await db_session.execute(
            select(ClothingItem).where(ClothingItem.id == already_processing_id)
        )
        # A transient Redis outage must not error out an item that was already
        # processing with a live job and untouched by this request.
        assert result.scalar_one().status == ItemStatus.processing

        result = await db_session.execute(
            select(ClothingItem).where(ClothingItem.id == needs_queueing_id)
        )
        assert result.scalar_one().status == ItemStatus.error


class TestRetryCooldownClaims:
    """Tests for the atomic retry-cooldown claim methods (issue #153)."""

    async def _create_item(
        self,
        db_session: AsyncSession,
        test_user,
        status: ItemStatus = ItemStatus.error,
        ai_job_id: str | None = None,
        ai_failed_at: datetime | None = None,
        processing_kind: str | None = None,
    ) -> ClothingItem:
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/cooldown.jpg",
            status=status,
            ai_job_id=ai_job_id,
            ai_failed_at=ai_failed_at,
            processing_kind=processing_kind,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        return item

    @pytest.mark.asyncio
    async def test_claim_blocked_within_cooldown(self, db_session: AsyncSession, test_user):
        item = await self._create_item(db_session, test_user, ai_failed_at=datetime.now(UTC))

        item_id = item.id
        service = ItemService(db_session)
        job_id, retry_after = await service.claim_error_item_for_retry(
            item_id, cooldown_seconds=120
        )

        assert job_id is None
        assert retry_after is not None and retry_after > 0

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        assert result.scalar_one().status == ItemStatus.error

    @pytest.mark.asyncio
    async def test_claim_succeeds_past_cooldown(self, db_session: AsyncSession, test_user):
        item = await self._create_item(
            db_session, test_user, ai_failed_at=datetime.now(UTC) - timedelta(seconds=200)
        )
        item_id = item.id

        service = ItemService(db_session)
        job_id, retry_after = await service.claim_error_item_for_retry(
            item_id, cooldown_seconds=120
        )

        assert job_id is not None
        assert retry_after is None

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        claimed = result.scalar_one()
        assert claimed.status == ItemStatus.processing
        assert claimed.ai_job_id == job_id
        assert claimed.ai_started_at is None

    @pytest.mark.asyncio
    async def test_claim_resets_processing_kind_to_none(self, db_session: AsyncSession, test_user):
        # A background-removal failure keeps processing_kind so the grid can
        # label it - retrying it as AI tagging must reset the kind back to
        # NULL, the invariant every tagging entry point relies on.
        item = await self._create_item(
            db_session,
            test_user,
            ai_failed_at=datetime.now(UTC) - timedelta(seconds=200),
            processing_kind="background_removal",
        )
        item_id = item.id

        service = ItemService(db_session)
        job_id, _ = await service.claim_error_item_for_retry(item_id, cooldown_seconds=120)
        assert job_id is not None

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        assert result.scalar_one().processing_kind is None

    @pytest.mark.asyncio
    async def test_batched_claim_resets_processing_kind_to_none(
        self, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(
            db_session,
            test_user,
            ai_failed_at=datetime.now(UTC) - timedelta(seconds=200),
            processing_kind="background_removal",
        )
        item_id = item.id

        service = ItemService(db_session)
        claimed, _ = await service.claim_error_items_for_retry([item_id], cooldown_seconds=120)
        assert item_id in claimed

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        assert result.scalar_one().processing_kind is None

    @pytest.mark.asyncio
    async def test_claim_succeeds_when_never_failed(self, db_session: AsyncSession, test_user):
        item = await self._create_item(db_session, test_user, ai_failed_at=None)

        service = ItemService(db_session)
        job_id, retry_after = await service.claim_error_item_for_retry(
            item.id, cooldown_seconds=120
        )

        assert job_id is not None
        assert retry_after is None

    @pytest.mark.asyncio
    async def test_claim_returns_none_for_non_error_status(
        self, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(db_session, test_user, status=ItemStatus.ready)

        service = ItemService(db_session)
        job_id, retry_after = await service.claim_error_item_for_retry(
            item.id, cooldown_seconds=120
        )

        # Not "error" at all - not a cooldown, caller must not report one.
        assert job_id is None
        assert retry_after is None

    @pytest.mark.asyncio
    async def test_claim_loser_of_race_gets_no_cooldown(self, db_session: AsyncSession, test_user):
        # Simulates losing a concurrent claim: by the time this call runs, some
        # other request already flipped the row to processing. Must not be
        # mislabeled as "cooldown" with a nonsensical retry_after_seconds.
        item = await self._create_item(
            db_session, test_user, status=ItemStatus.processing, ai_job_id="winner-job"
        )

        service = ItemService(db_session)
        job_id, retry_after = await service.claim_error_item_for_retry(
            item.id, cooldown_seconds=120
        )

        assert job_id is None
        assert retry_after is None

    @pytest.mark.asyncio
    async def test_release_failed_claim_restores_error_without_touching_ai_failed_at(
        self, db_session: AsyncSession, test_user
    ):
        original_failure = datetime.now(UTC) - timedelta(seconds=200)
        item = await self._create_item(db_session, test_user, ai_failed_at=original_failure)
        item_id = item.id

        service = ItemService(db_session)
        job_id, _ = await service.claim_error_item_for_retry(item_id, cooldown_seconds=120)
        assert job_id is not None

        await service.release_failed_claim(item_id, job_id)

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        released = result.scalar_one()
        assert released.status == ItemStatus.error
        # Untouched: this was an infra failure (enqueue), not a fresh AI failure -
        # the prior cooldown had already elapsed, so it must stay elapsed.
        assert released.ai_failed_at == original_failure

    @pytest.mark.asyncio
    async def test_release_failed_claim_is_noop_for_mismatched_job_id(
        self, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(
            db_session, test_user, status=ItemStatus.processing, ai_job_id="real-job"
        )
        item_id = item.id

        service = ItemService(db_session)
        await service.release_failed_claim(item_id, "wrong-job-id")

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        # A stale/mismatched compensating rollback must never clobber a
        # since-changed row.
        assert result.scalar_one().status == ItemStatus.processing

    @pytest.mark.asyncio
    async def test_batched_claim_empty_input_returns_empty(
        self, db_session: AsyncSession, test_user
    ):
        service = ItemService(db_session)
        claimed, cooling_down = await service.claim_error_items_for_retry([], cooldown_seconds=120)

        assert claimed == {}
        assert cooling_down == {}

    @pytest.mark.asyncio
    async def test_batched_claim_mixed_ids(self, db_session: AsyncSession, test_user):
        eligible = await self._create_item(
            db_session, test_user, ai_failed_at=datetime.now(UTC) - timedelta(seconds=200)
        )
        cooling_down = await self._create_item(
            db_session, test_user, ai_failed_at=datetime.now(UTC)
        )
        not_error = await self._create_item(db_session, test_user, status=ItemStatus.ready)

        service = ItemService(db_session)
        claimed, cooling = await service.claim_error_items_for_retry(
            [eligible.id, cooling_down.id, not_error.id], cooldown_seconds=120
        )

        assert set(claimed.keys()) == {eligible.id}
        assert set(cooling.keys()) == {cooling_down.id}
        assert not_error.id not in claimed
        assert not_error.id not in cooling

    @pytest.mark.asyncio
    async def test_concurrent_claims_only_one_wins(
        self, db_session: AsyncSession, async_engine, test_user
    ):
        # Exercises the actual production method (not a hand-copied SQL string)
        # from two independent DB sessions/connections - the shared `client`/
        # `db_session` test fixture aliases every request onto one transaction,
        # which can't demonstrate row-level contention at all.
        item = await self._create_item(
            db_session, test_user, ai_failed_at=datetime.now(UTC) - timedelta(seconds=200)
        )
        item_id = item.id

        session_maker = async_sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )

        async def _attempt() -> str | None:
            async with session_maker() as session:
                service = ItemService(session)
                job_id, _ = await service.claim_error_item_for_retry(item_id, cooldown_seconds=120)
                await session.commit()
                return job_id

        results = await asyncio.gather(_attempt(), _attempt())
        winners = [job_id for job_id in results if job_id is not None]
        assert len(winners) == 1


class TestRetryCooldownEndpoint:
    """trigger_ai_analysis's status-partitioned cooldown gate (issue #153)."""

    async def _create_item(
        self,
        db_session: AsyncSession,
        test_user,
        status: ItemStatus,
        ai_job_id: str | None = None,
        ai_failed_at: datetime | None = None,
        processing_kind: str | None = None,
    ) -> ClothingItem:
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/endpoint-cooldown.jpg",
            status=status,
            ai_job_id=ai_job_id,
            ai_failed_at=ai_failed_at,
            processing_kind=processing_kind,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        return item

    @pytest.mark.asyncio
    async def test_retry_blocked_within_cooldown(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(
            db_session, test_user, status=ItemStatus.error, ai_failed_at=datetime.now(UTC)
        )

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            response = await client.post(f"/api/v1/items/{item.id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cooldown"
        assert body["retry_after_seconds"] > 0
        mock_create_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_succeeds_past_cooldown(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(
            db_session,
            test_user,
            status=ItemStatus.error,
            ai_failed_at=datetime.now(UTC) - timedelta(seconds=200),
        )
        item_id = item.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value = object()
            mock_create_pool.return_value = mock_redis

            response = await client.post(f"/api/v1/items/{item_id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "queued"
        mock_redis.enqueue_job.assert_called_once()
        _, kwargs = mock_redis.enqueue_job.call_args
        assert kwargs["_job_id"] == body["job_id"]

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        assert result.scalar_one().status == ItemStatus.processing

    @pytest.mark.asyncio
    async def test_retry_past_cooldown_resets_leftover_processing_kind(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # An item that failed background removal keeps processing_kind so the
        # grid can label it - retrying it as AI tagging through this endpoint
        # must reset the kind back to NULL.
        item = await self._create_item(
            db_session,
            test_user,
            status=ItemStatus.error,
            ai_failed_at=datetime.now(UTC) - timedelta(seconds=200),
            processing_kind="background_removal",
        )
        item_id = item.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value = object()
            mock_create_pool.return_value = mock_redis

            response = await client.post(f"/api/v1/items/{item_id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["status"] == "queued"

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        assert result.scalar_one().processing_kind is None

    @pytest.mark.asyncio
    async def test_ready_item_never_routed_through_cooldown_claim(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # Regression guard: an earlier draft of this fix routed every status
        # through the error-only claim, which would have falsely cooldown-
        # blocked every normal (non-error) retry/analyze call.
        item = await self._create_item(db_session, test_user, status=ItemStatus.ready)
        item_id = item.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "ready-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(f"/api/v1/items/{item_id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "queued"
        assert body["job_id"] == "ready-job-id"
        mock_redis.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_orphaned_processing_item_never_routed_through_cooldown_claim(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        # The documented processing+no-job recovery fallthrough (a prior enqueue
        # silently failed) must also skip the error-only cooldown claim.
        item = await self._create_item(
            db_session, test_user, status=ItemStatus.processing, ai_job_id=None
        )
        item_id = item.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "recovered-job-id"
            mock_create_pool.return_value = mock_redis

            response = await client.post(f"/api/v1/items/{item_id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "queued"
        assert body["job_id"] == "recovered-job-id"

    @pytest.mark.asyncio
    async def test_retry_regression_real_failure_then_immediate_retry_blocked(
        self,
        client: AsyncClient,
        auth_headers,
        db_session: AsyncSession,
        async_engine,
        test_user,
    ):
        # Reproduces #153's actual reported symptom end to end: an item fails
        # through the real worker failure path, then an immediate retry.
        item = await self._create_item(db_session, test_user, status=ItemStatus.processing)
        item_id = item.id

        worker_ctx = {
            "db_session_factory": async_sessionmaker(
                async_engine, class_=AsyncSession, expire_on_commit=False
            )
        }
        await update_item_status_to_error(worker_ctx, str(item_id), "boom")
        # update_item_status_to_error writes through a separate session, so
        # db_session's identity map still holds the pre-failure `item` object
        # with its old (non-expired) status - expire it or the endpoint's
        # get_by_id on this same session returns the stale in-memory copy.
        db_session.expire_all()

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            response = await client.post(f"/api/v1/items/{item_id}/analyze", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cooldown"
        assert body["retry_after_seconds"] > 0
        mock_create_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_claim_enqueue_failure_rolls_back_without_new_cooldown(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        item = await self._create_item(
            db_session,
            test_user,
            status=ItemStatus.error,
            ai_failed_at=datetime.now(UTC) - timedelta(seconds=200),
        )
        item_id = item.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.side_effect = Exception("redis blip")
            mock_create_pool.return_value = mock_redis

            response = await client.post(f"/api/v1/items/{item_id}/analyze", headers=auth_headers)

        assert response.status_code == 500

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        rolled_back = result.scalar_one()
        assert rolled_back.status == ItemStatus.error
        # Infra failure, not an AI failure - must not start a fresh cooldown.
        assert rolled_back.ai_failed_at < datetime.now(UTC) - timedelta(seconds=100)


class TestBulkRetryCooldown:
    """bulk_analyze_items' batched cooldown gate (issue #153)."""

    async def _create_item(
        self,
        db_session: AsyncSession,
        test_user,
        status: ItemStatus,
        ai_job_id: str | None = None,
        ai_failed_at: datetime | None = None,
    ) -> ClothingItem:
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/bulk-cooldown.jpg",
            status=status,
            ai_job_id=ai_job_id,
            ai_failed_at=ai_failed_at,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        return item

    @pytest.mark.asyncio
    async def test_bulk_reports_cooldown_separately_from_skipped(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        already_processing = await self._create_item(
            db_session, test_user, status=ItemStatus.processing, ai_job_id="live-job"
        )
        cooling_down = await self._create_item(
            db_session, test_user, status=ItemStatus.error, ai_failed_at=datetime.now(UTC)
        )
        eligible = await self._create_item(
            db_session,
            test_user,
            status=ItemStatus.error,
            ai_failed_at=datetime.now(UTC) - timedelta(seconds=200),
        )

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value = object()
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/analyze",
                headers=auth_headers,
                json={
                    "item_ids": [
                        str(already_processing.id),
                        str(cooling_down.id),
                        str(eligible.id),
                    ]
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 1
        assert body["skipped"] == 1
        assert body["cooldown"] == 1
        assert body["retry_after_seconds"] > 0
        assert body["failed"] == 0
        mock_redis.enqueue_job.assert_called_once()
        _, kwargs = mock_redis.enqueue_job.call_args
        assert kwargs["_job_id"] is not None

    @pytest.mark.asyncio
    async def test_bulk_empty_error_candidate_batch(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        ready_item = await self._create_item(db_session, test_user, status=ItemStatus.ready)

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "ready-job"
            mock_create_pool.return_value = mock_redis

            response = await client.post(
                "/api/v1/items/bulk/analyze",
                headers=auth_headers,
                json={"item_ids": [str(ready_item.id)]},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["queued"] == 1
        assert body["cooldown"] == 0
        assert body["retry_after_seconds"] is None

    @pytest.mark.asyncio
    async def test_bulk_redis_failure_releases_claim_without_new_cooldown(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession, test_user
    ):
        eligible = await self._create_item(
            db_session,
            test_user,
            status=ItemStatus.error,
            ai_failed_at=datetime.now(UTC) - timedelta(seconds=200),
        )
        eligible_id = eligible.id

        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.side_effect = Exception("no redis")
            response = await client.post(
                "/api/v1/items/bulk/analyze",
                headers=auth_headers,
                json={"item_ids": [str(eligible_id)]},
            )

        assert response.status_code == 500

        db_session.expire_all()
        result = await db_session.execute(
            select(ClothingItem).where(ClothingItem.id == eligible_id)
        )
        released = result.scalar_one()
        assert released.status == ItemStatus.error
        assert released.ai_failed_at < datetime.now(UTC) - timedelta(seconds=100)
