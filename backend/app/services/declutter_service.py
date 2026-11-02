"""Items that have sat unworn long enough to reconsider: never worn since they were added,
or not worn for the chosen number of months. "Keep" hides an item until the window passes
again; giving it away goes through the normal archive."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem, DeclutterKeep, ItemStatus
from app.models.user import User

DEFAULT_MONTHS = 6
MIN_MONTHS = 1
MAX_MONTHS = 36
DAYS_PER_MONTH = 30


@dataclass
class DeclutterCandidate:
    item: ClothingItem
    reason: str  # "never_worn" | "not_worn_recently"
    idle_days: int


def idle_since(item: ClothingItem) -> date | None:
    if item.last_worn_at:
        return item.last_worn_at
    if item.created_at:
        return item.created_at.date()
    return None


def find_candidates(
    items: list[ClothingItem],
    today: date,
    months: int,
    kept_until: dict[UUID, date] | None = None,
) -> list[DeclutterCandidate]:
    cutoff = today - timedelta(days=months * DAYS_PER_MONTH)
    kept_until = kept_until or {}
    candidates = []
    for item in items:
        keep = kept_until.get(item.id)
        if keep and keep > today:
            continue
        since = idle_since(item)
        if since is None or since > cutoff:
            continue
        reason = "not_worn_recently" if item.last_worn_at else "never_worn"
        candidates.append(
            DeclutterCandidate(item=item, reason=reason, idle_days=(today - since).days)
        )
    candidates.sort(key=lambda c: (c.reason != "never_worn", -c.idle_days))
    return candidates


def idle_value(candidates: list[DeclutterCandidate]) -> Decimal:
    return sum((c.item.purchase_price or Decimal(0) for c in candidates), Decimal(0))


class DeclutterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def active_items(self, user: User) -> list[ClothingItem]:
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
        return list(result.scalars().all())

    async def kept_until(self, user: User) -> dict[UUID, date]:
        rows = await self.db.execute(
            select(DeclutterKeep.item_id, DeclutterKeep.kept_until)
            .join(ClothingItem, ClothingItem.id == DeclutterKeep.item_id)
            .where(ClothingItem.user_id == user.id)
        )
        return dict(rows.tuples().all())

    async def keep(self, item: ClothingItem, today: date, months: int) -> date:
        until = today + timedelta(days=months * DAYS_PER_MONTH)
        statement = insert(DeclutterKeep).values(item_id=item.id, kept_until=until)
        await self.db.execute(
            statement.on_conflict_do_update(
                index_elements=[DeclutterKeep.item_id], set_={"kept_until": until}
            )
        )
        await self.db.flush()
        return until
