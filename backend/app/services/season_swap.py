"""Seasonal wardrobe swap: what to put away and what to bring out for the coming months.

An item's own season tags decide first. An item without tags falls back on history: worn in
the same weeks last year means it belongs to the coming season. Anything worn in the last
few weeks stays out, whatever its tags say."""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem, ItemHistory, ItemStatus
from app.models.user import User
from app.services.item_scorer import get_season

LOOK_AHEAD_DAYS = 60
# Last year's wears inside this window around the same date mark an untagged item as seasonal.
HISTORY_WINDOW = (timedelta(days=15), timedelta(days=105))
STILL_IN_USE_DAYS = 21
ALL_SEASONS = {"all-season", "spring", "summer", "fall", "winter"}


@dataclass
class SwapPlan:
    current: str
    upcoming: str
    put_away: list[tuple[ClothingItem, str]]
    bring_out: list[tuple[ClothingItem, str]]
    stays: int


def seasons_ahead(today: date, latitude: float | None) -> tuple[str, str]:
    current = get_season(today.month, latitude)
    upcoming = get_season((today + timedelta(days=LOOK_AHEAD_DAYS)).month, latitude)
    return current, upcoming


def plan_swap(
    items: list[ClothingItem],
    today: date,
    latitude: float | None,
    last_year_worn: set[UUID],
) -> SwapPlan:
    current, upcoming = seasons_ahead(today, latitude)
    wanted = {current, upcoming}
    recent_cutoff = today - timedelta(days=STILL_IN_USE_DAYS)
    put_away: list[tuple[ClothingItem, str]] = []
    bring_out: list[tuple[ClothingItem, str]] = []
    stays = 0
    for item in items:
        tags = {s for s in (item.season or []) if s in ALL_SEASONS}
        in_use = item.last_worn_at is not None and item.last_worn_at >= recent_cutoff
        if not tags or "all-season" in tags:
            if not tags and item.id in last_year_worn and not in_use:
                bring_out.append((item, "last_year"))
            else:
                stays += 1
            continue
        if upcoming != current and upcoming in tags and current not in tags and not in_use:
            bring_out.append((item, "season"))
        elif not tags & wanted and not in_use:
            put_away.append((item, "season"))
        else:
            stays += 1
    return SwapPlan(current, upcoming, put_away, bring_out, stays)


class SeasonSwapService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def plan(self, user: User, today: date) -> SwapPlan:
        result = await self.db.execute(
            select(ClothingItem)
            .where(
                and_(
                    ClothingItem.user_id == user.id,
                    ClothingItem.status == ItemStatus.ready,
                    ClothingItem.is_archived.is_(False),
                )
            )
            .options(selectinload(ClothingItem.additional_images))
        )
        items = [i for i in result.scalars().all() if i.type and i.type != "unknown"]
        start = today - timedelta(days=365) + HISTORY_WINDOW[0]
        end = today - timedelta(days=365) + HISTORY_WINDOW[1]
        worn = await self.db.scalars(
            select(ItemHistory.item_id)
            .join(ClothingItem, ClothingItem.id == ItemHistory.item_id)
            .where(
                ClothingItem.user_id == user.id,
                ItemHistory.worn_at >= start,
                ItemHistory.worn_at <= end,
            )
        )
        latitude = float(user.location_lat) if user.location_lat is not None else None
        return plan_swap(items, today, latitude, set(worn))
