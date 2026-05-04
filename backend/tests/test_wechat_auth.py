import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_wechat_miniapp_sync_creates_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={
            "openid": "openid-123",
            "display_name": "Mini User",
            "avatar_url": "https://example.com/a.png",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "openid-123@wechat-miniapp.local"
    assert data["display_name"] == "Mini User"
    assert data["access_token"]


@pytest.mark.asyncio
async def test_wechat_miniapp_sync_requires_identity(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={"display_name": "No ID"},
    )

    assert response.status_code == 422
