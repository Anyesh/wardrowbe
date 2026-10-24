from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.auth import create_access_token
from app.config import Settings
from app.mcp.auth import MCPAuthMiddleware, current_token


async def _echo_app(scope, receive, send):
    token = current_token.get()
    body = (token.sub if token else "").encode()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": body})


def _client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=MCPAuthMiddleware(_echo_app)),
        base_url="http://test",
    )


@pytest.fixture(autouse=True)
def _mcp_enabled(monkeypatch):
    monkeypatch.setattr("app.mcp.auth.get_settings", lambda: Settings(mcp_enabled=True))


@pytest.mark.asyncio
async def test_disabled_flag_returns_404(monkeypatch):
    monkeypatch.setattr("app.mcp.auth.get_settings", lambda: Settings(mcp_enabled=False))
    async with _client() as c:
        resp = await c.post("/")
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer bad"}]
)
async def test_rejects_missing_or_invalid_token(headers):
    async with _client() as c:
        resp = await c.post("/", headers=headers)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_valid_token_sets_contextvar_for_the_request_only():
    user_id = uuid4()
    token = create_access_token(user_id, uuid4())
    async with _client() as c:
        resp = await c.post("/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.text == str(user_id)
    assert current_token.get() is None
