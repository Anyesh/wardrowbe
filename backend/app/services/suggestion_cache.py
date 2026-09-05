import json
import logging

from app.utils.redis_lock import get_redis

logger = logging.getLogger(__name__)

CACHE_TTL = 3600
KEY_PREFIX = "suggest"


def _cache_key(user_id, occasion, include_items: list | None = None) -> str:
    if include_items:
        items_part = ":".join(sorted(str(i) for i in include_items))
        return f"{KEY_PREFIX}:{user_id}:{occasion}:{items_part}"
    return f"{KEY_PREFIX}:{user_id}:{occasion}"


async def push_suggestions(
    user_id, occasion, suggestions: list[dict], include_items: list | None = None
) -> None:
    try:
        redis = await get_redis()
        key = _cache_key(user_id, occasion, include_items=include_items)
        pipe = redis.pipeline()
        for s in suggestions:
            pipe.rpush(key, json.dumps(s))
        pipe.expire(key, CACHE_TTL)
        await pipe.execute()
    except Exception:
        logger.warning("Failed to push suggestions to cache", exc_info=True)


async def pop_suggestion(
    user_id, occasion, include_items: list | None = None
) -> dict | None:
    try:
        redis = await get_redis()
        key = _cache_key(user_id, occasion, include_items=include_items)
        raw = await redis.lpop(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.warning("Failed to pop suggestion from cache", exc_info=True)
        return None


async def clear_suggestions(
    user_id, occasion, include_items: list | None = None
) -> None:
    try:
        redis = await get_redis()
        base_key = _cache_key(user_id, occasion, include_items=include_items)
        await redis.delete(base_key)
        if include_items is None:
            scan_iter = getattr(redis, "scan_iter", None)
            if callable(scan_iter):
                async for key in scan_iter(f"{base_key}:*"):
                    await redis.delete(key)
    except Exception:
        logger.warning("Failed to clear suggestion cache", exc_info=True)


async def has_cached(
    user_id, occasion, include_items: list | None = None
) -> bool:
    try:
        redis = await get_redis()
        key = _cache_key(user_id, occasion, include_items=include_items)
        length = await redis.llen(key)
        return length > 0
    except Exception:
        logger.warning("Failed to check suggestion cache", exc_info=True)
        return False
