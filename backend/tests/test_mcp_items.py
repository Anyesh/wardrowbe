import pytest

from app.models.item import TaggingStatus
from app.services import image_service


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filters", "matching"),
    [
        ({"tagging_status": "pending"}, {}),
        ({"needs_wash": True}, {"needs_wash": True, "tagging_status": TaggingStatus.tagged}),
    ],
)
async def test_list_items_filters(call_tool, make_item, test_user, filters, matching):
    expected = await make_item(test_user, **matching)
    await make_item(test_user, tagging_status=TaggingStatus.tagged)
    result = await call_tool("list_items", filters)
    assert [i["id"] for i in result["items"]] == [str(expected.id)]


@pytest.mark.asyncio
async def test_get_item_returns_signed_urls(call_tool, make_item, test_user):
    item = await make_item(test_user)
    result = await call_tool("get_item", {"item_id": str(item.id)})
    assert result["id"] == str(item.id)
    assert result["image_url"].startswith("/api/v1/images/")


@pytest.mark.asyncio
async def test_get_item_foreign_item_is_tool_error(call_tool_raw, make_item, other_user):
    foreign = await make_item(other_user)
    result = await call_tool_raw("get_item", {"item_id": str(foreign.id)})
    assert result["isError"] is True
    assert "Item not found" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_item_image_reads_storage(
    call_tool_raw, make_item, test_user, tmp_path, monkeypatch
):
    monkeypatch.setattr(image_service.settings, "storage_path", str(tmp_path))
    item = await make_item(test_user)
    file_path = tmp_path / item.image_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    result = await call_tool_raw("get_item_image", {"item_id": str(item.id), "variant": "full"})
    assert not result.get("isError"), result
    assert result["content"][0]["type"] == "image"
