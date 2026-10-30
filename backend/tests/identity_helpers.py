from datetime import datetime, timedelta
from uuid import UUID, uuid4

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User, UserIdentity


async def add_users_with_identities(
    session: AsyncSession, *users: User, provider: str = "legacy"
) -> list[UserIdentity]:
    # Each identity's subject is the user's external_id, as the migration's backfill wrote them.
    session.add_all(users)
    await session.flush()
    identities = [
        UserIdentity(id=uuid4(), user_id=user.id, provider=provider, subject=user.external_id)
        for user in users
    ]
    session.add_all(identities)
    await session.flush()
    return identities


async def identity_ids_of(session: AsyncSession, user_id) -> dict[tuple[str, str], UUID]:
    rows = await session.execute(
        select(UserIdentity.provider, UserIdentity.subject, UserIdentity.id).where(
            UserIdentity.user_id == user_id
        )
    )
    return {(provider, subject): id_ for provider, subject, id_ in rows.tuples()}


async def identities_of(session: AsyncSession, user_id) -> set[tuple[str, str]]:
    return set(await identity_ids_of(session, user_id))


async def user_of_subject(session: AsyncSession, subject: str) -> User | None:
    return await session.scalar(
        select(User)
        .join(UserIdentity, UserIdentity.user_id == User.id)
        .where(UserIdentity.subject == subject)
        .execution_options(populate_existing=True)
    )


def legacy_token(external_id: str) -> str:
    # The format main minted before identities existed: sub is the external_id, no sub_type.
    now = datetime.utcnow()
    return jwt.encode(
        {"sub": external_id, "exp": now + timedelta(days=7), "iat": now},
        get_settings().secret_key,
        algorithm="HS256",
    )
