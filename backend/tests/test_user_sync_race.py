import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, or_, select, text

from app.models import User
from app.schemas.user import UserResponse, UserSyncRequest
from app.services.user_service import UserEmailConflictError, UserService


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


async def _race(
    session_maker,
    first: UserSyncRequest,
    second: UserSyncRequest,
    *,
    first_verified: bool = True,
    second_verified: bool = True,
    commit_first_before: str | None = None,
):
    # By default the first sync commits once the second is blocked on its uncommitted rows;
    # commit_first_before instead names a UserService method that the second sync pauses at
    # until the first has committed, to land the commit between two of its lookups.
    async with session_maker() as session_a, session_maker() as session_b:
        pid_a = await session_a.scalar(text("SELECT pg_backend_pid()"))
        pid_b = await session_b.scalar(text("SELECT pg_backend_pid()"))
        first_result = await UserService(session_a).sync_from_oidc(
            first, email_verified=first_verified
        )
        service_b = UserService(session_b)
        reached, committed = asyncio.Event(), asyncio.Event()
        if commit_first_before is not None:
            original = getattr(service_b, commit_first_before)

            async def paused(*args, **kwargs):
                reached.set()
                await committed.wait()
                return await original(*args, **kwargs)

            setattr(service_b, commit_first_before, paused)
        task_b = asyncio.create_task(
            service_b.sync_from_oidc(second, email_verified=second_verified)
        )
        try:
            if commit_first_before is None:
                await _wait_until_blocked_by(session_maker, pid_b, pid_a)
            else:
                await asyncio.wait_for(reached.wait(), timeout=5)
            await session_a.commit()
            committed.set()
            try:
                second_result = await task_b
            except UserEmailConflictError as e:
                second_result = e
        finally:
            task_b.cancel()
        # Reading through the second session proves a conflict left its transaction usable.
        emails = dict((await session_b.execute(select(User.external_id, User.email))).all())
        await session_b.commit()
    return first_result, second_result, emails


async def _cleanup(session_maker, *conditions):
    async with session_maker() as cleanup:
        await cleanup.execute(delete(User).where(or_(*conditions)))
        await cleanup.commit()


async def _commit_users(session_maker, *users: User):
    async with session_maker() as setup:
        setup.add_all(users)
        await setup.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("verified", "commit_first_before", "squatted"),
    [
        pytest.param(True, None, False, id="commit-while-second-inserts"),
        pytest.param(False, "get_by_email", False, id="unverified-commit-between-lookups"),
        pytest.param(True, None, True, id="concurrent-reclaims"),
    ],
)
async def test_concurrent_first_sync_for_same_identity_creates_one_user(
    session_maker, verified, commit_first_before, squatted
):
    external_id = f"race-{uuid4()}"
    email = f"{external_id}@example.com"
    sync = UserSyncRequest(external_id=external_id, email=email, display_name="Race")
    squatter = User(external_id=f"squat-{uuid4()}", email=email, display_name="Squatter")
    if squatted:
        await _commit_users(session_maker, squatter)
    try:
        (user_a, new_a), (user_b, new_b), emails = await _race(
            session_maker,
            sync,
            sync,
            first_verified=verified,
            second_verified=verified,
            commit_first_before=commit_first_before,
        )
    finally:
        await _cleanup(session_maker, User.external_id.in_([external_id, squatter.external_id]))

    assert (new_a, new_b) == (True, False)
    assert user_b.id == user_a.id
    assert emails[external_id] == email
    if squatted:
        assert emails[squatter.external_id] == f"{squatter.id}@detached.invalid"


@pytest.mark.asyncio
async def test_concurrent_first_sync_with_same_email_adopts_the_committed_user(session_maker):
    email = f"race-{uuid4()}@example.com"
    first = UserSyncRequest(external_id=f"dev-{uuid4()}", email=email, display_name="First")
    second = UserSyncRequest(external_id=f"oidc-{uuid4()}", email=email, display_name="Second")
    try:
        (user_a, _), (user_b, new_b), _ = await _race(session_maker, first, second)

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
        _, conflict, _ = await _race(session_maker, first, second, second_verified=False)

        async with session_maker() as check:
            users = (await check.scalars(select(User).where(User.email == email))).all()
    finally:
        await _cleanup(session_maker, User.email == email)

    assert isinstance(conflict, UserEmailConflictError)
    assert [(u.external_id, u.display_name) for u in users] == [(first.external_id, "Owner")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("caller_verified", "stored_verified", "outcome"),
    [
        pytest.param(True, True, "adopted", id="both-verified"),
        pytest.param(False, True, "unverified-caller", id="caller-unverified"),
        pytest.param(True, False, "reclaimed", id="stored-unverified"),
        pytest.param(False, False, "unverified-caller", id="neither"),
    ],
)
async def test_adoption_requires_both_verified(
    db_session, caller_verified, stored_verified, outcome
):
    run = uuid4()
    email = f"owner-{run}@example.com"
    stored = User(external_id=f"old-{run}", email=email, display_name="Stored")
    if stored_verified:
        stored.email_verified = True
    db_session.add(stored)
    await db_session.flush()
    await db_session.refresh(stored)
    assert stored.email_verified is stored_verified
    caller = UserSyncRequest(external_id=f"new-{run}", email=email, display_name="Caller")
    service = UserService(db_session)

    if outcome == "unverified-caller":
        with pytest.raises(UserEmailConflictError, match="provider that verifies"):
            await service.sync_from_oidc(caller, email_verified=caller_verified)
        await db_session.refresh(stored)
        assert (stored.external_id, stored.email) == (f"old-{run}", email)
        return

    user, is_new = await service.sync_from_oidc(caller, email_verified=caller_verified)
    await db_session.refresh(stored)
    if outcome == "adopted":
        assert (is_new, user.id, user.external_id) == (False, stored.id, caller.external_id)
        return

    assert (is_new, user.email, user.email_verified) == (True, email, True)
    assert user.id != stored.id
    placeholder = f"{stored.id}@detached.invalid"
    assert (stored.external_id, stored.email, stored.email_verified) == (
        f"old-{run}",
        placeholder,
        False,
    )
    UserResponse.model_validate(stored)
    for later in (
        UserSyncRequest(external_id=stored.external_id, email=email, display_name="Stored"),
        UserSyncRequest(external_id=f"other-{run}", email=placeholder, display_name="Other"),
    ):
        with pytest.raises(UserEmailConflictError, match="^Email already in use by another"):
            await service.sync_from_oidc(later, email_verified=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change_verified", "owner_exists", "outcome"),
    [
        pytest.param(True, False, "adopted", id="verified-change-new-owner"),
        pytest.param(False, False, "reclaimed", id="unverified-change-new-owner"),
        pytest.param(True, True, "in-use", id="verified-change-existing-owner"),
        pytest.param(False, True, "reclaimed", id="unverified-change-existing-owner"),
    ],
)
async def test_changed_email_is_adoptable_only_when_verified(
    db_session, test_user, change_verified, owner_exists, outcome
):
    run = uuid4()
    target = f"target-{run}@example.com"
    change = UserSyncRequest(external_id=test_user.external_id, email=target, display_name="Me")
    owner = UserSyncRequest(external_id=f"owner-{run}", email=target, display_name="Owner")
    service = UserService(db_session)
    if owner_exists:
        await service.sync_from_oidc(
            owner.model_copy(update={"email": f"owner-{run}@example.com"}), email_verified=True
        )

    changed, _ = await service.sync_from_oidc(change, email_verified=change_verified)
    assert (changed.email, changed.email_verified) == (target, change_verified)

    if outcome == "in-use":
        with pytest.raises(UserEmailConflictError, match="^Email already in use by another"):
            await service.sync_from_oidc(owner, email_verified=True)
        return

    owned, is_new = await service.sync_from_oidc(owner, email_verified=True)
    await db_session.refresh(test_user)
    assert (owned.email, owned.email_verified) == (target, True)
    assert is_new is (outcome == "reclaimed" and not owner_exists)
    if outcome == "adopted":
        assert (owned.id, test_user.external_id) == (test_user.id, owner.external_id)
    else:
        assert owned.id != test_user.id
        assert (test_user.external_id, test_user.email) == (
            change.external_id,
            f"{test_user.id}@detached.invalid",
        )


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
async def test_concurrent_email_changes_to_same_address_conflict_cleanly(session_maker):
    run = uuid4()
    target = f"target-{run}@example.com"
    first = User(external_id=f"a-{run}", email=f"a-{run}@example.com", display_name="A")
    second = User(external_id=f"b-{run}", email=f"b-{run}@example.com", display_name="B")
    await _commit_users(session_maker, first, second)
    try:
        _, conflict, emails = await _race(
            session_maker,
            UserSyncRequest(external_id=first.external_id, email=target, display_name="A"),
            UserSyncRequest(external_id=second.external_id, email=target, display_name="B"),
        )
    finally:
        await _cleanup(session_maker, User.external_id.in_([first.external_id, second.external_id]))

    assert isinstance(conflict, UserEmailConflictError)
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
        _, conflict, emails = await _race(
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

    assert isinstance(conflict, UserEmailConflictError)
    assert emails[existing.external_id] == existing.email
    assert emails[external_id] == f"fresh-{run}@example.com"
