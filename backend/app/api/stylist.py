import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.database import DbSession
from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.schemas.item import ItemResponse
from app.services.ai_service import AIDisabledError, get_ai_service
from app.services.stylist_service import MAX_TURNS, ask_stylist
from app.utils.auth import get_current_user
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stylist", tags=["Stylist"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class StylistRequest(BaseModel):
    messages: list[Turn] = Field(min_length=1, max_length=MAX_TURNS)


class StylistResponse(BaseModel):
    reply: str
    items: list[ItemResponse]


@router.post("", response_model=StylistResponse)
async def chat_with_stylist(
    request: StylistRequest,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> StylistResponse:
    if request.messages[-1].role != "user":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The last message must come from the user",
        )
    try:
        ai = get_ai_service()
    except AIDisabledError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The AI is turned off"
        ) from None

    result = await db.execute(
        select(ClothingItem)
        .where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.status == ItemStatus.ready,
                ClothingItem.is_archived.is_(False),
            )
        )
        .options(selectinload(ClothingItem.additional_images))
        .order_by(ClothingItem.created_at, ClothingItem.id)
    )
    items = [i for i in result.scalars().all() if i.type and i.type != "unknown"]
    context = f"today is {get_user_today(current_user).isoformat()}"
    if current_user.location_name:
        context += f", the user lives in {current_user.location_name}"

    try:
        reply = await ask_stylist(
            ai, items, [turn.model_dump() for turn in request.messages], context
        )
    except Exception as e:
        logger.warning(f"Stylist chat failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI could not answer. Try again in a moment.",
        ) from None
    return StylistResponse(
        reply=reply.text, items=[ItemResponse.model_validate(i) for i in reply.items]
    )
