import pytest

from app.models.item import TaggingStatus


@pytest.mark.asyncio
async def test_set_item_tags_stamps_manual(call_tool, make_item, test_user):
    item = await make_item(test_user)
    result = await call_tool(
        "set_item_tags",
        {
            "item_id": str(item.id),
            "type": "top",
            "colors": ["black"],
            "primary_color": "black",
            "material": "cotton",
        },
    )
    assert result["tagging_status"] == "tagged"
    assert result["tagged_by"] == "manual"
    assert result["tags"]["material"] == "cotton"
    assert result["primary_color"] == "black"


@pytest.mark.asyncio
async def test_update_item_does_not_stamp(call_tool, make_item, test_user):
    item = await make_item(test_user)
    result = await call_tool("update_item", {"item_id": str(item.id), "notes": "hand-wash only"})
    assert result["notes"] == "hand-wash only"
    assert result["tagging_status"] == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "arguments"),
    [("set_item_tags", {}), ("update_item", {}), ("set_item_tags", {"type": "tights"})],
)
async def test_rejects_empty_or_invalid_input(
    call_tool_raw, make_item, db_session, test_user, tool, arguments
):
    item = await make_item(test_user)
    result = await call_tool_raw(tool, {"item_id": str(item.id), **arguments})
    assert result["isError"] is True
    await db_session.refresh(item)
    assert item.tagging_status == TaggingStatus.pending
