import pytest
from sqlalchemy import select, text

from app.config import Settings
from app.models.outfit import Outfit


@pytest.mark.asyncio
async def test_create_outfit_suggestion(call_tool, make_item, test_user):
    top = await make_item(test_user, type="top")
    bottom = await make_item(test_user, type="bottom")
    result = await call_tool(
        "create_outfit_suggestion",
        {
            "items": [str(top.id), str(bottom.id)],
            "occasion": "casual",
            "season": "autumn",
            "palette": ["black", "grey"],
        },
    )
    assert result["source"] == "external"
    assert result["status"] == "pending"
    assert [i["position"] for i in result["items"]] == [0, 1]
    assert result["season"] == "autumn"


@pytest.mark.asyncio
async def test_create_item_pairing_prepends_source(call_tool, make_item, test_user):
    source = await make_item(test_user, type="top")
    partner = await make_item(test_user, type="bottom")
    result = await call_tool(
        "create_item_pairing",
        {"source_item_id": str(source.id), "items": [str(partner.id)]},
    )
    assert result["occasion"] == "pairing"
    assert result["source_item"]["id"] == str(source.id)


@pytest.mark.asyncio
async def test_create_outfit_studio(call_tool, make_item, test_user):
    top = await make_item(test_user, type="top")
    result = await call_tool(
        "create_outfit", {"items": [str(top.id)], "occasion": "casual", "mark_worn": True}
    )
    assert result["source"] == "manual"
    assert result["feedback"]["worn_at"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "source_owned", "message"),
    [
        ("create_outfit_suggestion", None, "do not belong"),
        ("create_outfit", None, "do not belong"),
        ("create_item_pairing", True, "do not belong"),
        ("create_item_pairing", False, "Source item not found"),
    ],
)
async def test_authoring_rejects_foreign_items(
    call_tool_raw, make_item, test_user, other_user, tool, source_owned, message
):
    foreign = await make_item(other_user)
    arguments = {"items": [str(foreign.id)], "occasion": "casual"}
    if source_owned is not None:
        source = await make_item(test_user if source_owned else other_user)
        arguments = {"source_item_id": str(source.id), "items": [str(foreign.id)]}
    result = await call_tool_raw(tool, arguments)
    assert result["isError"] is True
    assert message in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_create_outfit_respects_studio_kill_switch(
    call_tool_raw, make_item, test_user, monkeypatch
):
    monkeypatch.setattr(
        "app.mcp.tools.authoring.get_settings",
        lambda: Settings(mcp_enabled=True, studio_disabled=True),
    )
    top = await make_item(test_user)
    result = await call_tool_raw("create_outfit", {"items": [str(top.id)], "occasion": "casual"})
    assert result["isError"] is True
    assert "studio" in result["content"][0]["text"].lower()


def _fail_learning(monkeypatch, target):
    calls = []

    async def failing(self, outfit_id, user_id):
        calls.append(outfit_id)
        await self.db.execute(text("SELECT 1/0"))

    monkeypatch.setattr(target, failing)
    return calls


@pytest.mark.asyncio
async def test_create_outfit_survives_learning_failure(
    call_tool, db_session, make_item, test_user, monkeypatch
):
    calls = _fail_learning(monkeypatch, "app.mcp.tools.authoring.LearningService.process_feedback")
    top = await make_item(test_user, type="top")
    result = await call_tool("create_outfit", {"items": [str(top.id)], "occasion": "casual"})
    assert await db_session.scalar(select(Outfit).where(Outfit.id == result["id"])) is not None
    assert [str(c) for c in calls] == [result["id"]]
