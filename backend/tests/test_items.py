from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.item_service import ItemService


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
