import pytest

from app.models.item import TaggingStatus


@pytest.mark.asyncio
async def test_get_wardrobe_summary(call_tool, make_item, test_user):
    await make_item(test_user, type="top")
    await make_item(test_user, type="bottom", tagging_status=TaggingStatus.tagged)
    await make_item(test_user, type="top", needs_wash=True)
    await make_item(test_user, type="coat", needs_wash=True, is_archived=True)
    result = await call_tool("get_wardrobe_summary")
    assert result["total_items"] == 3
    assert result["items_pending_tagging"] == 2
    assert result["items_needing_wash"] == 1
    assert {t["type"] for t in result["types"]} == {"top", "bottom"}
