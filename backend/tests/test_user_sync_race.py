import asyncio
from contextlib import AsyncExitStack
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, or_, select, text, update
from sqlalchemy.exc import IntegrityError

from app.models import User, UserIdentity
from app.schemas.user import UserSyncRequest
from app.services.user_service import UserEmailConflictError, UserService
from tests.identity_helpers import add_users_with_identities, identities_of, identity_ids_of


async def _wait_until_blocked_by(session_maker, waiter_pid: int, racer_pids: list[int]):
    # Any racer counts, because twins of one identity can queue behind each other's
    # uncommitted identity row before reaching the first sync's rows.
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
    first_provider: str = "oidc",
    others_provider: str = "oidc",
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
            first, provider=first_provider, email_verified=first_verified
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
            task = asyncio.create_task(
                service.sync_from_oidc(
                    sync, provider=others_provider, email_verified=others_verified
                )
            )
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
                    await session.execute(select(1))
                    await session.commit()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    async with session_maker() as check:
        emails = dict(
            (
                await check.execute(
                    select(UserIdentity.subject, User.email).join(
                        User, User.id == UserIdentity.user_id
                    )
                )
            ).all()
        )
    return (first_result, *(results[task] for task in tasks), emails)


def _outcome(result, names: dict) -> str | tuple[str, bool]:
    if isinstance(result, UserEmailConflictError):
        return "conflict"
    user, _, is_new = result
    return names.get(user.id, "new"), is_new


async def _cleanup(session_maker, subjects, *conditions):
    # Keyed on identity subjects because the ids of users a race creates are unknown here.
    holders = select(UserIdentity.user_id).where(UserIdentity.subject.in_(list(subjects)))
    async with session_maker() as cleanup:
        await cleanup.execute(delete(User).where(or_(User.id.in_(holders), *conditions)))
        await cleanup.commit()


async def _commit_users(session_maker, *users: User, provider: str = "legacy"):
    async with session_maker() as setup:
        await add_users_with_identities(setup, *users, provider=provider)
        await setup.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_is_new", "first_verified", "other_verified", "commit_first_before", "verified_after"),
    [
        pytest.param(True, True, True, None, True, id="commit-while-second-inserts"),
        pytest.param(
            True, False, False, "get_by_email", False, id="unverified-commit-between-lookups"
        ),
        pytest.param(False, True, True, "get_by_email", True, id="verified-twins-move-email"),
        pytest.param(False, True, False, "get_by_email", True, id="verified-move-then-unverified"),
        pytest.param(False, False, True, "get_by_email", True, id="unverified-move-then-verified"),
        pytest.param(False, False, False, "get_by_email", False, id="unverified-twins-move-email"),
        pytest.param(False, True, True, None, True, id="twin-legacy-claims"),
    ],
)
async def test_concurrent_syncs_of_one_identity_converge_on_one_user(
    session_maker, first_is_new, first_verified, other_verified, commit_first_before, verified_after
):
    external_id = f"race-{uuid4()}"
    email = f"{external_id}@example.com"
    sync = UserSyncRequest(external_id=external_id, email=email, display_name="Race")
    if not first_is_new:
        await _commit_users(
            session_maker,
            User(external_id=external_id, email=f"old-{email}", display_name="Stored"),
        )
    try:
        (user_a, _, new_a), (user_b, _, new_b), emails = await _race(
            session_maker,
            sync,
            sync,
            first_verified=first_verified,
            others_verified=other_verified,
            commit_first_before=commit_first_before,
        )
    finally:
        await _cleanup(session_maker, [external_id])

    assert (new_a, new_b) == (first_is_new, False)
    assert user_b.id == user_a.id
    assert (emails[external_id], user_b.email_verified) == (email, verified_after)


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
        (first_user, _, _), other_result, emails = await _race(
            session_maker,
            sync(*first[:2]),
            sync(*other[:2]),
            first_verified=first[2],
            others_verified=other[2],
        )
    finally:
        await _cleanup(session_maker, external_ids.values())

    assert _outcome(other_result, {first_user.id: "first", holder.id: "holder"}) == other_becomes
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
        (squatter, _, _), *results, emails = await _race(
            session_maker, unverified, *[verified] * twins, first_verified=False
        )
    finally:
        await _cleanup(session_maker, [unverified.external_id, verified.external_id])

    assert sorted(is_new for _, _, is_new in results) == [False] * (twins - 1) + [True]
    assert len({user.id for user, _, _ in results}) == 1
    assert {
        external_id: emails.get(external_id)
        for external_id in (unverified.external_id, verified.external_id)
    } == {
        unverified.external_id: f"{squatter.id}@detached.invalid",
        verified.external_id: email,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("second_verified", "second_becomes", "stored_as"),
    [
        pytest.param(True, ("first", False), "second", id="verified-adopts"),
        pytest.param(False, "conflict", "first", id="unverified-is-refused"),
    ],
)
async def test_concurrent_first_sync_with_same_email_adopts_only_when_verified(
    session_maker, second_verified, second_becomes, stored_as
):
    run = uuid4()
    email = f"race-{run}@example.com"
    syncs = {
        role: UserSyncRequest(external_id=f"{role}-{run}", email=email, display_name=role)
        for role in ("first", "second")
    }
    try:
        (user_a, _, _), second_result, _ = await _race(
            session_maker, syncs["first"], syncs["second"], others_verified=second_verified
        )

        async with session_maker() as check:
            users = [
                (user.id, await identities_of(check, user.id), user.display_name)
                for user in (await check.scalars(select(User).where(User.email == email))).all()
            ]
    finally:
        await _cleanup(session_maker, [], User.email == email)

    assert _outcome(second_result, {user_a.id: "first"}) == second_becomes
    # Both sign in through OIDC, so an adoption replaces the first subject: one per provider.
    assert users == [(user_a.id, {("oidc", f"{stored_as}-{run}")}, stored_as)]


async def _stored_holder(db_session, run, *, verified: bool) -> User:
    stored = User(
        external_id=f"old-{run}",
        email=f"owner-{run}@example.com",
        display_name="Stored",
        email_verified=verified,
    )
    await add_users_with_identities(db_session, stored)
    await db_session.refresh(stored)
    return stored


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_verified", [True, False], ids=["holder-verified", "holder-unverified"]
)
async def test_unverified_caller_can_neither_adopt_nor_reclaim_a_held_email(
    db_session, stored_verified
):
    run = uuid4()
    stored = await _stored_holder(db_session, run, verified=stored_verified)
    caller = UserSyncRequest(external_id=f"new-{run}", email=stored.email, display_name="Caller")

    with pytest.raises(UserEmailConflictError, match="provider that verifies"):
        await UserService(db_session).sync_from_oidc(caller, provider="oidc", email_verified=False)

    await db_session.refresh(stored)
    assert stored.email == f"owner-{run}@example.com"
    assert await identities_of(db_session, stored.id) == {("legacy", f"old-{run}")}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_verified", "is_new", "same_row", "stored_after"),
    [
        pytest.param(True, False, True, ("new", "owner"), id="adopts-verified-holder"),
        pytest.param(False, True, False, ("old", "detached"), id="reclaims-from-unverified-holder"),
    ],
)
async def test_verified_caller_adopts_a_verified_holder_or_reclaims_from_an_unverified_one(
    db_session, stored_verified, is_new, same_row, stored_after
):
    run = uuid4()
    stored = await _stored_holder(db_session, run, verified=stored_verified)
    caller = UserSyncRequest(external_id=f"new-{run}", email=stored.email, display_name="Caller")
    names = {
        "new": {("oidc", caller.external_id)},
        "old": {("legacy", f"old-{run}")},
        "owner": stored.email,
        "detached": f"{stored.id}@detached.invalid",
    }

    user, _, created = await UserService(db_session).sync_from_oidc(
        caller, provider="oidc", email_verified=True
    )

    await db_session.refresh(stored)
    assert (created, user.id == stored.id) == (is_new, same_row)
    assert (await identities_of(db_session, user.id), user.email, user.email_verified) == (
        names["new"],
        names["owner"],
        True,
    )
    assert (await identities_of(db_session, stored.id), stored.email) == tuple(
        names[name] for name in stored_after
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change_verified", "owner_exists", "is_new", "same_row", "me_after"),
    [
        pytest.param(
            True, False, False, True, ("owner", "target"), id="verified-change-is-adopted"
        ),
        pytest.param(
            False, False, True, False, ("me", "detached"), id="unverified-change-is-reclaimed"
        ),
        pytest.param(
            False,
            True,
            False,
            False,
            ("me", "detached"),
            id="unverified-change-is-reclaimed-by-owner",
        ),
    ],
)
async def test_changed_email_is_adopted_when_verified_and_reclaimed_when_not(
    db_session, test_user, change_verified, owner_exists, is_new, same_row, me_after
):
    run = uuid4()
    target = f"target-{run}@example.com"
    change = UserSyncRequest(external_id=test_user.external_id, email=target, display_name="Me")
    owner = UserSyncRequest(external_id=f"owner-{run}", email=target, display_name="Owner")
    names = {
        "me": {("oidc", test_user.external_id)},
        "owner": {("oidc", owner.external_id)},
        "target": target,
        "detached": f"{test_user.id}@detached.invalid",
    }
    service = UserService(db_session)
    if owner_exists:
        await service.sync_from_oidc(
            owner.model_copy(update={"email": f"owner-{run}@example.com"}),
            provider="oidc",
            email_verified=True,
        )
    changed, _, _ = await service.sync_from_oidc(
        change, provider="oidc", email_verified=change_verified
    )
    assert (changed.email, changed.email_verified) == (target, change_verified)

    owned, _, created = await service.sync_from_oidc(owner, provider="oidc", email_verified=True)

    await db_session.refresh(test_user)
    assert (owned.email, owned.email_verified, created) == (target, True, is_new)
    assert (owned.id == test_user.id) is same_row
    assert (await identities_of(db_session, test_user.id), test_user.email) == tuple(
        names[name] for name in me_after
    )


@pytest.mark.asyncio
async def test_verified_sign_in_marks_unchanged_email_verified(db_session):
    external_id = f"oidc-{uuid4()}"
    sync = UserSyncRequest(
        external_id=external_id, email=f"{external_id}@example.com", display_name="Me"
    )
    service = UserService(db_session)

    user, _, _ = await service.sync_from_oidc(sync, provider="oidc", email_verified=False)
    assert user.email_verified is False

    user, _, _ = await service.sync_from_oidc(sync, provider="oidc", email_verified=True)
    assert user.email_verified is True

    user, _, _ = await service.sync_from_oidc(sync, provider="oidc", email_verified=False)
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
        await _cleanup(session_maker, [first.external_id, second.external_id])

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
            session_maker, [external_id, existing.external_id], User.email == existing.email
        )

    assert isinstance(conflict, UserEmailConflictError)
    assert emails[existing.external_id] == existing.email
    assert emails[external_id] == f"fresh-{run}@example.com"


@pytest.mark.asyncio
async def test_concurrent_email_swap_between_two_accounts_completes(session_maker):
    run = uuid4()
    users = {
        role: User(
            external_id=f"{role}-{run}", email=f"{role}-{run}@example.com", display_name=role
        )
        for role in ("a", "b")
    }
    await _commit_users(session_maker, *users.values())
    # The bystander's commit only releases both swaps at once, so that each detaches the other's
    # row before either updates its own.
    bystander = UserSyncRequest(
        external_id=f"bystander-{run}", email=f"bystander-{run}@example.com", display_name="C"
    )
    try:
        _, a_result, b_result, emails = await _race(
            session_maker,
            bystander,
            UserSyncRequest(external_id=f"a-{run}", email=f"b-{run}@example.com", display_name="a"),
            UserSyncRequest(external_id=f"b-{run}", email=f"a-{run}@example.com", display_name="b"),
            commit_first_before="get_by_email",
        )
    finally:
        await _cleanup(session_maker, [f"{role}-{run}" for role in ("a", "b", "bystander")])

    assert _outcome(a_result, {users["a"].id: "a"}) == ("a", False)
    assert _outcome(b_result, {users["b"].id: "b"}) == ("b", False)
    assert (emails[f"a-{run}"], emails[f"b-{run}"]) == (
        f"b-{run}@example.com",
        f"a-{run}@example.com",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored", "first", "other", "final"),
    [
        pytest.param(
            ("legacy", "s"),
            ("oidc", "s"),
            ("oidc", "t"),
            {("oidc", "t")},
            id="legacy-claim-racing-adoption",
        ),
        pytest.param(
            ("oidc", "a"),
            ("oidc", "b"),
            ("oidc", "a"),
            {("oidc", "a")},
            id="replace-racing-stale-sign-in",
        ),
        pytest.param(
            ("legacy", "l"),
            ("oidc", "o"),
            ("dev", "d"),
            {("oidc", "o"), ("dev", "d")},
            id="oidc-and-dev-adoptions",
        ),
        pytest.param(
            ("legacy", "l"),
            ("oidc", "s"),
            ("oidc", "s"),
            {("oidc", "s")},
            id="twin-adoptions",
        ),
        pytest.param(
            ("legacy", "s"),
            ("forward_auth", "s"),
            ("forward_auth", "s"),
            {("legacy", "s"), ("forward_auth", "s")},
            id="proxy-twin-legacy-claims",
        ),
        pytest.param(
            ("legacy", "s"),
            ("forward_auth", "s"),
            ("oidc", "s"),
            {("forward_auth", "s"), ("oidc", "s")},
            id="proxy-claim-racing-oidc-claim",
        ),
        pytest.param(
            ("legacy", "s"),
            ("oidc", "s"),
            ("forward_auth", "s"),
            {("forward_auth", "s"), ("oidc", "s")},
            id="oidc-claim-racing-proxy-claim",
        ),
        pytest.param(
            ("legacy", "s"),
            ("forward_auth", "s"),
            ("oidc", "o"),
            {("forward_auth", "s"), ("oidc", "o")},
            id="proxy-claim-racing-oidc-adoption",
        ),
        pytest.param(
            ("legacy", "s"),
            ("oidc", "o"),
            ("forward_auth", "s"),
            {("forward_auth", "s"), ("oidc", "o")},
            id="oidc-adoption-racing-proxy-claim",
        ),
        pytest.param(
            ("legacy", "s"),
            ("forward_auth", "t"),
            ("forward_auth", "s"),
            {("legacy", "s"), ("forward_auth", "s")},
            id="proxy-adoption-racing-proxy-claim",
        ),
        pytest.param(
            ("legacy", "s"),
            ("forward_auth", "s"),
            ("forward_auth", "t"),
            {("legacy", "s"), ("forward_auth", "t")},
            id="proxy-claim-racing-proxy-adoption",
        ),
    ],
)
async def test_identity_writes_racing_on_one_holder_converge(
    session_maker, stored, first, other, final
):
    run = uuid4()
    email = f"holder-{run}@example.com"
    holder = User(
        external_id=f"{stored[1]}-{run}", email=email, display_name="Holder", email_verified=True
    )
    await _commit_users(session_maker, holder, provider=stored[0])
    subjects = {name: f"{name}-{run}" for name in ("s", "t", "a", "b", "l", "o", "d")}
    try:
        (first_user, first_identity_id, _), other_result, _ = await _race(
            session_maker,
            UserSyncRequest(external_id=subjects[first[1]], email=email, display_name="First"),
            UserSyncRequest(external_id=subjects[other[1]], email=email, display_name="Other"),
            first_provider=first[0],
            others_provider=other[0],
        )
        async with session_maker() as check:
            held = await identity_ids_of(check, holder.id)
    finally:
        await _cleanup(session_maker, subjects.values())

    assert first_user.id == holder.id
    assert _outcome(other_result, {holder.id: "holder"}) == ("holder", False)
    assert set(held) == {(provider, subjects[name]) for provider, name in final}
    # Each sync's token is bound to the row it left behind, never to one a racer replaced.
    assert other_result.identity_id == held[(other[0], subjects[other[1]])]
    first_key = (first[0], subjects[first[1]])
    assert first_identity_id == held.get(first_key, first_identity_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("holder_verified", "first", "other_outcome", "holder_after"),
    [
        pytest.param(
            False,
            ("oidc", "owner-email"),
            ("holder", False),
            ("owner-email", {"legacy", "oidc", "forward_auth"}),
            id="holder-verifies-before-proxy-reclaim",
        ),
        pytest.param(
            False,
            ("forward_auth", "owner-email"),
            "Email already in use by another account.",
            ("detached", {"legacy", "oidc"}),
            id="proxy-reclaims-before-holder-verifies",
        ),
        pytest.param(
            True,
            ("oidc", "moved-email"),
            "legacy_identity_conflict",
            ("moved-email", {"legacy", "oidc"}),
            id="holder-moves-email-before-proxy-claim",
        ),
    ],
)
async def test_proxy_legacy_claim_racing_the_holders_own_sign_in(
    session_maker, holder_verified, first, other_outcome, holder_after
):
    # The holder signs in through OIDC as the proxy user signs in with the holder's legacy
    # subject; whichever commits first, the other decides again on the committed holder.
    run = uuid4()
    subject, oidc_subject = f"proxy-{run}", f"oidc-{run}"
    emails = {
        "owner-email": f"owner-{run}@example.com",
        "moved-email": f"moved-{run}@example.com",
    }
    holder = User(
        external_id=subject,
        email=emails["owner-email"],
        display_name="Holder",
        email_verified=holder_verified,
    )
    await _commit_users(session_maker, holder)
    async with session_maker() as setup:
        await setup.execute(
            insert(UserIdentity).values(user_id=holder.id, provider="oidc", subject=oidc_subject)
        )
        await setup.commit()
    syncs = {
        "oidc": UserSyncRequest(
            external_id=oidc_subject, email=emails[first[1]], display_name="Holder"
        ),
        "forward_auth": UserSyncRequest(
            external_id=subject, email=emails["owner-email"], display_name="Proxy"
        ),
    }
    other = "forward_auth" if first[0] == "oidc" else "oidc"
    try:
        _, other_result, _ = await _race(
            session_maker,
            syncs[first[0]],
            syncs[other],
            first_provider=first[0],
            others_provider=other,
        )
        async with session_maker() as check:
            stored = await check.get(User, holder.id)
            held = await identities_of(check, holder.id)
    finally:
        await _cleanup(session_maker, [subject, oidc_subject])

    if isinstance(other_outcome, str):
        assert isinstance(other_result, UserEmailConflictError)
        assert str(other_result) == other_outcome
    else:
        assert _outcome(other_result, {holder.id: "holder"}) == other_outcome
    emails["detached"] = f"{holder.id}@detached.invalid"
    assert (stored.email, {provider for provider, _ in held}) == (
        emails[holder_after[0]],
        holder_after[1],
    )


@pytest.mark.asyncio
async def test_proxy_twins_claiming_a_placeholder_account_converge(session_maker):
    # The twin decides after the first claim moved the holder off its placeholder address and
    # added the forward_auth identity, so it must not mix the two states into a conflict.
    run = uuid4()
    subject = f"proxy-{run}"
    holder = User(
        external_id=subject,
        email=f"{subject}@forward-auth.local",
        display_name="Holder",
        email_verified=True,
    )
    await _commit_users(session_maker, holder)
    sync = UserSyncRequest(
        external_id=subject, email=f"owner-{run}@example.com", display_name="Proxy"
    )
    try:
        (first_user, _, _), other_result, _ = await _race(
            session_maker,
            sync,
            sync,
            first_provider="forward_auth",
            others_provider="forward_auth",
            commit_first_before="_sign_in_existing",
        )
        async with session_maker() as check:
            held = await identities_of(check, holder.id)
    finally:
        await _cleanup(session_maker, [subject])

    assert first_user.id == holder.id
    assert _outcome(other_result, {holder.id: "holder"}) == ("holder", False)
    assert held == {("legacy", subject), ("forward_auth", subject)}


@pytest.mark.asyncio
async def test_proxy_sign_in_decides_again_when_the_holder_moves_off_the_proxy_email(
    session_maker,
):
    # The holder's legacy row is S and it already signs in through the proxy as T, so a proxy
    # sign-in of S with the holder's email takes the email path. The holder moving its email in
    # between leaves no email holder, which must not make S a new account.
    run = uuid4()
    subject, other_subject = f"proxy-{run}", f"other-{run}"
    proxy_email = f"owner-{run}@example.com"
    holder = User(
        external_id=subject, email=proxy_email, display_name="Holder", email_verified=True
    )
    await _commit_users(session_maker, holder)
    async with session_maker() as setup:
        await setup.execute(
            insert(UserIdentity).values(
                user_id=holder.id, provider="forward_auth", subject=other_subject
            )
        )
        await setup.commit()
    try:
        _, other_result, _ = await _race(
            session_maker,
            UserSyncRequest(
                external_id=other_subject, email=f"moved-{run}@example.com", display_name="H"
            ),
            UserSyncRequest(external_id=subject, email=proxy_email, display_name="Proxy"),
            first_provider="forward_auth",
            others_provider="forward_auth",
            commit_first_before="get_by_email",
        )
        async with session_maker() as check:
            held = await identities_of(check, holder.id)
            proxy_owner = await UserService(check).get_by_identity("forward_auth", subject)
    finally:
        await _cleanup(session_maker, [subject, other_subject])

    assert isinstance(other_result, UserEmailConflictError)
    assert str(other_result) == "legacy_identity_conflict"
    assert proxy_owner is None
    assert held == {("legacy", subject), ("forward_auth", other_subject)}


@pytest.mark.asyncio
async def test_proxy_sign_in_retries_when_its_identity_appears_before_the_holder_read(
    session_maker,
):
    # Between this sign-in's identity lookup and its holder read, a twin reclaims the address
    # into a new account with ('forward_auth', S), then the holder verifies a new address. The
    # holder alone now looks like a conflict, but the twin's identity is this caller's.
    run = uuid4()
    subject, oidc_subject = f"proxy-{run}", f"oidc-{run}"
    proxy_email, holder_email = f"owner-{run}@example.com", f"moved-{run}@example.com"
    holder = User(
        external_id=subject, email=proxy_email, display_name="Holder", email_verified=False
    )
    await _commit_users(session_maker, holder)
    async with session_maker() as setup:
        await setup.execute(
            insert(UserIdentity).values(user_id=holder.id, provider="oidc", subject=oidc_subject)
        )
        await setup.commit()
    proxy = UserSyncRequest(external_id=subject, email=proxy_email, display_name="Proxy")
    try:
        async with session_maker() as session:
            service = UserService(session)
            original = service._legacy_holder_of_proxy_user

            async def after_twins(*args, **kwargs):
                for sync, provider in (
                    (proxy, "forward_auth"),
                    (
                        UserSyncRequest(
                            external_id=oidc_subject, email=holder_email, display_name="Holder"
                        ),
                        "oidc",
                    ),
                ):
                    async with session_maker() as twin:
                        await UserService(twin).sync_from_oidc(
                            sync, provider=provider, email_verified=True
                        )
                        await twin.commit()
                return await original(*args, **kwargs)

            service._legacy_holder_of_proxy_user = after_twins
            user, _, is_new = await service.sync_from_oidc(
                proxy, provider="forward_auth", email_verified=True
            )
            await session.commit()
        async with session_maker() as check:
            owner = await UserService(check).get_by_identity("forward_auth", subject)
    finally:
        await _cleanup(session_maker, [subject, oidc_subject])

    assert (user.id, is_new) == (owner.id, False)
    assert owner.id != holder.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("violation", "surfaces"),
    [
        pytest.param("not-null", IntegrityError, id="not-null-is-a-bug"),
        pytest.param("external-id-unique", IntegrityError, id="frozen-external-id-is-a-bug"),
        pytest.param("identity-unique", UserEmailConflictError, id="identity-unique-is-a-race"),
    ],
)
async def test_only_a_violation_a_concurrent_sign_in_can_cause_is_retried(
    db_session, test_user, violation, surfaces
):
    service = UserService(db_session)
    insert_identity = service._insert_identity

    async def violating(user_id, provider, subject):
        if violation == "not-null":
            await db_session.execute(
                insert(UserIdentity).values(user_id=user_id, provider=provider, subject=None)
            )
        elif violation == "external-id-unique":
            await db_session.execute(
                update(User).where(User.id == user_id).values(external_id=test_user.external_id)
            )
        else:
            await insert_identity(user_id, provider, subject)
        return await insert_identity(user_id, provider, subject)

    service._insert_identity = violating
    run = uuid4()
    sync = UserSyncRequest(
        external_id=f"new-{run}", email=f"new-{run}@example.com", display_name="N"
    )

    with pytest.raises(surfaces):
        await service.sync_from_oidc(sync, provider="oidc", email_verified=True)
