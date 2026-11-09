import logging
from collections import defaultdict

from app.models.notification import NotificationStatus
from app.models.user import User
from app.services.notification_service import NotificationDispatcher
from app.services.price_watch import check_prices, drop_message, due_query
from app.utils.redis_lock import distributed_lock
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)

# One daily pass; shops are read one at a time with a pause, so a long list spreads over days.
MAX_PER_RUN = 200


async def check_wishlist_prices(ctx: dict) -> dict:
    try:
        async with distributed_lock("wishlist-prices-cron", timeout=3600, blocking_timeout=0):
            return await _check_wishlist_prices(ctx)
    except TimeoutError:
        logger.debug("Skipping wishlist price check - another worker holds the lock")
        return {"checked": 0, "skipped": "lock_held"}


async def _check_wishlist_prices(ctx: dict) -> dict:
    db = get_db_session(ctx)
    try:
        entries = list((await db.scalars(due_query().limit(MAX_PER_RUN))).all())
        if not entries:
            return {"checked": 0, "drops": 0}
        drops = await check_prices(db, entries)
        await db.commit()

        by_user: dict = defaultdict(list)
        for drop in drops:
            by_user[drop.entry.user_id].append(drop)
        dispatcher = NotificationDispatcher(db)
        for user_id, user_drops in by_user.items():
            user = await db.get(User, user_id)
            if user is None:
                continue
            try:
                results = await dispatcher.deliver(user_id, drop_message(user, user_drops))
                # No channel set up is not a failure: the drop still shows on the page.
                failed = bool(results) and not any(
                    r.status == NotificationStatus.sent for r in results
                )
            except Exception as e:
                logger.warning(f"Price drop notification failed for {user_id}: {e}")
                failed = True
            if failed:
                # Put the old shop price back so the next check sees the same drop as new and
                # tries the alert again, instead of it being lost.
                for drop in user_drops:
                    drop.entry.current_price = drop.previous
                await db.commit()
        logger.info(f"Wishlist prices: checked {len(entries)}, {len(drops)} drops")
        return {"checked": len(entries), "drops": len(drops)}
    finally:
        await db.close()
