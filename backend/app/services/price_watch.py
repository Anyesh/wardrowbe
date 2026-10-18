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
    # The shop price before this check, put back when the alert cannot be delivered so the
    # next check reports the same drop again.
    previous: Decimal | None = None


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
        return PriceDrop(entry, entry.price, price, previous)
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
    # Never-checked links first: with NULLs last, a long list would keep re-reading the same
    # batch of old links and never reach the new ones.
    return (
        select(WishlistItem)
        .where(and_(*conditions))
        .order_by(WishlistItem.price_checked_at.asc().nulls_first())
    )


async def check_prices(
    db: AsyncSession, entries: list[WishlistItem], pause: float = PAUSE_BETWEEN_SHOPS_SECONDS
) -> list[PriceDrop]:
    drops = []
    for index, entry in enumerate(entries):
        if index and pause:
            await asyncio.sleep(pause)
        link = entry.link
        try:
            preview = await fetch_preview(link)
            price = preview.price
        except PreviewError as e:
            logger.info(f"Price check skipped for wishlist entry {entry.id}: {e}")
            price = None
        # The user may have edited the entry while the shop page was loading: compare against
        # the reference price saved now, and drop the result if the link changed or it was bought.
        await db.refresh(entry, ["price", "current_price", "link", "bought"])
        if entry.link != link or entry.bought:
            continue
        drop = apply_price(entry, price, datetime.now(UTC))
        if drop:
            drops.append(drop)
    await db.flush()
    return drops


def _money(value: Decimal) -> str:
    return f"{value:.2f} €"


# (one drop, several drops with {count}, button label) per supported locale.
DROP_TEXTS: dict[str, tuple[str, str, str]] = {
    "en": ("Price drop", "{count} price drops", "Open shopping list"),
    "it": ("Prezzo sceso", "{count} prezzi scesi", "Apri Cosa comprare"),
    "de": ("Preis gesunken", "{count} Preise gesunken", "Einkaufsliste öffnen"),
    "fr": ("Baisse de prix", "{count} baisses de prix", "Ouvrir la liste d'achats"),
    "ja": ("値下がり", "{count}件の値下がり", "買い物リストを開く"),
    "ko": ("가격 인하", "가격 인하 {count}건", "쇼핑 목록 열기"),
    "zh-CN": ("降价", "{count} 件降价", "打开购物清单"),
    "zh-TW": ("降價", "{count} 件降價", "開啟購物清單"),
}


def drop_texts(locale: str | None) -> tuple[str, str, str]:
    """Exact locale first (zh-TW), then its language (it-IT -> it), English otherwise."""
    locale = (locale or "").replace("_", "-")
    if locale in DROP_TEXTS:
        return DROP_TEXTS[locale]
    if locale.lower().startswith("zh"):
        traditional = any(tag in locale.lower() for tag in ("tw", "hk", "hant"))
        return DROP_TEXTS["zh-TW" if traditional else "zh-CN"]
    return DROP_TEXTS.get(locale.split("-")[0].lower(), DROP_TEXTS["en"])


def drop_message(user: User, drops: list[PriceDrop]) -> NotificationMessage:
    lines = [f"{d.entry.name}: {_money(d.old)} → {_money(d.new)}" for d in drops[:5]]
    one, several, label = drop_texts(user.locale)
    title = one if len(drops) == 1 else several.format(count=len(drops))
    return NotificationMessage(
        title=title,
        body="\n".join(lines),
        url=get_settings().app_link("/dashboard/wishlist"),
        url_label=label,
        tags=["shopping_bags", "chart_with_downwards_trend"],
        data={"screen": "wishlist"},
    )
