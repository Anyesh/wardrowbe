from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from fastapi import HTTPException
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.mcp.auth import current_token
from app.models.user import User
from app.services.user_service import UserService

ModelT = TypeVar("ModelT", bound=BaseModel)

READ_ONLY = ToolAnnotations(read_only_hint=True)


@dataclass
class ToolContext:
    db: AsyncSession
    user: User


def validated(model_cls: type[ModelT], payload: dict) -> ModelT:
    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        raise ToolError(str(exc)) from exc


def present(**fields: Any) -> dict[str, Any]:
    return {k: v for k, v in fields.items() if v is not None}


def _detail_message(exc: HTTPException) -> str:
    if isinstance(exc.detail, dict):
        return str(exc.detail.get("message") or exc.detail)
    return str(exc.detail)


@asynccontextmanager
async def tool_context():
    token = current_token.get()
    if token is None:
        raise ToolError("Not authenticated")
    async with async_session_maker() as session:
        user = await UserService(session).get_by_token(token)
        if user is None or not user.is_active:
            raise ToolError("Unknown or inactive user")
        try:
            yield ToolContext(db=session, user=user)
        except HTTPException as exc:
            await session.rollback()
            raise ToolError(_detail_message(exc)) from exc
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
