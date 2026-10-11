from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import select

from app.mcp import runtime
from app.mcp.auth import current_token
from app.models.user import User
from app.schemas.auth import IDENTITY_TOKEN, TokenPayload


@pytest.fixture(autouse=True)
def _session_maker(session_maker, monkeypatch):
    monkeypatch.setattr(runtime, "async_session_maker", session_maker)


@contextmanager
def _as_user(user_id: UUID | None, identity_id: UUID | None = None):
    payload = None
    if user_id is not None:
        payload = TokenPayload(
            sub=str(user_id), iid=str(identity_id or uuid4()), sub_type=IDENTITY_TOKEN, exp=0
        )
    reset = current_token.set(payload)
    try:
        yield
    finally:
        current_token.reset(reset)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "message"),
    [(None, "Not authenticated"), (uuid4(), "Unknown or inactive user")],
)
async def test_requires_a_known_user(user_id, message):
    with _as_user(user_id):
        with pytest.raises(ToolError, match=message):
            async with runtime.tool_context():
                pass


@pytest.mark.asyncio
async def test_resolves_user_and_commits(session_maker, test_user, test_user_identity):
    with _as_user(test_user.id, test_user_identity.id):
        async with runtime.tool_context() as ctx:
            assert ctx.user.id == test_user.id
            ctx.user.display_name = "Changed by tool"
    async with session_maker() as check:
        row = await check.execute(select(User).where(User.id == test_user.id))
        assert row.scalar_one().display_name == "Changed by tool"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "detail", ["Item not found", {"error_code": "NOT_FOUND", "message": "Item not found"}]
)
async def test_http_exception_becomes_tool_error_and_rolls_back(
    session_maker, test_user, test_user_identity, detail
):
    with _as_user(test_user.id, test_user_identity.id):
        with pytest.raises(ToolError, match="Item not found"):
            async with runtime.tool_context() as ctx:
                ctx.user.display_name = "Should not persist"
                raise HTTPException(status_code=404, detail=detail)
    async with session_maker() as check:
        row = await check.execute(select(User).where(User.id == test_user.id))
        assert row.scalar_one().display_name == "Test User"
