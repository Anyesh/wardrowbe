from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserIdentity
from tests.migration_helpers import migration_downgrade

PREVIOUS = "6c1e8f2a9d47"


def _user(external_id: str | None) -> User:
    user_id = uuid4()
    return User(
        id=user_id,
        external_id=external_id,
        email=f"mig-{user_id}@example.com",
        display_name="Migration",
        email_verified=True,
    )


async def _users(db_session: AsyncSession, ids: list[UUID]) -> dict[UUID, tuple]:
    rows = await db_session.execute(
        text("SELECT id, external_id, created_at, updated_at FROM users WHERE id = ANY(:ids)"),
        {"ids": ids},
    )
    return {row.id: (row.external_id, row.created_at, row.updated_at) for row in rows}


async def _identities(db_session: AsyncSession, ids: list[UUID]) -> set[tuple]:
    rows = await db_session.execute(
        select(
            UserIdentity.user_id,
            UserIdentity.provider,
            UserIdentity.subject,
            UserIdentity.created_at,
        ).where(UserIdentity.user_id.in_(ids))
    )
    return set(rows.all())


async def _external_id_nullable(db_session: AsyncSession) -> bool:
    nullable = await db_session.scalar(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'external_id'"
        )
    )
    return nullable == "YES"


async def test_backfills_every_user_as_a_legacy_identity(db_session: AsyncSession):
    run = uuid4().hex
    users = [_user(f"backfill-{run}-{n}") for n in range(3)]
    async with migration_downgrade(db_session, PREVIOUS):
        db_session.add_all(users)
        await db_session.commit()

    ids = [user.id for user in users]
    stored = await _users(db_session, ids)
    assert await _identities(db_session, ids) == {
        (user_id, "legacy", external_id, created_at)
        for user_id, (external_id, created_at, _updated_at) in stored.items()
    }
    assert {external_id for external_id, _, _ in stored.values()} == {
        f"backfill-{run}-{n}" for n in range(3)
    }
    assert await _external_id_nullable(db_session)


async def test_downgrade_keeps_each_subject_on_one_user_and_never_fails(
    db_session: AsyncSession,
):
    run = uuid4().hex
    oidc_owner = _user(f"frozen-oidc-{run}")
    legacy_rival = _user(f"frozen-legacy-{run}")
    dev_over_legacy = _user(f"frozen-dev-{run}")
    proxy_alice = _user(None)
    oidc_alice = _user(None)
    proxy_only = _user(None)
    frozen_only = _user(f"frozen-only-{run}")
    frozen_shadowed = _user(f"shadowed-{run}")
    shadowing_oidc = _user(None)
    revoked = _user(None)
    placeholder_lookalike = _user(None)
    users = [
        oidc_owner,
        legacy_rival,
        dev_over_legacy,
        proxy_alice,
        oidc_alice,
        proxy_only,
        frozen_only,
        frozen_shadowed,
        shadowing_oidc,
        revoked,
        placeholder_lookalike,
    ]
    lookalike_subject = f"downgraded:{uuid4()}:{run}"
    db_session.add_all(users)
    await db_session.flush()
    db_session.add_all(
        [
            UserIdentity(user_id=oidc_owner.id, provider="oidc", subject=f"shared-{run}"),
            UserIdentity(user_id=legacy_rival.id, provider="legacy", subject=f"shared-{run}"),
            UserIdentity(user_id=dev_over_legacy.id, provider="dev", subject=f"dev-{run}"),
            UserIdentity(user_id=dev_over_legacy.id, provider="legacy", subject=f"old-{run}"),
            UserIdentity(user_id=proxy_alice.id, provider="forward_auth", subject=f"alice-{run}"),
            UserIdentity(user_id=oidc_alice.id, provider="oidc", subject=f"alice-{run}"),
            UserIdentity(user_id=proxy_only.id, provider="forward_auth", subject=f"bob-{run}"),
            UserIdentity(user_id=shadowing_oidc.id, provider="oidc", subject=f"shadowed-{run}"),
            UserIdentity(
                user_id=placeholder_lookalike.id, provider="legacy", subject=lookalike_subject
            ),
        ]
    )
    await db_session.commit()
    # Read before the downgrade because the helper's rollback expires the ORM objects.
    ids = [user.id for user in users]
    kept = {
        oidc_owner.id: f"shared-{run}",
        dev_over_legacy.id: f"dev-{run}",
        oidc_alice.id: f"alice-{run}",
        frozen_only.id: f"frozen-only-{run}",
        shadowing_oidc.id: f"shadowed-{run}",
        placeholder_lookalike.id: lookalike_subject,
    }
    before = await _users(db_session, ids)

    async with migration_downgrade(db_session, PREVIOUS):
        after = await _users(db_session, ids)
        assert not await _external_id_nullable(db_session)
        assert not await db_session.scalar(
            text("SELECT to_regclass('user_identities') IS NOT NULL")
        )

    for user_id in ids:
        external_id = after[user_id][0]
        if user_id in kept:
            assert external_id == kept[user_id]
        else:
            assert external_id.startswith(f"downgraded:{user_id}:")
        assert after[user_id][2] == before[user_id][2], "downgrade must not bump updated_at"
    assert len({row[0] for row in after.values()}) == len(ids)

    assert await _identities(db_session, ids) == {
        (user_id, "legacy", external_id, created_at)
        for user_id, (external_id, created_at, _updated_at) in after.items()
    }
