import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from redis.exceptions import LockNotOwnedError

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.from_url(
            str(settings.redis_url),
            decode_responses=True,
        )
    return _redis_pool


@asynccontextmanager
async def distributed_lock(key: str, timeout: int = 10, blocking_timeout: int = 5):
    r = await get_redis()
    lock = r.lock(key, timeout=timeout, blocking_timeout=blocking_timeout)
    acquired = False
    try:
        acquired = await lock.acquire()
        if not acquired:
            raise TimeoutError(f"Could not acquire lock: {key}")
        yield
    finally:
        if acquired:
            try:
                await lock.release()
            except LockNotOwnedError:
                logger.warning("Lock %s already released (expired?)", key)
