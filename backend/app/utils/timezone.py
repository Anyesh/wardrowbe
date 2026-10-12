import logging
from datetime import UTC, date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models import User

logger = logging.getLogger(__name__)


def _load_zone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def is_valid_timezone(name: str | None) -> bool:
    return _load_zone(name) is not None


# Cached so that a bad stored zone warns once per process instead of on every
# minute's schedule check.
@lru_cache(maxsize=256)
def resolve_timezone(name: str | None) -> ZoneInfo:
    zone = _load_zone(name)
    if zone is not None:
        return zone
    if name:
        logger.warning("Unknown timezone %r, using UTC", name)
    return ZoneInfo("UTC")


def get_user_timezone(user: User) -> ZoneInfo:
    return resolve_timezone(user.timezone)


def get_user_now(user: User) -> datetime:
    return datetime.now(UTC).astimezone(get_user_timezone(user))


def get_user_today(user: User) -> date:
    return get_user_now(user).date()
