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
    second_verified: bool = True,
):
    async with session_maker() as session_a, session_maker() as session_b:
        pid_a = await session_a.scalar(text("SELECT pg_backend_pid()"))
        pid_b = await session_b.scalar(text("SELECT pg_backend_pid()"))
        user_a, new_a = await UserService(session_a).sync_from_oidc(first, email_verified=True)
        task_b = asyncio.create_task(
            UserService(session_b).sync_from_oidc(second, email_verified=second_verified)
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
            await _race_two_first_syncs(session_maker, first, second, second_verified=False)

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
        await UserService(db_session).sync_from_oidc(sync, email_verified=False)

    await db_session.refresh(test_user)
    assert test_user.external_id == original_external_id
    assert test_user.display_name == "Test User"


@pytest.mark.asyncio
async def test_sync_adopts_by_email_when_allowed(db_session, test_user):
    sync = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=test_user.email, display_name="New")

    user, is_new = await UserService(db_session).sync_from_oidc(sync, email_verified=True)

    assert is_new is False
    assert user.id == test_user.id
    assert user.external_id == sync.external_id


@pytest.mark.asyncio
async def test_unverified_sign_up_is_never_adopted(db_session):
    email = f"victim-{uuid4()}@example.com"
    squatter = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=email, display_name="Squatter")
    owner = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=email, display_name="Owner")
    service = UserService(db_session)

    squatted, is_new = await service.sync_from_oidc(squatter, email_verified=False)
    assert is_new is True
    assert squatted.email_verified is False

    with pytest.raises(UserEmailConflictError):
        await service.sync_from_oidc(owner, email_verified=True)

    await db_session.refresh(squatted)
    assert (squatted.external_id, squatted.display_name) == (squatter.external_id, "Squatter")


@pytest.mark.asyncio
async def test_unverified_email_change_is_never_adopted(db_session, test_user):
    victim_email = f"victim-{uuid4()}@example.com"
    change = UserSyncRequest(
        external_id=test_user.external_id, email=victim_email, display_name="Squatter"
    )
    owner = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=victim_email, display_name="Owner")
    service = UserService(db_session)

    changed, _ = await service.sync_from_oidc(change, email_verified=False)
    assert changed.email == victim_email
    assert changed.email_verified is False

    with pytest.raises(UserEmailConflictError):
        await service.sync_from_oidc(owner, email_verified=True)

    await db_session.refresh(test_user)
    assert test_user.external_id == change.external_id


@pytest.mark.asyncio
async def test_verified_email_change_stays_adoptable(db_session, test_user):
    new_email = f"moved-{uuid4()}@example.com"
    change = UserSyncRequest(external_id=test_user.external_id, email=new_email, display_name="Me")
    migrate = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=new_email, display_name="Me")
    service = UserService(db_session)

    changed, _ = await service.sync_from_oidc(change, email_verified=True)
    assert changed.email_verified is True

    adopted, is_new = await service.sync_from_oidc(migrate, email_verified=True)
    assert is_new is False
    assert adopted.id == test_user.id
    assert adopted.external_id == migrate.external_id
    assert adopted.email_verified is True


@pytest.mark.asyncio
async def test_verified_sign_in_marks_unchanged_email_verified(db_session):
    external_id = f"oidc-{uuid4()}"
    sync = UserSyncRequest(
        external_id=external_id, email=f"{external_id}@example.com", display_name="Me"
    )
    service = UserService(db_session)

    user, _ = await service.sync_from_oidc(sync, email_verified=False)
    assert user.email_verified is False

    user, _ = await service.sync_from_oidc(sync, email_verified=True)
    assert user.email_verified is True

    user, _ = await service.sync_from_oidc(sync, email_verified=False)
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_user_inserted_without_verification_defaults_to_unverified(db_session):
    unique_id = uuid4()
    user = User(
        external_id=f"raw-{unique_id}", email=f"raw-{unique_id}@example.com", display_name="Raw"
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.email_verified is False


async def _commit_users(session_maker, *users: User):
    async with session_maker() as setup:
        setup.add_all(users)
        await setup.commit()


async def _race_conflicting_syncs(session_maker, first: UserSyncRequest, second: UserSyncRequest):
    async with session_maker() as session_a, session_maker() as session_b:
        pid_a = await session_a.scalar(text("SELECT pg_backend_pid()"))
        pid_b = await session_b.scalar(text("SELECT pg_backend_pid()"))
        await UserService(session_a).sync_from_oidc(first, email_verified=True)
        task_b = asyncio.create_task(
            UserService(session_b).sync_from_oidc(second, email_verified=True)
        )
        try:
            await _wait_until_blocked_by(session_maker, pid_b, pid_a)
            await session_a.commit()
            with pytest.raises(UserEmailConflictError):
                await task_b
        finally:
            task_b.cancel()
        emails = (await session_b.execute(select(User.external_id, User.email))).all()
        await session_b.commit()
    return dict(emails)


@pytest.mark.asyncio
async def test_concurrent_email_changes_to_same_address_conflict_cleanly(session_maker):
    run = uuid4()
    target = f"target-{run}@example.com"
    first = User(external_id=f"a-{run}", email=f"a-{run}@example.com", display_name="A")
    second = User(external_id=f"b-{run}", email=f"b-{run}@example.com", display_name="B")
    await _commit_users(session_maker, first, second)
    try:
        emails = await _race_conflicting_syncs(
            session_maker,
            UserSyncRequest(external_id=first.external_id, email=target, display_name="A"),
            UserSyncRequest(external_id=second.external_id, email=target, display_name="B"),
        )
    finally:
        await _cleanup(session_maker, User.external_id.in_([first.external_id, second.external_id]))

    assert emails[first.external_id] == target
    assert emails[second.external_id] == f"b-{run}@example.com"


@pytest.mark.asyncio
async def test_adoption_racing_a_first_sign_in_of_the_same_identity_conflicts_cleanly(
    session_maker,
):
    run = uuid4()
    external_id = f"oidc-{run}"
    existing = User(
        external_id=f"old-{run}",
        email=f"existing-{run}@example.com",
        display_name="Existing",
        email_verified=True,
    )
    await _commit_users(session_maker, existing)
    try:
        emails = await _race_conflicting_syncs(
            session_maker,
            UserSyncRequest(
                external_id=external_id, email=f"fresh-{run}@example.com", display_name="Fresh"
            ),
            UserSyncRequest(external_id=external_id, email=existing.email, display_name="Adopt"),
        )
    finally:
        await _cleanup(
            session_maker,
            User.external_id.in_([external_id, existing.external_id]),
            User.email == existing.email,
        )

    assert emails[existing.external_id] == existing.email
    assert emails[external_id] == f"fresh-{run}@example.com"
