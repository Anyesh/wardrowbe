from io import BytesIO
from unittest.mock import MagicMock, patch
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

BLUE = (0, 0, 255)


def _jpeg_bytes(size: tuple[int, int] = (400, 600)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (10, 200, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def _mock_provider():
    provider = MagicMock()
    provider.remove.side_effect = lambda img: Image.new("RGBA", img.size, (*BLUE, 255))
    return provider


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
        response = await client.post(
            f"/api/v1/items/{uuid4()}/remove-background",
            json={},
            headers=auth_headers,
        )
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

        response = await client.post(
            f"/api/v1/items/{item.id}/remove-background",
            json={},
            headers=auth_headers,
        )
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
    async def test_409_when_live_job_owns_the_item(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        # A queued or running background-removal (or tagging) job owns
        # image_path/medium_path/thumbnail_path - racing it here would stomp
        # whichever write lands last.
        item = await _make_item(
            db_session,
            test_user,
            status=ItemStatus.processing,
            ai_job_id="live-job-id",
        )
        item_id = item.id

        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            response = await client.post(
                f"/api/v1/items/{item_id}/remove-background",
                json={},
                headers=auth_headers,
            )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_orphaned_processing_item_not_blocked(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        # processing with no ai_job_id means no live job actually owns the
        # files (a prior enqueue silently failed) - must not be blocked.
        item = await _make_item(
            db_session,
            test_user,
            status=ItemStatus.processing,
            ai_job_id=None,
        )

        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            response = await client.post(
                f"/api/v1/items/{item.id}/remove-background",
                json={},
                headers=auth_headers,
            )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_error_kind_item_recovers_to_ready(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(
            db_session,
            test_user,
            status=ItemStatus.error,
            processing_kind="background_removal",
        )
        item_id = item.id

        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            response = await client.post(
                f"/api/v1/items/{item_id}/remove-background",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ready"

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        refreshed = result.scalar_one()
        assert refreshed.status == ItemStatus.ready
        assert refreshed.processing_kind is None
        assert refreshed.ai_started_at is None

    @pytest.mark.asyncio
    async def test_ordinary_ready_item_unaffected(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = await _make_item(db_session, test_user, status=ItemStatus.ready)
        item_id = item.id

        with patch("app.services.background_removal.get_provider", return_value=_mock_provider()):
            response = await client.post(
                f"/api/v1/items/{item_id}/remove-background",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ready"

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        refreshed = result.scalar_one()
        assert refreshed.status == ItemStatus.ready
        assert refreshed.processing_kind is None


class TestHealthFeatures:
    @pytest.mark.asyncio
    async def test_features_endpoint(self, client: AsyncClient):
        response = await client.get("/api/v1/health/features")
        assert response.status_code == 200
        data = response.json()
        assert "background_removal" in data
        assert isinstance(data["background_removal"], bool)
