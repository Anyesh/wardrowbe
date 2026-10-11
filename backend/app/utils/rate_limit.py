import ipaddress
import logging
from uuid import UUID

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    hops = get_settings().trusted_proxy_count
    if hops == 0:
        return peer

    # Repeated header lines are the same list as one comma-joined line, so a proxy that adds its
    # own line instead of appending to the client's still counts from the right.
    entries = [
        entry.strip()
        for line in request.headers.getlist("x-forwarded-for")
        for entry in line.split(",")
        if entry.strip()
    ]
    # Fewer entries than trusted proxies means the request skipped part of the chain, so any
    # entry may have been written by the client; the socket peer is the one address it cannot forge.
    if len(entries) < hops:
        return peer
    try:
        return str(ipaddress.ip_address(entries[-hops]))
    except ValueError:
        return peer


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    settings = get_settings()
    try:
        redis = Redis.from_url(str(settings.redis_url))
        try:
            # The window is fixed when the key is first created, because re-arming the expiry on
            # every hit would let a steady trickle keep the counter alive forever. SET NX rather
            # than EXPIRE NX so it works on Redis 6, where EXPIRE NX errors and limiting is lost.
            pipe = redis.pipeline(transaction=True)
            pipe.set(key, 0, ex=window_seconds, nx=True)
            pipe.incr(key)
            results = await pipe.execute()
            count = results[1]
            if count > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                )
        finally:
            await redis.aclose()
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Rate limit check failed (allowing request): %s", e)


async def rate_limit_by_ip(request: Request, action: str, limit: int, window_seconds: int) -> None:
    ip = _get_client_ip(request)
    key = f"rate_limit:{action}:ip:{ip}"
    await check_rate_limit(key, limit, window_seconds)


async def rate_limit_by_user(
    user_id: UUID, action: str, max_requests: int, window_seconds: int
) -> None:
    key = f"rate_limit:{action}:user:{user_id}"
    await check_rate_limit(key, max_requests, window_seconds)
