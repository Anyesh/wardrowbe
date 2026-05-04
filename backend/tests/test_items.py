from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import items as items_api
from app.models.item import ClothingItem, ItemStatus
from app.services.item_service import ItemService


def make_upload_jpeg() -> bytes:
    out = BytesIO()
    Image.new("RGB", (32, 32), "white").save(out, format="JPEG")
    return out.getvalue()


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

    @pytest.mark.asyncio
    async def test_create_item_enqueues_storage_key(self, monkeypatch: pytest.MonkeyPatch):
        enqueued: dict[str, str] = {}
        user_id = uuid4()
        item_id = uuid4()
        now = datetime.now(UTC)

        class FakeUploadFile:
            filename = "shirt.jpg"
            content_type = "image/jpeg"

            async def read(self):
                return make_upload_jpeg()

        class FakeImageService:
            def validate_image(self, content: bytes, content_type: str) -> bool:
                return True

            def compute_phash(self, image_data: bytes, original_filename: str) -> str:
                return "abcd1234abcd1234"

            async def process_and_store(self, user_id, image_data: bytes, original_filename: str):
                return {
                    "image_path": f"{user_id}/shirt.jpg",
                    "thumbnail_path": f"{user_id}/shirt_thumb.jpg",
                    "medium_path": f"{user_id}/shirt_medium.jpg",
                    "image_hash": "abcd1234abcd1234",
                }

        class FakeItemService:
            def __init__(self, db):
                self.db = db

            async def find_duplicate_by_hash(self, user_id, image_hash: str):
                return None

            async def create(self, user_id, item_data, image_paths):
                return SimpleNamespace(
                    id=item_id,
                    user_id=user_id,
                    type=item_data.type,
                    subtype=item_data.subtype,
                    name=item_data.name,
                    brand=item_data.brand,
                    notes=item_data.notes,
                    purchase_date=None,
                    purchase_price=None,
                    favorite=item_data.favorite,
                    image_path=image_paths["image_path"],
                    thumbnail_path=image_paths["thumbnail_path"],
                    medium_path=image_paths["medium_path"],
                    tags={},
                    colors=[],
                    primary_color=None,
                    pattern=None,
                    material=None,
                    style=[],
                    formality=None,
                    season=[],
                    status=ItemStatus.processing,
                    ai_processed=False,
                    ai_confidence=None,
                    ai_description=None,
                    wear_count=0,
                    last_worn_at=None,
                    last_suggested_at=None,
                    suggestion_count=0,
                    acceptance_count=0,
                    wears_since_wash=0,
                    last_washed_at=None,
                    wash_interval=None,
                    needs_wash=False,
                    additional_images=[],
                    is_archived=False,
                    archived_at=None,
                    archive_reason=None,
                    created_at=now,
                    updated_at=now,
                )

        class FakeRedis:
            async def enqueue_job(self, name, item_id, image_key, **kwargs):
                enqueued["name"] = name
                enqueued["image_key"] = image_key
                enqueued["queue_name"] = kwargs["_queue_name"]

            async def aclose(self):
                pass

        async def fake_create_pool(*args, **kwargs):
            return FakeRedis()

        monkeypatch.setattr(items_api, "ImageService", FakeImageService)
        monkeypatch.setattr(items_api, "ItemService", FakeItemService)
        monkeypatch.setattr(items_api, "create_pool", fake_create_pool)
        response = await items_api.create_item(
            db=object(),
            current_user=SimpleNamespace(id=user_id),
            image=FakeUploadFile(),
            type=None,
            subtype=None,
            name=None,
            brand=None,
            notes=None,
            colors=None,
            primary_color=None,
            favorite=False,
        )

        assert response.id == item_id
        assert enqueued["name"] == "tag_item_image"
        assert enqueued["queue_name"] == "arq:tagging"
        assert enqueued["image_key"] == f"{user_id}/shirt.jpg"
        assert not enqueued["image_key"].startswith("/")


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
