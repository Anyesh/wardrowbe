import httpx
import pytest
from httpx import AsyncClient

from app.api import auth
from app.utils.auth import decode_token


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
    assert decode_token(data["access_token"]).sub == "wechat-miniapp:openid:openid-123"


@pytest.mark.asyncio
async def test_wechat_miniapp_sync_requires_identity(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={"display_name": "No ID"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_wechat_miniapp_sync_rejects_missing_code_in_non_dev_mode(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(auth.settings, "debug", False)
    monkeypatch.setattr(auth.settings, "secret_key", "not-the-default-test-secret")
    monkeypatch.setattr(auth.settings, "wechat_miniapp_appid", "app-id")
    monkeypatch.setattr(auth.settings, "wechat_miniapp_secret", "app-secret")

    response = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={"openid": "attacker-openid", "display_name": "No Code"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wechat_miniapp_sync_exchanges_code_in_non_dev_mode(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(auth.settings, "debug", False)
    monkeypatch.setattr(auth.settings, "secret_key", "not-the-default-test-secret")
    monkeypatch.setattr(auth.settings, "wechat_miniapp_appid", "app-id")
    monkeypatch.setattr(auth.settings, "wechat_miniapp_secret", "app-secret")

    async def mock_get(self, url, params):
        assert url == "https://api.weixin.qq.com/sns/jscode2session"
        assert params == {
            "appid": "app-id",
            "secret": "app-secret",
            "js_code": "login-code",
            "grant_type": "authorization_code",
        }
        return httpx.Response(200, json={"openid": "verified-openid"})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    response = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={
            "code": "login-code",
            "openid": "untrusted-openid",
            "display_name": "Verified Mini User",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "verified-openid@wechat-miniapp.local"
    assert data["display_name"] == "Verified Mini User"
    assert decode_token(data["access_token"]).sub == "wechat-miniapp:openid:verified-openid"


@pytest.mark.asyncio
async def test_wechat_miniapp_sync_rejects_wechat_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(auth.settings, "debug", False)
    monkeypatch.setattr(auth.settings, "secret_key", "not-the-default-test-secret")
    monkeypatch.setattr(auth.settings, "wechat_miniapp_appid", "app-id")
    monkeypatch.setattr(auth.settings, "wechat_miniapp_secret", "app-secret")

    async def mock_get(self, url, params):
        return httpx.Response(200, json={"errcode": 40029, "errmsg": "invalid code"})

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    response = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={"code": "bad-code", "display_name": "Rejected"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wechat_miniapp_sync_rejects_too_long_subject(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={"openid": "x" * 201, "display_name": "Too Long"},
    )

    assert response.status_code == 422
