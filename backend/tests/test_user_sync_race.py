import asyncio
from contextlib import AsyncExitStack
from uuid import uuid4

import pytest
from sqlalchemy import delete, or_, select, text

from app.models import User
from app.schemas.user import UserResponse, UserSyncRequest
from app.services.user_service import UserEmailConflictError, UserService


async def _wait_until_blocked_by(session_maker, waiter_pid: int, racer_pids: list[int]):
    # Any racer counts, because twins of one identity can queue behind each other's
    # uncommitted external_id before reaching the first sync's rows.
    for _ in range(100):
        async with session_maker() as probe:
            blocked = await probe.scalar(
                text("SELECT pg_blocking_pids(:waiter) && CAST(:racers AS integer[])"),
                {"racers": racer_pids, "waiter": waiter_pid},
            )
        if blocked:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("a racing sync never blocked on the first sync's uncommitted rows")


async def _race(
    session_maker,
    first: UserSyncRequest,
    *others: UserSyncRequest,
    first_verified: bool = True,
    others_verified: bool = True,
    commit_first_before: str | None = None,
):
    # By default the first sync commits once every other sync is blocked on its uncommitted
    # rows; commit_first_before instead names a UserService method that the others pause at
    # until the first has committed, to land the commit between two of their lookups. Each
    # other sync commits as soon as it returns, releasing any sync still blocked on its rows.
    async with AsyncExitStack() as stack:
        session_a = await stack.enter_async_context(session_maker())
        sessions = [await stack.enter_async_context(session_maker()) for _ in others]
        pid_a = await session_a.scalar(text("SELECT pg_backend_pid()"))
        pids = [await session.scalar(text("SELECT pg_backend_pid()")) for session in sessions]
        first_result = await UserService(session_a).sync_from_oidc(
            first, email_verified=first_verified
        )
        committed = asyncio.Event()
        reached = []
        tasks = {}
        for sync, session in zip(others, sessions, strict=True):
            service = UserService(session)
            if commit_first_before is not None:
                original = getattr(service, commit_first_before)
                arrived = asyncio.Event()
                reached.append(arrived.wait())

                async def paused(*args, _original=original, _arrived=arrived, **kwargs):
                    _arrived.set()
                    await committed.wait()
                    return await _original(*args, **kwargs)

                setattr(service, commit_first_before, paused)
            task = asyncio.create_task(service.sync_from_oidc(sync, email_verified=others_verified))
            tasks[task] = session
        results = {}
        try:
            if commit_first_before is None:
                for pid in pids:
                    await _wait_until_blocked_by(session_maker, pid, [pid_a, *pids])
            else:
                await asyncio.wait_for(asyncio.gather(*reached), timeout=5)
            await session_a.commit()
            committed.set()
            pending = dict(tasks)
            while pending:
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    session = pending.pop(task)
                    try:
                        results[task] = task.result()
                    except UserEmailConflictError as e:
                        results[task] = e
                    # Reading through the session proves a conflict left its transaction usable.
                    emails = dict(
                        (await session.execute(select(User.external_id, User.email))).all()
                    )
                    await session.commit()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    return (first_result, *(results[task] for task in tasks), emails)


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
    ("verified", "commit_first_before"),
    [
        pytest.param(True, None, id="commit-while-second-inserts"),
        pytest.param(False, "get_by_email", id="unverified-commit-between-lookups"),
    ],
)
async def test_concurrent_first_sync_for_same_identity_creates_one_user(
    session_maker, verified, commit_first_before
):
    external_id = f"race-{uuid4()}"
    email = f"{external_id}@example.com"
    sync = UserSyncRequest(external_id=external_id, email=email, display_name="Race")
    try:
        (user_a, new_a), (user_b, new_b), emails = await _race(
            session_maker,
            sync,
            sync,
            first_verified=verified,
            others_verified=verified,
            commit_first_before=commit_first_before,
        )
    finally:
        await _cleanup(session_maker, User.external_id == external_id)

    assert (new_a, new_b) == (True, False)
    assert user_b.id == user_a.id
    assert emails[external_id] == email


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first", "other", "other_becomes", "final"),
    [
        pytest.param(
            ("caller", "claimed", True),
            ("caller", "claimed", True),
            ("first", False),
            {"holder": "detached", "caller": "claimed"},
            id="same-identity-reclaims",
        ),
        pytest.param(
            ("caller", "claimed", True),
            ("rival", "claimed", True),
            ("first", False),
            {"holder": "detached", "rival": "claimed"},
            id="two-identities-reclaim",
        ),
        pytest.param(
            ("holder", "claimed", True),
            ("caller", "claimed", True),
            ("holder", False),
            {"caller": "claimed"},
            id="holder-verifies-before-reclaim",
        ),
        pytest.param(
            ("caller", "claimed", True),
            ("holder", "claimed", True),
            "conflict",
            {"holder": "detached", "caller": "claimed"},
            id="reclaim-before-holder-verifies",
        ),
        pytest.param(
            ("holder", "moved", False),
            ("caller", "claimed", True),
            ("new", True),
            {"holder": "moved", "caller": "claimed"},
            id="holder-moves-before-reclaim",
        ),
    ],
)
async def test_reclaim_racing_another_sign_in_acts_on_the_committed_holder(
    session_maker, first, other, other_becomes, final
):
    run = uuid4()
    emails_by_kind = {"claimed": f"claimed-{run}@example.com", "moved": f"moved-{run}@example.com"}
    holder = User(
        external_id=f"holder-{run}", email=emails_by_kind["claimed"], display_name="Holder"
    )
    await _commit_users(session_maker, holder)
    emails_by_kind["detached"] = f"{holder.id}@detached.invalid"
    external_ids = {role: f"{role}-{run}" for role in ("holder", "caller", "rival")}

    def sync(role, email_kind):
        return UserSyncRequest(
            external_id=external_ids[role], email=emails_by_kind[email_kind], display_name=role
        )

    try:
        (first_user, _), other_result, emails = await _race(
            session_maker,
            sync(*first[:2]),
            sync(*other[:2]),
            first_verified=first[2],
            others_verified=other[2],
        )
    finally:
        await _cleanup(session_maker, User.external_id.in_(external_ids.values()))

    outcomes = {first_user.id: "first", holder.id: "holder"}
    assert (
        "conflict"
        if isinstance(other_result, UserEmailConflictError)
        else (outcomes.get(other_result[0].id, "new"), other_result[1])
    ) == other_becomes
    assert {role: emails.get(external_ids[role]) for role in external_ids} == {
        role: emails_by_kind.get(final.get(role)) for role in external_ids
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("twins", [2, 3], ids=["two-verified-twins", "three-verified-twins"])
async def test_verified_burst_against_an_unverified_first_sign_in_reclaims_once(
    session_maker, twins
):
    run = uuid4()
    email = f"burst-{run}@example.com"
    unverified = UserSyncRequest(external_id=f"u-{run}", email=email, display_name="U")
    verified = UserSyncRequest(external_id=f"v-{run}", email=email, display_name="V")
    try:
        (squatter, _), *results, emails = await _race(
            session_maker, unverified, *[verified] * twins, first_verified=False
        )
    finally:
        await _cleanup(
            session_maker, User.external_id.in_([unverified.external_id, verified.external_id])
        )

    assert sorted(is_new for _, is_new in results) == [False] * (twins - 1) + [True]
    assert len({user.id for user, _ in results}) == 1
    assert {
        external_id: emails.get(external_id)
        for external_id in (unverified.external_id, verified.external_id)
    } == {
        unverified.external_id: f"{squatter.id}@detached.invalid",
        verified.external_id: email,
    }


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
        _, conflict, _ = await _race(session_maker, first, second, others_verified=False)

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
