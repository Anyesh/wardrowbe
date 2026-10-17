import pytest
from sqlalchemy import text

from app.models.outfit import Outfit
from app.models.user import User
from app.services.external_outfit_service import ExternalOutfitService
from app.services.suggestion_cache import has_cached, push_suggestions


@pytest.fixture
def make_outfit(db_session, make_item):
    async def _make(user: User) -> Outfit:
        items = [await make_item(user, type="top"), await make_item(user, type="bottom")]
        outfit = await ExternalOutfitService(db_session).create_suggestion(
            user=user, item_ids=[i.id for i in items], occasion="casual"
        )
        await db_session.commit()
        return outfit

    return _make


@pytest.mark.asyncio
async def test_list_and_get_outfit(call_tool, make_outfit, test_user):
    outfit = await make_outfit(test_user)
    listed = await call_tool("list_outfits", {"status": "pending"})
    assert [o["id"] for o in listed["outfits"]] == [str(outfit.id)]
    assert (await call_tool("list_outfits", {"status": "accepted"}))["total"] == 0
    result = await call_tool("get_outfit", {"outfit_id": str(outfit.id)})
    assert len(result["items"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "cache_kept"),
    [("accepted", True), ("rejected", False), ("skipped", False)],
)
async def test_respond_to_outfit_sets_status(
    call_tool, db_session, make_outfit, test_user, response, cache_kept
):
    outfit = await make_outfit(test_user)
    await push_suggestions(test_user.id, outfit.occasion, [{"items": [1], "headline": "cached"}])
    result = await call_tool(
        "respond_to_outfit", {"outfit_id": str(outfit.id), "response": response}
    )
    assert result["status"] == response
    await db_session.refresh(outfit)
    assert outfit.responded_at is not None
    assert await has_cached(test_user.id, outfit.occasion) is cache_kept


@pytest.mark.asyncio
async def test_submit_outfit_feedback(call_tool, make_outfit, test_user):
    outfit = await make_outfit(test_user)
    result = await call_tool(
        "submit_outfit_feedback",
        {"outfit_id": str(outfit.id), "accepted": True, "rating": 5, "worn": True},
    )
    assert result["accepted"] is True
    assert result["rating"] == 5
    stored = await call_tool("get_outfit", {"outfit_id": str(outfit.id)})
    assert stored["status"] == "accepted"
    item = await call_tool("get_item", {"item_id": stored["items"][0]["id"]})
    assert item["wear_count"] == 1


def _fail_learning(monkeypatch, target):
    calls = []

    async def failing(self, outfit_id, user_id):
        calls.append(outfit_id)
        await self.db.execute(text("SELECT 1/0"))

    monkeypatch.setattr(target, failing)
    return calls


@pytest.mark.asyncio
async def test_submit_outfit_feedback_survives_learning_failure(
    call_tool, db_session, make_outfit, test_user, monkeypatch
):
    calls = _fail_learning(monkeypatch, "app.mcp.tools.outfits.LearningService.process_feedback")
    outfit = await make_outfit(test_user)
    result = await call_tool(
        "submit_outfit_feedback", {"outfit_id": str(outfit.id), "rating": 4, "comment": "kept"}
    )
    assert result["rating"] == 4
    await db_session.refresh(outfit, ["feedback"])
    assert outfit.feedback.comment == "kept"
    assert calls == [outfit.id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "extra"),
    [
        ("get_outfit", {}),
        ("respond_to_outfit", {"response": "accepted"}),
        ("submit_outfit_feedback", {"rating": 3}),
    ],
)
async def test_outfit_tools_reject_foreign_outfit(
    call_tool_raw, make_outfit, other_user, tool, extra
):
    outfit = await make_outfit(other_user)
    result = await call_tool_raw(tool, {"outfit_id": str(outfit.id), **extra})
    assert result["isError"] is True
    assert "Outfit not found" in result["content"][0]["text"]
