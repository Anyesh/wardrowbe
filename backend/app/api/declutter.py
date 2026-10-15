from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.database import DbSession
from app.models.user import User
from app.schemas.item import ItemResponse
from app.services.declutter_service import (
    DEFAULT_MONTHS,
    MAX_MONTHS,
    MIN_MONTHS,
    DeclutterService,
    find_candidates,
    idle_value,
)
from app.services.item_service import ItemService
from app.utils.auth import get_current_user
from app.utils.timezone import get_user_today

router = APIRouter(prefix="/declutter", tags=["Declutter"])


class DeclutterCandidateResponse(BaseModel):
    item: ItemResponse
    reason: Literal["never_worn", "not_worn_recently"]
    idle_days: int


class DeclutterResponse(BaseModel):
    months: int
    total_items: int
    idle_value: Decimal
    candidates: list[DeclutterCandidateResponse]


class KeepRequest(BaseModel):
    months: int = Field(DEFAULT_MONTHS, ge=MIN_MONTHS, le=MAX_MONTHS)


class KeepResponse(BaseModel):
    item_id: UUID
    kept_until: date


@router.get("", response_model=DeclutterResponse)
async def declutter_review(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    months: int = Query(DEFAULT_MONTHS, ge=MIN_MONTHS, le=MAX_MONTHS),
) -> DeclutterResponse:
    service = DeclutterService(db)
    items = await service.active_items(current_user)
    candidates = find_candidates(
        items, get_user_today(current_user), months, await service.kept_until(current_user)
    )
    return DeclutterResponse(
        months=months,
        total_items=len(items),
        idle_value=idle_value(candidates),
        candidates=[
            DeclutterCandidateResponse(
                item=ItemResponse.model_validate(c.item), reason=c.reason, idle_days=c.idle_days
            )
            for c in candidates
        ],
    )


@router.post("/{item_id}/keep", response_model=KeepResponse)
async def keep_item(
    item_id: UUID,
    request: KeepRequest,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> KeepResponse:
    item = await ItemService(db).get_by_id(item_id, current_user.id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    until = await DeclutterService(db).keep(item, get_user_today(current_user), request.months)
    return KeepResponse(item_id=item.id, kept_until=until)
