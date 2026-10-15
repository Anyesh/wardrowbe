"""Price watch for the shopping list: read each saved shop link again and note when the price
falls below the one the user saved."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user import User
from app.models.wishlist import WishlistItem
from app.services.link_preview import PreviewError, fetch_preview
from app.services.notification_providers import NotificationMessage

logger = logging.getLogger(__name__)

RECHECK_AFTER = timedelta(hours=20)
# Shops round and reformat prices; a cent off is not a sale.
MIN_DROP = Decimal("0.01")
PAUSE_BETWEEN_SHOPS_SECONDS = 1.0


@dataclass
class PriceDrop:
    entry: WishlistItem
    old: Decimal
    new: Decimal


def apply_price(entry: WishlistItem, price: Decimal | None, now: datetime) -> PriceDrop | None:
    """Store the shop's price; a drop is reported once per new low."""
    entry.price_checked_at = now
    if price is None:
        return None
    previous = entry.current_price
    entry.current_price = price
    if entry.price is None:
        entry.price = price
        return None
    dropped = entry.price - price >= MIN_DROP
    new_low = previous is None or price < previous
    if dropped and new_low:
        entry.price_dropped_at = now
        return PriceDrop(entry, entry.price, price)
    if not dropped:
        entry.price_dropped_at = None
    return None


def due_query(user_id=None, now: datetime | None = None):
    now = now or datetime.now(UTC)
    conditions = [
        WishlistItem.link.is_not(None),
        WishlistItem.bought.is_(False),
        or_(
            WishlistItem.price_checked_at.is_(None),
            WishlistItem.price_checked_at < now - RECHECK_AFTER,
        ),
    ]
    if user_id is not None:
        conditions.append(WishlistItem.user_id == user_id)
    return select(WishlistItem).where(and_(*conditions)).order_by(WishlistItem.price_checked_at)


async def check_prices(
    db: AsyncSession, entries: list[WishlistItem], pause: float = PAUSE_BETWEEN_SHOPS_SECONDS
) -> list[PriceDrop]:
    drops = []
    for index, entry in enumerate(entries):
        if index and pause:
            await asyncio.sleep(pause)
        try:
            preview = await fetch_preview(entry.link)
            price = preview.price
        except PreviewError as e:
            logger.info(f"Price check skipped for wishlist entry {entry.id}: {e}")
            price = None
        drop = apply_price(entry, price, datetime.now(UTC))
        if drop:
            drops.append(drop)
    await db.flush()
    return drops


def _money(value: Decimal) -> str:
    return f"{value:.2f} €"


def drop_message(user: User, drops: list[PriceDrop]) -> NotificationMessage:
    italian = (user.locale or "").startswith("it")
    lines = [f"{d.entry.name}: {_money(d.old)} → {_money(d.new)}" for d in drops[:5]]
    if italian:
        title = "Prezzo sceso" if len(drops) == 1 else f"{len(drops)} prezzi scesi"
        label = "Apri Cosa comprare"
    else:
        title = "Price drop" if len(drops) == 1 else f"{len(drops)} price drops"
        label = "Open shopping list"
    return NotificationMessage(
        title=title,
        body="\n".join(lines),
        url=get_settings().app_link("/dashboard/wishlist"),
        url_label=label,
        tags=["shopping_bags", "chart_with_downwards_trend"],
        data={"screen": "wishlist"},
    )
