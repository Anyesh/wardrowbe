import pytest

from app.mcp.server import MCPDispatchMiddleware


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/mcp", "/api/v1/mcp/"])
async def test_mcp_mount_404_when_disabled(client, auth_headers, path):
    resp = await client.post(path, json={}, headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mcp_mount_401_when_enabled_without_valid_token(client, monkeypatch):
    from app.config import Settings

    monkeypatch.setattr("app.mcp.auth.get_settings", lambda: Settings(mcp_enabled=True))
    resp = await client.post("/api/v1/mcp", json={})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_mcp_path_prefix_does_not_match_siblings(client, auth_headers):
    resp = await client.post("/api/v1/mcpx", json={}, headers=auth_headers)
    assert resp.status_code == 404
    assert resp.headers.get("www-authenticate") is None


@pytest.mark.asyncio
async def test_dispatch_honours_root_path():
    seen: dict = {}

    async def mcp_app(scope, receive, send):
        seen.update(path=scope["path"], root_path=scope["root_path"])

    async def fallback(scope, receive, send):
        seen.update(fallback=True)

    middleware = MCPDispatchMiddleware(fallback, mcp_app=mcp_app)
    scope = {"type": "http", "root_path": "/wardrobe", "path": "/wardrobe/api/v1/mcp"}
    await middleware(scope, None, None)
    assert seen == {"path": "/wardrobe/api/v1/mcp/", "root_path": "/wardrobe/api/v1/mcp"}


READ_ONLY_TOOLS = {
    "session_info",
    "get_wardrobe_summary",
    "list_items",
    "get_item",
    "get_item_image",
    "list_outfits",
    "get_outfit",
}


EXPECTED_TOOLS = {
    "session_info",
    "get_wardrobe_summary",
    "list_items",
    "get_item",
    "get_item_image",
    "create_item_upload",
    "set_item_tags",
    "update_item",
    "archive_item",
    "restore_item",
    "log_wear",
    "log_wash",
    "list_outfits",
    "get_outfit",
    "respond_to_outfit",
    "submit_outfit_feedback",
    "create_outfit_suggestion",
    "create_item_pairing",
    "create_outfit",
}


@pytest.mark.asyncio
async def test_tools_list_names(mcp_call):
    resp = await mcp_call("tools/list")
    assert resp.status_code == 200, resp.text
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert names == EXPECTED_TOOLS


@pytest.mark.asyncio
async def test_session_info(call_tool, test_user):
    result = await call_tool("session_info")
    assert result["user"]["email"] == test_user.email
    assert result["user"]["timezone"] == "UTC"
    assert set(result["ai"]) == {"vision", "text"}


@pytest.mark.asyncio
async def test_read_tools_carry_read_only_hint(mcp_call):
    resp = await mcp_call("tools/list")
    assert resp.status_code == 200, resp.text
    tools = {t["name"]: t for t in resp.json()["result"]["tools"]}
    for name, tool in tools.items():
        read_only = tool.get("annotations", {}).get("readOnlyHint", False)
        assert read_only == (name in READ_ONLY_TOOLS), name
