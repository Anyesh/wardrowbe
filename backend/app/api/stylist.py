import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import DbSession
from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.schemas.item import ItemResponse
from app.services.ai_service import AIDisabledError
from app.services.stylist_service import MAX_TURNS, ask_stylist
from app.services.user_ai import ai_service_for
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
    # The stylist uses the text model only: off when text AI is, whatever vision says.
    if not get_settings().effective_ai_text_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The AI is turned off"
        )
    try:
        ai = await ai_service_for(db, current_user.id)
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
        # Newest first: with more than MAX_ITEMS pieces, the recent ones are the ones shown.
        .order_by(ClothingItem.created_at.desc(), ClothingItem.id)
    )
    items = [i for i in result.scalars().all() if i.type and i.type != "unknown"]
    # Hand the connection back before waiting on the model.
    await db.commit()
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
    # A piece archived or deleted while the model was answering is not offered any more.
    still_there = set()
    if reply.items:
        still_there = set(
            await db.scalars(
                select(ClothingItem.id).where(
                    ClothingItem.id.in_([i.id for i in reply.items]),
                    ClothingItem.user_id == current_user.id,
                    ClothingItem.status == ItemStatus.ready,
                    ClothingItem.is_archived.is_(False),
                )
            )
        )
    return StylistResponse(
        reply=reply.text,
        items=[ItemResponse.model_validate(i) for i in reply.items if i.id in still_there],
    )
