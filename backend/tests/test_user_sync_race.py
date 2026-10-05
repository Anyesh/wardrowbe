import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import User
from app.schemas.user import UserSyncRequest
from app.services.user_service import UserEmailConflictError, UserService


@pytest.fixture
def session_maker(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _wait_until_blocked_by(session_maker, waiter_pid: int, holder_pid: int):
    for _ in range(100):
        async with session_maker() as probe:
            blocked = await probe.scalar(
                text("SELECT CAST(:holder AS integer) = ANY(pg_blocking_pids(:waiter))"),
                {"holder": holder_pid, "waiter": waiter_pid},
            )
        if blocked:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("second sync never blocked on the first sync's uncommitted insert")


async def _race_two_first_syncs(
    session_maker,
    first: UserSyncRequest,
    second: UserSyncRequest,
    *,
    second_may_adopt: bool = True,
):
    async with session_maker() as session_a, session_maker() as session_b:
        pid_a = await session_a.scalar(text("SELECT pg_backend_pid()"))
        pid_b = await session_b.scalar(text("SELECT pg_backend_pid()"))
        user_a, new_a = await UserService(session_a).sync_from_oidc(
            first, allow_email_adoption=True
        )
        task_b = asyncio.create_task(
            UserService(session_b).sync_from_oidc(second, allow_email_adoption=second_may_adopt)
        )
        try:
            await _wait_until_blocked_by(session_maker, pid_b, pid_a)
            await session_a.commit()
            user_b, new_b = await task_b
        finally:
            task_b.cancel()
        await session_b.commit()
    return (user_a, new_a), (user_b, new_b)


async def _cleanup(session_maker, *conditions):
    async with session_maker() as cleanup:
        await cleanup.execute(delete(User).where(or_(*conditions)))
        await cleanup.commit()


@pytest.mark.asyncio
async def test_concurrent_first_sync_for_same_identity_creates_one_user(session_maker):
    external_id = f"race-{uuid4()}"
    sync = UserSyncRequest(
        external_id=external_id, email=f"{external_id}@example.com", display_name="Race"
    )
    try:
        (user_a, new_a), (user_b, new_b) = await _race_two_first_syncs(session_maker, sync, sync)

        async with session_maker() as check:
            rows = await check.scalar(
                select(func.count()).select_from(User).where(User.external_id == external_id)
            )
    finally:
        await _cleanup(session_maker, User.external_id == external_id)

    assert new_a is True
    assert new_b is False
    assert user_b.id == user_a.id
    assert rows == 1


@pytest.mark.asyncio
async def test_concurrent_first_sync_with_same_email_adopts_the_committed_user(session_maker):
    email = f"race-{uuid4()}@example.com"
    first = UserSyncRequest(external_id=f"dev-{uuid4()}", email=email, display_name="First")
    second = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=email, display_name="Second")
    try:
        (user_a, _), (user_b, new_b) = await _race_two_first_syncs(session_maker, first, second)

        async with session_maker() as check:
            users = (await check.scalars(select(User).where(User.email == email))).all()
    finally:
        await _cleanup(session_maker, User.email == email)

    assert new_b is False
    assert user_b.id == user_a.id
    assert [(u.id, u.external_id) for u in users] == [(user_a.id, second.external_id)]


@pytest.mark.asyncio
async def test_concurrent_first_sync_refuses_adoption_when_not_allowed(session_maker):
    email = f"race-{uuid4()}@example.com"
    first = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=email, display_name="Owner")
    second = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=email, display_name="Attacker")
    try:
        with pytest.raises(UserEmailConflictError):
            await _race_two_first_syncs(session_maker, first, second, second_may_adopt=False)

        async with session_maker() as check:
            users = (await check.scalars(select(User).where(User.email == email))).all()
    finally:
        await _cleanup(session_maker, User.email == email)

    assert [(u.external_id, u.display_name) for u in users] == [(first.external_id, "Owner")]


@pytest.mark.asyncio
async def test_sync_refuses_adoption_by_email_when_not_allowed(db_session, test_user):
    original_external_id = test_user.external_id
    sync = UserSyncRequest(
        external_id=f"oidc-{uuid4()}", email=test_user.email, display_name="Attacker"
    )

    with pytest.raises(UserEmailConflictError):
        await UserService(db_session).sync_from_oidc(sync, allow_email_adoption=False)

    await db_session.refresh(test_user)
    assert test_user.external_id == original_external_id
    assert test_user.display_name == "Test User"


@pytest.mark.asyncio
async def test_sync_adopts_by_email_when_allowed(db_session, test_user):
    sync = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=test_user.email, display_name="New")

    user, is_new = await UserService(db_session).sync_from_oidc(sync, allow_email_adoption=True)

    assert is_new is False
    assert user.id == test_user.id
    assert user.external_id == sync.external_id
