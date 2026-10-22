from io import BytesIO

import pytest
import pytest_asyncio
from PIL import Image

from app.config import Settings, get_settings
from app.utils import redis_lock
from app.utils.upload_tokens import issue_upload_token


def _jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), (20, 20, 20)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _mcp_enabled(monkeypatch):
    monkeypatch.setattr(
        "app.api.items.settings", Settings(mcp_enabled=True, ai_vision_enabled=False)
    )


@pytest_asyncio.fixture(autouse=True)
async def _redis_on_this_loop(monkeypatch):
    monkeypatch.setattr(redis_lock, "_redis_pool", None)
    yield
    if redis_lock._redis_pool is not None:
        await redis_lock._redis_pool.aclose()


async def _upload(client, token: str, content: bytes | None = None):
    return await client.post(
        f"/api/v1/items/uploads/{token}",
        files={"image": ("tee.jpg", content or _jpeg(), "image/jpeg")},
    )


@pytest.mark.asyncio
async def test_upload_link_creates_item_once(client, test_user):
    token = await issue_upload_token(test_user.id, {"name": "Black tee", "type": "t-shirt"}, True)
    first = await _upload(client, token)
    assert first.status_code == 201, first.text
    item = first.json()
    assert item["user_id"] == str(test_user.id)
    assert (item["name"], item["type"]) == ("Black tee", "t-shirt")
    assert (item["status"], item["tagging_status"]) == ("ready", "pending")
    assert (await _upload(client, token)).status_code == 404


@pytest.mark.asyncio
async def test_unknown_link_is_404(client):
    assert (await _upload(client, "not-a-token")).status_code == 404


@pytest.mark.asyncio
async def test_link_is_404_when_mcp_disabled(client, test_user, monkeypatch):
    token = await issue_upload_token(test_user.id, {}, True)
    monkeypatch.setattr("app.api.items.settings", Settings(mcp_enabled=False))
    assert (await _upload(client, token)).status_code == 404


@pytest.mark.asyncio
async def test_link_is_404_for_inactive_user(client, db_session, test_user):
    token = await issue_upload_token(test_user.id, {}, True)
    test_user.is_active = False
    await db_session.commit()
    assert (await _upload(client, token)).status_code == 404


@pytest.mark.asyncio
async def test_invalid_image_is_rejected(client, test_user):
    token = await issue_upload_token(test_user.id, {}, True)
    resp = await _upload(client, token, b"not an image")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_tool_link_round_trip(call_tool, client):
    link = await call_tool("create_item_upload", {"name": "Grey hoodie", "type": "hoodie"})
    assert link["field"] == "image"
    assert link["expires_in_seconds"] == 600
    path = link["upload_url"].removeprefix(get_settings().app_url)
    assert path.startswith("/api/v1/items/uploads/")
    resp = await _upload(client, path.rsplit("/", 1)[1])
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Grey hoodie"


@pytest.mark.asyncio
async def test_tool_validates_fields_before_issuing(call_tool_raw):
    result = await call_tool_raw("create_item_upload", {"name": "x" * 101})
    assert result["isError"] is True


@pytest.mark.asyncio
async def test_tool_refuses_without_app_url(call_tool_raw, monkeypatch):
    monkeypatch.setattr("app.mcp.tools.items.get_settings", lambda: Settings(app_url=""))
    result = await call_tool_raw("create_item_upload", {"name": "Grey hoodie"})
    assert result["isError"] is True
    assert "APP_URL" in result["content"][0]["text"]
