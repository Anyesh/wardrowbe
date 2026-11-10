from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.database import DbSession
from app.models.user import User
from app.schemas.item import ItemResponse
from app.services.season_swap import SeasonSwapService
from app.utils.auth import get_current_user
from app.utils.timezone import get_user_today

router = APIRouter(prefix="/season-swap", tags=["Season swap"])


class SwapEntry(BaseModel):
    item: ItemResponse
    reason: Literal["season", "last_year"]


class SwapResponse(BaseModel):
    current_season: str
    upcoming_season: str
    put_away: list[SwapEntry]
    bring_out: list[SwapEntry]
    stays: int


@router.get("", response_model=SwapResponse)
async def season_swap(
    db: DbSession, current_user: Annotated[User, Depends(get_current_user)]
) -> SwapResponse:
    plan = await SeasonSwapService(db).plan(current_user, get_user_today(current_user))
    return SwapResponse(
        current_season=plan.current,
        upcoming_season=plan.upcoming,
        put_away=[
            SwapEntry(item=ItemResponse.model_validate(i), reason=r) for i, r in plan.put_away
        ],
        bring_out=[
            SwapEntry(item=ItemResponse.model_validate(i), reason=r) for i, r in plan.bring_out
        ],
        stays=plan.stays,
    )
