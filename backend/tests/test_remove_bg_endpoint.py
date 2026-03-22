from uuid import uuid4

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.schemas.item import RemoveBackgroundRequest


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


class TestHealthFeatures:
    @pytest.mark.asyncio
    async def test_features_endpoint(self, client: AsyncClient):
        response = await client.get("/api/v1/health/features")
        assert response.status_code == 200
        data = response.json()
        assert "background_removal" in data
        assert isinstance(data["background_removal"], bool)
