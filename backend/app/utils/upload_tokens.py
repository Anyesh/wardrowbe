import json
import secrets
from uuid import UUID

from app.utils.redis_lock import get_redis

UPLOAD_TOKEN_TTL_SECONDS = 600
_KEY_PREFIX = "item_upload"


async def issue_upload_token(user_id: UUID, item: dict, skip_ai: bool) -> str:
    token = secrets.token_urlsafe(32)
    redis = await get_redis()
    await redis.set(
        f"{_KEY_PREFIX}:{token}",
        json.dumps({"user_id": str(user_id), "item": item, "skip_ai": skip_ai}),
        ex=UPLOAD_TOKEN_TTL_SECONDS,
    )
    return token


async def redeem_upload_token(token: str) -> dict | None:
    redis = await get_redis()
    raw = await redis.getdel(f"{_KEY_PREFIX}:{token}")
    return json.loads(raw) if raw else None
