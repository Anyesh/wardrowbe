import pytest

from app.utils.timezone import get_user_today


@pytest.mark.asyncio
async def test_archive_and_restore(call_tool, make_item, test_user):
    item = await make_item(test_user)
    archived = await call_tool("archive_item", {"item_id": str(item.id), "reason": "seasonal"})
    assert archived["status"] == "archived"
    restored = await call_tool("restore_item", {"item_id": str(item.id)})
    assert restored["status"] == "ready"


@pytest.mark.asyncio
async def test_log_wear_defaults_to_user_today(call_tool, make_item, test_user):
    item = await make_item(test_user)
    result = await call_tool("log_wear", {"item_id": str(item.id), "occasion": "Office"})
    assert result["wear_count"] == 1
    assert result["last_worn_at"] == get_user_today(test_user).isoformat()


@pytest.mark.asyncio
async def test_log_wear_rejects_unknown_occasion(call_tool_raw, make_item, test_user):
    item = await make_item(test_user)
    result = await call_tool_raw("log_wear", {"item_id": str(item.id), "occasion": "gala"})
    assert result["isError"] is True
    assert "Invalid occasion" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_log_wash_resets_wear_since_wash(call_tool, make_item, test_user):
    item = await make_item(test_user, wears_since_wash=3, needs_wash=True)
    result = await call_tool("log_wash", {"item_id": str(item.id), "method": "machine"})
    assert result["wears_since_wash"] == 0
    assert result["needs_wash"] is False


@pytest.mark.asyncio
async def test_log_wash_rejects_clean_item(call_tool_raw, make_item, test_user):
    item = await make_item(test_user)
    result = await call_tool_raw("log_wash", {"item_id": str(item.id)})
    assert result["isError"] is True
    assert "already clean" in result["content"][0]["text"]
