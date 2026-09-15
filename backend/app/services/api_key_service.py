"""Creation and storage of user-owned API keys."""

import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import ApiKeyCreateRequest

API_KEY_PREFIX = "wrb_"


def hash_api_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


class ApiKeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, user_id: UUID, request: ApiKeyCreateRequest) -> tuple[ApiKey, str]:
        token = generate_api_key()
        api_key = ApiKey(
            user_id=user_id,
            name=request.name,
            token_hash=hash_api_key(token),
            scopes=list(request.scopes),
            expires_at=request.expires_at,
        )
        self.db.add(api_key)
        await self.db.flush()
        await self.db.refresh(api_key)
        return api_key, token

    async def list_for_user(self, user_id: UUID) -> list[ApiKey]:
        result = await self.db.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke(self, user_id: UUID, key_id: UUID) -> ApiKey | None:
        result = await self.db.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            return None
        if api_key.revoked_at is None:
            api_key.revoked_at = datetime.now(UTC)
            await self.db.flush()
            await self.db.refresh(api_key)
        return api_key

    async def authenticate_with_key(
        self, token: str, required_scope: str
    ) -> tuple[User, ApiKey] | None:
        if not token.startswith(API_KEY_PREFIX):
            return None

        result = await self.db.execute(
            select(ApiKey).where(ApiKey.token_hash == hash_api_key(token))
        )
        api_key = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if not api_key or api_key.revoked_at is not None:
            return None
        if api_key.expires_at is not None and api_key.expires_at <= now:
            return None
        if required_scope not in api_key.scopes:
            return None

        user = await self.db.get(User, api_key.user_id)
        if not user or not user.is_active:
            return None

        api_key.last_used_at = now
        await self.db.flush()
        return user, api_key

    async def authenticate(self, token: str, required_scope: str) -> User | None:
        authenticated = await self.authenticate_with_key(token, required_scope)
        return authenticated[0] if authenticated else None
