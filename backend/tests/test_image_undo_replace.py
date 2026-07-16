from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService

GREEN = (10, 200, 30)
RED = (220, 30, 20)
BLUE = (0, 0, 255)


def _jpeg_bytes(color=GREEN, size=(600, 600)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _mock_provider():
    provider = MagicMock()
    provider.remove.side_effect = lambda img: Image.new("RGBA", img.size, (*BLUE, 255))
    return provider


def _pixel(path) -> tuple[int, int, int]:
    return Image.open(path).convert("RGB").getpixel((5, 5))


def _close(a: tuple, b: tuple, tolerance: int = 20) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


async def _make_item(db_session: AsyncSession, user: User) -> ClothingItem:
    svc = ImageService()
    paths = await svc.process_and_store(
        user_id=user.id, image_data=_jpeg_bytes(), original_filename="test.jpg"
    )
    item = ClothingItem(
        user_id=user.id,
        type="shirt",
        image_path=paths["image_path"],
        medium_path=paths["medium_path"],
        thumbnail_path=paths["thumbnail_path"],
        image_hash=paths["image_hash"],
        status=ItemStatus.ready,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


@pytest_asyncio.fixture
async def item_with_image(db_session: AsyncSession, test_user: User) -> ClothingItem:
    return await _make_item(db_session, test_user)


class TestRemoveBackgroundBackup:
    @pytest.mark.asyncio
    async def test_backup_file_created(self, item_with_image: ClothingItem):
        svc = ImageService()
        original_bytes = svc.get_image_path(item_with_image.image_path).read_bytes()

        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            result = svc.remove_background(item_with_image.image_path)

        backup_path = result["original_backup_path"]
        assert backup_path.endswith("_orig.jpg")
        backup_full = svc.get_image_path(backup_path)
        assert backup_full.exists()
        assert backup_full.read_bytes() == original_bytes
        assert _close(_pixel(svc.get_image_path(item_with_image.image_path)), BLUE)

    @pytest.mark.asyncio
    async def test_double_removal_keeps_first_backup(self, item_with_image: ClothingItem):
        svc = ImageService()
        original_bytes = svc.get_image_path(item_with_image.image_path).read_bytes()

        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            first = svc.remove_background(item_with_image.image_path)
            second = svc.remove_background(item_with_image.image_path)

        assert first["original_backup_path"] == second["original_backup_path"]
        backup_full = svc.get_image_path(first["original_backup_path"])
        assert backup_full.read_bytes() == original_bytes

    @pytest.mark.asyncio
    async def test_restore_original(self, item_with_image: ClothingItem):
        svc = ImageService()
        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            result = svc.remove_background(item_with_image.image_path)

        restored = svc.restore_original(item_with_image.image_path, result["original_backup_path"])

        assert restored["image_path"] == item_with_image.image_path
        assert _close(_pixel(svc.get_image_path(item_with_image.image_path)), GREEN)
        assert _close(_pixel(svc.get_image_path(restored["medium_path"])), GREEN)
        assert _close(_pixel(svc.get_image_path(restored["thumbnail_path"])), GREEN)
        assert not svc.get_image_path(result["original_backup_path"]).exists()

    @pytest.mark.asyncio
    async def test_restore_missing_backup_raises(self, item_with_image: ClothingItem):
        svc = ImageService()
        with pytest.raises(ValueError, match="Backup not found"):
            svc.restore_original(
                item_with_image.image_path, f"{item_with_image.user_id}/missing_orig.jpg"
            )


class TestRemoveBackgroundEndpointBackup:
    @pytest.mark.asyncio
    async def test_sets_original_image_path(
        self, client: AsyncClient, auth_headers, item_with_image: ClothingItem
    ):
        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            response = await client.post(
                f"/api/v1/items/{item_with_image.id}/remove-background",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["original_image_path"] is not None
        assert data["original_image_path"].endswith("_orig.jpg")
        assert ImageService().get_image_path(data["original_image_path"]).exists()


class TestRestoreOriginalEndpoint:
    @pytest.mark.asyncio
    async def test_restores_and_clears_backup(
        self, client: AsyncClient, auth_headers, item_with_image: ClothingItem
    ):
        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            removal = await client.post(
                f"/api/v1/items/{item_with_image.id}/remove-background",
                json={},
                headers=auth_headers,
            )
        backup_path = removal.json()["original_image_path"]

        response = await client.post(
            f"/api/v1/items/{item_with_image.id}/restore-original",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["original_image_path"] is None
        svc = ImageService()
        assert _close(_pixel(svc.get_image_path(item_with_image.image_path)), GREEN)
        assert not svc.get_image_path(backup_path).exists()

    @pytest.mark.asyncio
    async def test_no_backup_returns_400(
        self, client: AsyncClient, auth_headers, item_with_image: ClothingItem
    ):
        response = await client.post(
            f"/api/v1/items/{item_with_image.id}/restore-original",
            headers=auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_unauthenticated(self, client: AsyncClient):
        response = await client.post(f"/api/v1/items/{uuid4()}/restore-original")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_other_users_item_404(
        self, client: AsyncClient, auth_headers, db_session: AsyncSession
    ):
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
        item = await _make_item(db_session, other_user)

        response = await client.post(
            f"/api/v1/items/{item.id}/restore-original",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestReplaceImageEndpoint:
    @pytest.mark.asyncio
    async def test_replaces_image_and_cleans_up(
        self, client: AsyncClient, auth_headers, item_with_image: ClothingItem
    ):
        svc = ImageService()
        old_paths = {
            "image_path": item_with_image.image_path,
            "medium_path": item_with_image.medium_path,
            "thumbnail_path": item_with_image.thumbnail_path,
        }
        old_hash = item_with_image.image_hash
        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            removal = await client.post(
                f"/api/v1/items/{item_with_image.id}/remove-background",
                json={},
                headers=auth_headers,
            )
        backup_path = removal.json()["original_image_path"]

        response = await client.put(
            f"/api/v1/items/{item_with_image.id}/image",
            files={"image": ("new.jpg", _jpeg_bytes(color=RED), "image/jpeg")},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["image_path"] != old_paths["image_path"]
        assert data["original_image_path"] is None
        assert data["image_hash"] != old_hash if "image_hash" in data else True
        assert _close(_pixel(svc.get_image_path(data["image_path"])), RED)
        for path in old_paths.values():
            assert not svc.get_image_path(path).exists()
        assert not svc.get_image_path(backup_path).exists()

    @pytest.mark.asyncio
    async def test_invalid_file_400(
        self, client: AsyncClient, auth_headers, item_with_image: ClothingItem
    ):
        response = await client.put(
            f"/api/v1/items/{item_with_image.id}/image",
            files={"image": ("evil.txt", b"not an image", "text/plain")},
            headers=auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_unauthenticated(self, client: AsyncClient):
        response = await client.put(
            f"/api/v1/items/{uuid4()}/image",
            files={"image": ("new.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_item_not_found(self, client: AsyncClient, auth_headers):
        response = await client.put(
            f"/api/v1/items/{uuid4()}/image",
            files={"image": ("new.jpg", _jpeg_bytes(), "image/jpeg")},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestDeleteCleansBackup:
    @pytest.mark.asyncio
    async def test_delete_item_removes_backup(
        self, client: AsyncClient, auth_headers, item_with_image: ClothingItem
    ):
        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            removal = await client.post(
                f"/api/v1/items/{item_with_image.id}/remove-background",
                json={},
                headers=auth_headers,
            )
        backup_path = removal.json()["original_image_path"]
        assert ImageService().get_image_path(backup_path).exists()

        response = await client.delete(f"/api/v1/items/{item_with_image.id}", headers=auth_headers)
        assert response.status_code == 204
        assert not ImageService().get_image_path(backup_path).exists()
