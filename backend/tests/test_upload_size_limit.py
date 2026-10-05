from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import items as items_api
from app.config import Settings
from app.models.item import ClothingItem, ItemStatus
from app.utils.uploads import UploadTooLargeError, read_upload_within_limit

ONE_MB = 1024 * 1024


def _valid_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), (100, 150, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _oversize_jpeg() -> bytes:
    return _valid_jpeg() + b"\0" * ONE_MB


@pytest.fixture
def one_mb_limit():
    with patch.object(items_api.settings, "max_upload_size_mb", 1):
        yield


async def _make_item(db_session: AsyncSession, user_id) -> ClothingItem:
    item = ClothingItem(
        user_id=user_id,
        type="shirt",
        image_path="test/item.jpg",
        status=ItemStatus.ready,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _item_count(db_session: AsyncSession, user_id) -> int:
    result = await db_session.execute(
        select(func.count()).select_from(ClothingItem).where(ClothingItem.user_id == user_id)
    )
    return result.scalar_one()


class TestReadUploadWithinLimit:
    @pytest.mark.asyncio
    async def test_returns_content_at_the_limit(self):
        upload = UploadFile(file=BytesIO(b"x" * ONE_MB), size=ONE_MB)
        assert len(await read_upload_within_limit(upload, 1)) == ONE_MB

    @pytest.mark.asyncio
    async def test_rejects_declared_size_without_reading(self):
        file = BytesIO(b"x")
        upload = UploadFile(file=file, size=ONE_MB + 1)
        with pytest.raises(UploadTooLargeError):
            await read_upload_within_limit(upload, 1)
        assert file.tell() == 0

    @pytest.mark.asyncio
    async def test_rejects_oversize_body_when_size_is_unknown(self):
        upload = UploadFile(file=BytesIO(b"x" * (ONE_MB + 1)), size=None)
        with pytest.raises(UploadTooLargeError):
            await read_upload_within_limit(upload, 1)

    @pytest.mark.asyncio
    async def test_rejects_body_larger_than_its_declared_size(self):
        upload = UploadFile(file=BytesIO(b"x" * (ONE_MB + 1)), size=10)
        with pytest.raises(UploadTooLargeError):
            await read_upload_within_limit(upload, 1)


@pytest.mark.usefixtures("one_mb_limit")
class TestSingleUploadLimit:
    @pytest.mark.asyncio
    async def test_create_item_oversize_returns_413(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        response = await client.post(
            "/api/v1/items",
            files={"image": ("big.jpg", _oversize_jpeg(), "image/jpeg")},
            data={"skip_ai": "true"},
            headers=auth_headers,
        )

        assert response.status_code == 413
        assert "1 MB" in response.json()["detail"]
        assert await _item_count(db_session, test_user.id) == 0

    @pytest.mark.asyncio
    async def test_replace_image_oversize_returns_413(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user.id)

        response = await client.put(
            f"/api/v1/items/{item.id}/image",
            files={"image": ("big.jpg", _oversize_jpeg(), "image/jpeg")},
            headers=auth_headers,
        )

        assert response.status_code == 413
        await db_session.refresh(item)
        assert item.image_path == "test/item.jpg"

    @pytest.mark.asyncio
    async def test_add_image_oversize_returns_413(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user.id)

        response = await client.post(
            f"/api/v1/items/{item.id}/images",
            files={"image": ("big.jpg", _oversize_jpeg(), "image/jpeg")},
            headers=auth_headers,
        )

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_create_item_within_limit_still_succeeds(self, client: AsyncClient, auth_headers):
        response = await client.post(
            "/api/v1/items",
            files={"image": ("ok.jpg", _valid_jpeg(), "image/jpeg")},
            data={"skip_ai": "true"},
            headers=auth_headers,
        )

        assert response.status_code == 201


@pytest.mark.usefixtures("one_mb_limit")
class TestBulkUploadLimit:
    @pytest.mark.asyncio
    async def test_oversize_file_fails_alone_and_the_rest_are_created(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        files = [
            ("images", ("big.jpg", _oversize_jpeg(), "image/jpeg")),
            ("images", ("ok.jpg", _valid_jpeg(), "image/jpeg")),
        ]
        with patch("app.api.items.create_pool", new_callable=AsyncMock):
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                data={"skip_ai": "true"},
                headers=auth_headers,
            )

        assert response.status_code == 201
        data = response.json()
        assert data["successful"] == 1
        assert data["failed"] == 1
        big, ok = data["results"]
        assert big["filename"] == "big.jpg"
        assert big["success"] is False
        assert "1 MB" in big["error"]
        assert ok["filename"] == "ok.jpg"
        assert ok["success"] is True
        assert await _item_count(db_session, test_user.id) == 1


class TestFeaturesUploadLimit:
    @pytest.mark.asyncio
    async def test_features_carries_the_upload_limit(self, client: AsyncClient):
        with patch("app.api.health.get_settings") as mock_settings:
            mock_settings.return_value.max_upload_size_mb = 37
            response = await client.get("/api/v1/health/features")

        assert response.status_code == 200
        assert response.json()["max_upload_size_mb"] == 37

    def test_default_limit_is_50_mb(self):
        assert Settings.model_fields["max_upload_size_mb"].default == 50
