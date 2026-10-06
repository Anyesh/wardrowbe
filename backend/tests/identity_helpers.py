from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def identities_of(session: AsyncSession, user_id) -> set[tuple[str, str]]:
    rows = await session.execute(
        select(UserIdentity.provider, UserIdentity.subject).where(UserIdentity.user_id == user_id)
    )
    return set(rows.tuples().all())
