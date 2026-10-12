from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.auth import create_access_token
from app.config import Settings, get_settings
from app.models import User, UserIdentity
from app.schemas.user import UserSyncRequest
from app.services.user_service import FORWARD_AUTH, UserEmailConflictError, UserService
from app.utils.auth import decode_token
from app.utils.rate_limit import _get_client_ip, check_rate_limit
from tests.identity_helpers import (
    add_users_with_identities,
    identities_of,
    identity_ids_of,
    legacy_token,
    user_of_subject,
)

PROXY_SECRET = "s" * 32
# The first of each pair ends in a UTF-8 byte that Latin-1 reads as whitespace (\xa0, \x85), so
# trimming before decoding would collapse it onto the second.
# Its UTF-8 bytes include 0x90 and 0x8d, which Latin-1 reads as C1 control characters.
LATIN1_NAME = "名前".encode().decode("latin-1")
TRAILING_BYTE_PAIRS = [("voilà", "voilÃ"), ("Å", "Ã")]
SYNC_URL = "/api/v1/auth/sync"


def _settings(**overrides) -> Settings:
    return get_settings().model_copy(update=overrides)


def _forward_auth_only() -> Settings:
    return _settings(debug=False, forward_auth_secret=PROXY_SECRET)


def _forward_auth_and_oidc() -> Settings:
    return _settings(
        debug=False,
        forward_auth_secret=PROXY_SECRET,
        oidc_issuer_url="https://auth.example.com",
        oidc_client_id="web-client",
        oidc_mobile_client_id=None,
    )


def _proxy_headers(
    user: str | bytes = "tinyauth-alice",
    email: str = "Alice@Example.com",
    name: str | bytes = "Alice",
    secret: str = PROXY_SECRET,
) -> dict:
    return {
        "X-Forward-Auth-Secret": secret,
        "Remote-User": user,
        "Remote-Email": email,
        "Remote-Name": name,
    }


async def _token_user(db: AsyncSession, token: str, provider: str, subject: str) -> User:
    payload = decode_token(token)
    user = await UserService(db).get_by_token(payload)
    assert user is not None
    assert payload.iid == str((await identity_ids_of(db, user.id))[(provider, subject)])
    return user


async def _proxy_user_bearer(db: AsyncSession, subject: str) -> dict:
    # No external_id, as sign-in leaves it NULL, so the switch check cannot lean on it.
    user = User(email=f"{uuid4()}@example.com", display_name="Voilà")
    db.add(user)
    await db.flush()
    identity = UserIdentity(user_id=user.id, provider=FORWARD_AUTH, subject=subject)
    db.add(identity)
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, identity.id)}"}


class TestForwardAuthSync:
    @pytest.mark.asyncio
    async def test_valid_secret_issues_jwt_for_remote_user(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers())

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "alice@example.com"
        assert data["display_name"] == "Alice"
        assert data["is_new_user"] is True
        assert data["onboarding_completed"] is False
        user = await _token_user(db_session, data["access_token"], "forward_auth", "tinyauth-alice")
        assert (str(user.id), user.external_id) == (data["id"], None)

    @pytest.mark.asyncio
    async def test_body_identity_is_ignored(self, client: AsyncClient, db_session: AsyncSession):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(
                SYNC_URL,
                headers=_proxy_headers(),
                json={
                    "external_id": "body-attacker",
                    "email": "victim@example.com",
                    "display_name": "Mallory",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "alice@example.com"
        assert data["display_name"] == "Alice"
        await _token_user(db_session, data["access_token"], "forward_auth", "tinyauth-alice")
        assert await user_of_subject(db_session, "body-attacker") is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name",
        [None, "\u200b\u2060".encode(), "\u0301".encode(), b"\x01"],
        ids=["missing", "zero-width-only", "combining-mark-only", "control-only"],
    )
    async def test_display_name_falls_back_to_remote_user(
        self, client: AsyncClient, name: bytes | None
    ):
        headers = _proxy_headers(name=name)
        if name is None:
            del headers["Remote-Name"]
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=headers)

        assert response.status_code == 200
        assert response.json()["display_name"] == "tinyauth-alice"

    @pytest.mark.asyncio
    async def test_utf8_remote_name_is_decoded(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(name="José 王".encode()))

        assert response.status_code == 200
        assert response.json()["display_name"] == "José 王"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("name", "stored"),
        [
            pytest.param("n" * 150, "n" * 100, id="overlong"),
            pytest.param("a" + "\t" * 60 + "b" * 98, "a " + "b" * 98, id="flattened-before-cut"),
        ],
    )
    async def test_remote_name_follows_the_sync_name_rules(
        self, client: AsyncClient, name: str, stored: str
    ):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(name=name))

        assert response.status_code == 200
        assert response.json()["display_name"] == stored

    @pytest.mark.asyncio
    async def test_second_sync_returns_same_user(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_only()):
            first = await client.post(SYNC_URL, headers=_proxy_headers())
            second = await client.post(SYNC_URL, headers=_proxy_headers())

        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["is_new_user"] is False

    @pytest.mark.asyncio
    async def test_proxy_identity_joins_the_verified_account_with_its_email(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(
                SYNC_URL,
                headers=_proxy_headers(user="tinyauth-bob", email=test_user.email),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["is_new_user"] is False
        await _token_user(db_session, data["access_token"], "forward_auth", "tinyauth-bob")
        assert await identities_of(db_session, test_user.id) == {
            ("legacy", test_user.external_id),
            ("forward_auth", "tinyauth-bob"),
        }


class TestForwardAuthLegacyClaim:
    # A pre-identities user's external_id became a legacy identity. A proxy username can equal
    # it, so a proxy sign-in only takes it over when the account's verified email shows the
    # proxy user is its owner.
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("subject", "stored_email", "verified", "holds_proxy_identity", "outcome"),
        [
            pytest.param("alice", "proxy", True, False, "claim", id="claims-by-proxy-email"),
            pytest.param(
                "Alice", "placeholder", True, False, "claim", id="claims-by-pre-identities-email"
            ),
            pytest.param(
                "alice", "proxy", True, True, "adopt", id="same-email-replaces-proxy-identity"
            ),
            pytest.param("alice", "other", True, False, "conflict", id="other-email-conflicts"),
            pytest.param(
                "al ice", "other", True, False, "conflict", id="subject-not-an-email-local-part"
            ),
            pytest.param(
                "alice", "placeholder", True, True, "conflict", id="placeholder-with-proxy-identity"
            ),
            pytest.param(
                "alice", "other", True, True, "conflict", id="other-email-with-proxy-identity"
            ),
            pytest.param("alice", "proxy", False, False, "reclaim", id="unverified-is-reclaimed"),
            pytest.param("alice", "other", False, False, "new", id="unverified-is-ignored"),
        ],
    )
    async def test_proxy_sign_in_of_a_legacy_subject(
        self,
        db_session: AsyncSession,
        subject: str,
        stored_email: str,
        verified: bool,
        holds_proxy_identity: bool,
        outcome: str,
    ):
        run = uuid4()
        subject = f"{subject}-{run}"
        emails = {
            "proxy": f"real-{run}@example.net",
            "placeholder": f"{subject}@example.com",
            "other": f"someone-{run}@example.com",
        }
        stored = User(
            external_id=subject,
            email=emails[stored_email],
            display_name="Stored",
            email_verified=verified,
        )
        await add_users_with_identities(db_session, stored)
        before = {("legacy", subject)}
        if holds_proxy_identity:
            db_session.add(
                UserIdentity(user_id=stored.id, provider=FORWARD_AUTH, subject=f"old-{run}")
            )
            before.add((FORWARD_AUTH, f"old-{run}"))
        await db_session.commit()
        sync = UserSyncRequest(external_id=subject, email=emails["proxy"], display_name="Proxy")
        service = UserService(db_session)

        if outcome == "conflict":
            with pytest.raises(UserEmailConflictError, match="^legacy_identity_conflict$"):
                await service.sync_from_oidc(sync, provider=FORWARD_AUTH, email_verified=True)
            await db_session.refresh(stored)
            assert (stored.email, await identities_of(db_session, stored.id)) == (
                emails[stored_email],
                before,
            )
            assert await service.get_by_identity(FORWARD_AUTH, subject) is None
            return

        user, identity_id, is_new = await service.sync_from_oidc(
            sync, provider=FORWARD_AUTH, email_verified=True
        )
        await db_session.refresh(stored)
        held = await identity_ids_of(db_session, user.id)
        assert identity_id == held[(FORWARD_AUTH, subject)]
        assert (user.email, user.email_verified) == (emails["proxy"], True)
        if outcome in ("claim", "adopt"):
            assert (user.id, is_new) == (stored.id, False)
            assert set(held) == {("legacy", subject), (FORWARD_AUTH, subject)}
            # The kept legacy row keeps the account's pre-upgrade sessions working.
            pre_upgrade = await service.get_by_token(decode_token(legacy_token(subject)))
            assert pre_upgrade is not None and pre_upgrade.id == stored.id
        else:
            assert (user.id != stored.id, is_new) == (True, True)
            assert set(held) == {(FORWARD_AUTH, subject)}
            assert await identities_of(db_session, stored.id) == before
            assert stored.email == (
                f"{stored.id}@detached.invalid" if outcome == "reclaim" else emails["other"]
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("proxy_user", "stored_subject", "stored_email"),
        [
            pytest.param("bob", "bob", "bob@forward-auth.local", id="frontend-placeholder"),
            pytest.param("åsa", "Ã¥sa", "Ã¥sa@forward-auth.local", id="username-read-as-latin1"),
            pytest.param(
                "名前",
                LATIN1_NAME,
                f"{LATIN1_NAME}@forward-auth.local",
                id="cjk-username-read-as-latin1",
            ),
        ],
    )
    async def test_proxy_sign_in_claims_what_older_forward_auth_stored(
        self, db_session: AsyncSession, proxy_user: str, stored_subject: str, stored_email: str
    ):
        run = uuid4()
        proxy_user, stored_subject = f"{run}{proxy_user}", f"{run}{stored_subject}"
        stored = User(
            external_id=stored_subject,
            email=f"{run}{stored_email}",
            display_name="Stored",
            email_verified=True,
        )
        await add_users_with_identities(db_session, stored)
        await db_session.commit()
        sync = UserSyncRequest(
            external_id=proxy_user, email=f"real-{run}@example.net", display_name="Proxy"
        )

        user, identity_id, is_new = await UserService(db_session).sync_from_oidc(
            sync, provider=FORWARD_AUTH, email_verified=True
        )

        held = await identity_ids_of(db_session, user.id)
        assert (user.id, is_new, user.email) == (stored.id, False, f"real-{run}@example.net")
        assert set(held) == {("legacy", stored_subject), (FORWARD_AUTH, proxy_user)}
        assert identity_id == held[(FORWARD_AUTH, proxy_user)]

    @pytest.mark.asyncio
    async def test_username_spelled_as_another_users_latin1_row_does_not_claim_it(
        self, db_session: AsyncSession
    ):
        # Older forward-auth stored "Jürgen" as "JÃ¼rgen", so that row is Jürgen's even though
        # a proxy username can be written as "JÃ¼rgen" literally.
        run = uuid4()
        stored_subject = f"{run}Jürgen".encode().decode("latin-1")
        stored = User(
            external_id=stored_subject,
            email=f"{stored_subject}@forward-auth.local",
            display_name="Jürgen",
            email_verified=True,
        )
        await add_users_with_identities(db_session, stored)
        await db_session.commit()
        sync = UserSyncRequest(
            external_id=stored_subject, email=f"other-{run}@example.net", display_name="Other"
        )

        user, _, is_new = await UserService(db_session).sync_from_oidc(
            sync, provider=FORWARD_AUTH, email_verified=True
        )

        assert (user.id != stored.id, is_new) == (True, True)
        assert await identities_of(db_session, stored.id) == {("legacy", stored_subject)}


class TestForwardAuthRejections:
    @pytest.mark.asyncio
    async def test_wrong_secret_returns_401(self, client: AsyncClient, db_session: AsyncSession):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(secret="x" * 32))

        assert response.status_code == 401
        assert await user_of_subject(db_session, "tinyauth-alice") is None

    @pytest.mark.asyncio
    async def test_empty_secret_returns_401(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(secret=""))

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_secret_returns_401_when_forward_auth_is_the_only_mode(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        headers = _proxy_headers()
        del headers["X-Forward-Auth-Secret"]
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(
                SYNC_URL,
                headers=headers,
                json={
                    "external_id": "tinyauth-alice",
                    "email": "alice@example.com",
                    "display_name": "Alice",
                },
            )

        assert response.status_code == 401
        assert await user_of_subject(db_session, "tinyauth-alice") is None

    @pytest.mark.asyncio
    async def test_secret_header_rejected_when_forward_auth_not_configured(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        with patch("app.api.auth.settings", _settings(debug=True, forward_auth_secret=None)):
            response = await client.post(
                SYNC_URL,
                headers=_proxy_headers(),
                json={
                    "external_id": "dev-user",
                    "email": "dev@example.com",
                    "display_name": "Dev",
                },
            )

        assert response.status_code == 401
        assert await user_of_subject(db_session, "dev-user") is None

    @pytest.mark.asyncio
    async def test_missing_remote_email_returns_400(self, client: AsyncClient):
        headers = _proxy_headers()
        del headers["Remote-Email"]
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(
                SYNC_URL,
                headers=headers,
                json={
                    "external_id": "tinyauth-alice",
                    "email": "body@example.com",
                    "display_name": "Alice",
                },
            )

        assert response.status_code == 400
        assert "Remote-Email" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_malformed_remote_email_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(email="not-an-email"))

        assert response.status_code == 400
        assert "Remote-Email" in response.json()["detail"]
        assert await user_of_subject(db_session, "tinyauth-alice") is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user",
        [None, "\u200b\ufeff".encode(), "\u0301".encode(), b"mallory, tinyauth-alice"],
        ids=["missing", "zero-width-only", "combining-mark-only", "comma-joined-duplicate"],
    )
    async def test_missing_blank_or_joined_remote_user_returns_400(
        self, client: AsyncClient, db_session: AsyncSession, user: bytes | None
    ):
        headers = _proxy_headers(user=user)
        if user is None:
            del headers["Remote-User"]
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=headers)

        assert response.status_code == 400
        assert "Remote-User" in response.json()["detail"]
        if user is not None:
            assert await user_of_subject(db_session, user.decode()) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("name", "client_value"),
        [
            ("Remote-User", "mallory"),
            ("Remote-Email", "mallory@example.com"),
            ("Remote-Name", "Mallory"),
            ("X-Forward-Auth-Secret", PROXY_SECRET),
        ],
        ids=["remote-user", "remote-email", "remote-name", "secret"],
    )
    async def test_repeated_proxy_header_returns_400(
        self, client: AsyncClient, db_session: AsyncSession, name: str, client_value: str
    ):
        # The client's line comes first, as when a proxy appends its header instead of replacing.
        headers = [(name, client_value), *_proxy_headers().items()]
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=headers)

        assert response.status_code == 400
        assert name in response.json()["detail"]
        assert await user_of_subject(db_session, "mallory") is None
        assert await user_of_subject(db_session, "tinyauth-alice") is None

    @pytest.mark.asyncio
    async def test_overlong_remote_user_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(user="u" * 256))

        assert response.status_code == 400
        assert "Remote-User" in response.json()["detail"]
        assert await user_of_subject(db_session, "u" * 256) is None

    @pytest.mark.asyncio
    async def test_remote_user_at_the_column_limit_is_accepted(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(user="u" * 255))

        assert response.status_code == 200
        await _token_user(db_session, response.json()["access_token"], "forward_auth", "u" * 255)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user,expected",
        [
            ("voilà".encode(), "voilà"),
            ("voilÃ".encode(), "voilÃ"),
            ("bob\u00a0".encode(), "bob\u00a0"),
            (b"carol\t ", "carol"),
        ],
    )
    async def test_remote_user_is_decoded_before_trimming(
        self, client: AsyncClient, db_session: AsyncSession, user: bytes, expected: str
    ):
        prefix = str(uuid4())
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(
                SYNC_URL,
                headers=_proxy_headers(
                    user=f" {prefix}".encode() + user, email=f"{prefix}@example.com"
                ),
            )

        assert response.status_code == 200
        await _token_user(
            db_session, response.json()["access_token"], "forward_auth", f"{prefix}{expected}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("user", "other"), TRAILING_BYTE_PAIRS, ids=["trailing-nbsp", "trailing-nel"]
    )
    async def test_remote_users_differing_in_a_trailing_byte_get_separate_accounts(
        self, client: AsyncClient, user: str, other: str
    ):
        prefix = str(uuid4())
        with patch("app.api.auth.settings", _forward_auth_only()):
            first = await client.post(
                SYNC_URL,
                headers=_proxy_headers(
                    user=f"{prefix}{user}".encode(), email=f"{prefix}-a@example.com"
                ),
            )
            second = await client.post(
                SYNC_URL,
                headers=_proxy_headers(
                    user=f"{prefix}{other}".encode(), email=f"{prefix}-b@example.com"
                ),
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] != second.json()["id"]


class TestForwardAuthRateLimit:
    @pytest.mark.asyncio
    async def test_successful_syncs_do_not_consume_the_limit(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_only()):
            statuses = [
                (await client.post(SYNC_URL, headers=_proxy_headers())).status_code
                for _ in range(15)
            ]

        assert statuses == [200] * 15

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("trusted_proxy_count", "forwarded_for"),
        [
            (0, "203.0.113.{i}"),
            (1, "203.0.113.{i}, 198.51.100.7"),
        ],
        ids=["direct-with-spoofed-header", "behind-one-proxy-with-spoofed-prefix"],
    )
    async def test_failed_attempts_are_limited_without_blocking_valid_ones(
        self, client: AsyncClient, trusted_proxy_count: int, forwarded_for: str
    ):
        bad = _proxy_headers(secret="x" * 32)
        with (
            patch("app.api.auth.settings", _forward_auth_only()),
            patch(
                "app.utils.rate_limit.get_settings",
                return_value=_settings(trusted_proxy_count=trusted_proxy_count),
            ),
        ):
            statuses = [
                (
                    await client.post(
                        SYNC_URL, headers={**bad, "X-Forwarded-For": forwarded_for.format(i=i)}
                    )
                ).status_code
                for i in range(11)
            ]
            valid = await client.post(SYNC_URL, headers=_proxy_headers())

        assert statuses == [401] * 10 + [429]
        assert valid.status_code == 200

    @pytest.mark.asyncio
    async def test_hits_inside_the_window_do_not_extend_it(self):
        key = f"rate_limit:test:{uuid4()}"
        redis = Redis.from_url(get_settings().redis_url)
        try:
            await check_rate_limit(key, 10, 60)
            assert 0 < await redis.ttl(key) <= 60
            # Stands in for most of the window passing, which the second hit must not restart.
            await redis.expire(key, 5)
            await check_rate_limit(key, 10, 60)

            assert int(await redis.get(key)) == 2
            assert 0 < await redis.ttl(key) <= 5
        finally:
            await redis.delete(key)
            await redis.aclose()

    @pytest.mark.parametrize(
        ("trusted_proxy_count", "forwarded_for", "peer", "expected"),
        [
            (0, ["203.0.113.9"], "10.0.0.5", "10.0.0.5"),
            (0, [], None, "unknown"),
            (1, [], "10.0.0.5", "10.0.0.5"),
            (1, ["198.51.100.7"], "10.0.0.5", "198.51.100.7"),
            (1, ["203.0.113.9, 198.51.100.7"], "10.0.0.5", "198.51.100.7"),
            (1, ["203.0.113.9", "198.51.100.7"], "10.0.0.5", "198.51.100.7"),
            (1, [" 203.0.113.9 ,, 2001:db8::7 "], "10.0.0.5", "2001:db8::7"),
            (2, ["203.0.113.9, 198.51.100.7, 172.18.0.1"], "10.0.0.5", "198.51.100.7"),
            (2, ["198.51.100.7"], "10.0.0.5", "10.0.0.5"),
            (1, ["203.0.113.9, not-an-ip"], "10.0.0.5", "10.0.0.5"),
            (1, ["203.0.113.9, 198.51.100.7:4711"], "10.0.0.5", "198.51.100.7"),
            (1, ["[2001:db8::7]:4711"], "10.0.0.5", "2001:db8::7"),
            (1, ["2001:db8::7:4711"], "10.0.0.5", "2001:db8::7:4711"),
            (1, ["198.51.100.7:http"], "10.0.0.5", "10.0.0.5"),
            (1, ["[198.51.100.7]:4711"], "10.0.0.5", "10.0.0.5"),
            (1, ["::ffff:198.51.100.7"], "10.0.0.5", "198.51.100.7"),
            (1, ["[::ffff:198.51.100.7]:4711"], "10.0.0.5", "198.51.100.7"),
            (1, ["2600:1f18:abcd:1234:5:6:7:8"], "10.0.0.5", "2600:1f18:abcd:1234::/64"),
            (1, ["fd00:1:2:3::5"], "10.0.0.5", "fd00:1:2:3::5"),
            (1, ["fe80::5"], "10.0.0.5", "fe80::5"),
            (0, [], "::ffff:10.0.0.5", "10.0.0.5"),
            (0, [], "2600:1f18:abcd:1234::9", "2600:1f18:abcd:1234::/64"),
            (1, ["not-an-ip"], "::ffff:10.0.0.5", "10.0.0.5"),
        ],
        ids=[
            "zero-hops-ignores-header",
            "zero-hops-without-peer",
            "no-header-uses-peer",
            "one-hop",
            "one-hop-spoofed-prefix",
            "one-hop-repeated-header-lines",
            "one-hop-whitespace-empty-entries-ipv6",
            "two-hops-spoofed-prefix",
            "fewer-entries-than-hops-uses-peer",
            "malformed-trusted-entry-uses-peer",
            "one-hop-ipv4-with-port",
            "one-hop-bracketed-ipv6-with-port",
            "one-hop-ipv6-ending-in-port-like-group-is-an-address",
            "one-hop-non-numeric-port-uses-peer",
            "one-hop-bracketed-ipv4-uses-peer",
            "one-hop-ipv4-mapped-ipv6-folds-to-ipv4",
            "one-hop-bracketed-ipv4-mapped-ipv6-with-port",
            "one-hop-global-ipv6-buckets-on-its-64",
            "one-hop-ula-ipv6-stays-distinct",
            "one-hop-link-local-ipv6-stays-distinct",
            "ipv4-mapped-peer-folds-to-ipv4",
            "global-ipv6-peer-buckets-on-its-64",
            "malformed-entry-falls-back-to-normalised-peer",
        ],
    )
    def test_client_ip_is_the_entry_the_trusted_proxies_appended(
        self, trusted_proxy_count, forwarded_for, peer, expected
    ):
        request = Request(
            {
                "type": "http",
                "headers": [(b"x-forwarded-for", line.encode()) for line in forwarded_for],
                "client": (peer, 4321) if peer else None,
            }
        )
        with patch(
            "app.utils.rate_limit.get_settings",
            return_value=_settings(trusted_proxy_count=trusted_proxy_count),
        ):
            assert _get_client_ip(request) == expected

    @pytest.mark.asyncio
    async def test_secret_is_checked_before_the_rate_limit(self, client: AsyncClient):
        limiter = AsyncMock()
        with (
            patch("app.api.auth.settings", _forward_auth_only()),
            patch("app.api.auth.rate_limit_by_ip", limiter),
        ):
            ok = await client.post(SYNC_URL, headers=_proxy_headers())
            limiter.assert_not_awaited()
            bad = await client.post(SYNC_URL, headers=_proxy_headers(secret="x" * 32))

        assert ok.status_code == 200
        assert bad.status_code == 401
        limiter.assert_awaited_once()


class TestForwardAuthPrecedence:
    def test_debug_with_secret_is_not_dev_mode(self):
        assert _settings(debug=True, forward_auth_secret=PROXY_SECRET).dev_mode is False

    @pytest.mark.asyncio
    async def test_debug_with_secret_takes_forward_auth_branch(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        with patch(
            "app.api.auth.settings", _settings(debug=True, forward_auth_secret=PROXY_SECRET)
        ):
            with_header = await client.post(
                SYNC_URL,
                headers=_proxy_headers(),
                json={"external_id": "dev-typed", "email": "dev@example.com", "display_name": "D"},
            )
            without_header = await client.post(
                SYNC_URL,
                json={"external_id": "dev-typed", "email": "dev@example.com", "display_name": "D"},
            )

        assert with_header.status_code == 200
        await _token_user(
            db_session, with_header.json()["access_token"], "forward_auth", "tinyauth-alice"
        )
        assert without_header.status_code == 401
        assert await user_of_subject(db_session, "dev-typed") is None

    @pytest.mark.asyncio
    async def test_oidc_and_secret_uses_forward_auth_when_header_present(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        validator = AsyncMock()
        with (
            patch("app.api.auth.settings", _forward_auth_and_oidc()),
            patch("app.api.auth.validate_oidc_id_token", validator),
        ):
            response = await client.post(SYNC_URL, headers=_proxy_headers())

        assert response.status_code == 200
        await _token_user(
            db_session, response.json()["access_token"], "forward_auth", "tinyauth-alice"
        )
        validator.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_oidc_and_secret_uses_oidc_when_header_absent(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        validator = AsyncMock(
            return_value={
                "sub": "oidc-carol",
                "email": "carol@example.com",
                "email_verified": True,
            }
        )
        with (
            patch("app.api.auth.settings", _forward_auth_and_oidc()),
            patch("app.api.auth.validate_oidc_id_token", validator),
        ):
            response = await client.post(
                SYNC_URL,
                json={
                    "external_id": "oidc-carol",
                    "display_name": "Carol",
                    "id_token": "mobile-id-token",
                },
            )

        assert response.status_code == 200
        await _token_user(db_session, response.json()["access_token"], "oidc", "oidc-carol")
        validator.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_oidc_token_through_proxy_without_remote_user_uses_oidc(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        validator = AsyncMock(
            return_value={
                "sub": "oidc-dave",
                "email": "dave@example.com",
                "email_verified": True,
            }
        )
        with (
            patch("app.api.auth.settings", _forward_auth_and_oidc()),
            patch("app.api.auth.validate_oidc_id_token", validator),
        ):
            response = await client.post(
                SYNC_URL,
                headers={"X-Forward-Auth-Secret": PROXY_SECRET},
                json={
                    "external_id": "oidc-dave",
                    "display_name": "Dave",
                    "id_token": "mobile-id-token",
                },
            )

        assert response.status_code == 200
        await _token_user(db_session, response.json()["access_token"], "oidc", "oidc-dave")
        validator.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remote_user_wins_over_body_id_token(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        validator = AsyncMock()
        with (
            patch("app.api.auth.settings", _forward_auth_and_oidc()),
            patch("app.api.auth.validate_oidc_id_token", validator),
        ):
            response = await client.post(
                SYNC_URL,
                headers=_proxy_headers(),
                json={
                    "external_id": "oidc-mallory",
                    "display_name": "Mallory",
                    "id_token": "forged",
                },
            )

        assert response.status_code == 200
        await _token_user(
            db_session, response.json()["access_token"], "forward_auth", "tinyauth-alice"
        )
        validator.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_body_id_token_without_oidc_configured_stays_on_forward_auth(
        self, client: AsyncClient
    ):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(
                SYNC_URL,
                headers={"X-Forward-Auth-Secret": PROXY_SECRET},
                json={"external_id": "x", "display_name": "X", "id_token": "t"},
            )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_oidc_path_still_requires_a_body(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_and_oidc()):
            response = await client.post(SYNC_URL)

        assert response.status_code == 422


class TestForwardAuthSettings:
    @pytest.mark.parametrize(
        "secret",
        ["s" * 31, "é" * 32, " " + "s" * 32, "s" * 16 + " " + "s" * 16, "s" * 32 + "\t"],
        ids=["short", "non-ascii", "leading-space", "inner-space", "trailing-tab"],
    )
    def test_secret_a_proxy_cannot_send_verbatim_fails_validation(self, secret: str):
        settings = Settings(secret_key="a-strong-custom-secret", forward_auth_secret=secret)
        with pytest.raises(RuntimeError, match="FORWARD_AUTH_SECRET"):
            settings.validate_security()

    def test_secret_of_minimum_length_is_a_configured_mode(self):
        settings = Settings(secret_key="a-strong-custom-secret", forward_auth_secret=PROXY_SECRET)
        assert settings.forward_auth_configured is True
        assert settings.validate_security() is None
        assert settings.get_auth_mode() == "forward-auth"

    def test_unset_secret_is_not_configured(self):
        settings = Settings(debug=True, secret_key="a-strong-custom-secret")
        assert settings.forward_auth_configured is False
        assert settings.get_auth_mode() == "dev"

    def test_debug_with_secret_reports_forward_auth(self):
        settings = Settings(
            debug=True, secret_key="a-strong-custom-secret", forward_auth_secret=PROXY_SECRET
        )
        assert settings.get_auth_mode() == "forward-auth"

    def test_secret_with_oidc_reports_both(self):
        settings = Settings(
            secret_key="a-strong-custom-secret",
            forward_auth_secret=PROXY_SECRET,
            oidc_issuer_url="https://auth.example.com",
            oidc_client_id="web-client",
        )
        assert settings.validate_security() is None
        assert settings.get_auth_mode() == "forward-auth+oidc"

    def test_no_mode_warning_mentions_forward_auth(self):
        settings = Settings(debug=False, secret_key="a-strong-custom-secret")
        warning = settings.validate_security()
        assert warning is not None
        assert "FORWARD_AUTH_SECRET" in warning


class TestForwardAuthConfigAndStatus:
    @pytest.mark.asyncio
    async def test_config_reports_forward_auth_and_mobile_needs_oidc(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.get("/api/v1/auth/config")

        assert response.status_code == 200
        data = response.json()
        assert data["forward_auth"] is True
        assert data["dev_mode"] is False
        assert data["oidc"]["enabled"] is False
        assert "OIDC" in data["mobile_notice"]
        assert PROXY_SECRET not in response.text

    @pytest.mark.asyncio
    async def test_config_with_oidc_has_no_mobile_notice(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_and_oidc()):
            response = await client.get("/api/v1/auth/config")

        data = response.json()
        assert data["forward_auth"] is True
        assert data["oidc"]["enabled"] is True
        assert data["mobile_notice"] is None

    @pytest.mark.asyncio
    async def test_config_without_secret_reports_no_forward_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/config")

        data = response.json()
        assert data["forward_auth"] is False
        assert data["mobile_notice"] is None

    @pytest.mark.asyncio
    async def test_status_reports_forward_auth(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.get("/api/v1/auth/status")

        assert response.json() == {"configured": True, "mode": "forward-auth", "error": None}

    @pytest.mark.asyncio
    async def test_status_unconfigured_mentions_forward_auth(self, client: AsyncClient):
        with patch("app.api.auth.settings", _settings(debug=False, forward_auth_secret=None)):
            response = await client.get("/api/v1/auth/status")

        data = response.json()
        assert data["configured"] is False
        assert "FORWARD_AUTH_SECRET" in data["error"]


class TestRequestsAfterSignIn:
    @pytest.mark.asyncio
    async def test_every_session_of_the_account_holding_the_remote_user_is_accepted(
        self, client: AsyncClient, test_user: User, auth_headers: dict
    ):
        with (
            patch("app.api.auth.settings", _forward_auth_only()),
            patch("app.utils.auth.settings", _forward_auth_only()),
        ):
            proxy = await client.post(
                SYNC_URL, headers=_proxy_headers(user="tinyauth-bob", email=test_user.email)
            )
            proxy_bearer = {"Authorization": f"Bearer {proxy.json()['access_token']}"}
            responses = [
                await client.get(
                    "/api/v1/users/me", headers={**_proxy_headers(user="tinyauth-bob"), **bearer}
                )
                for bearer in (proxy_bearer, auth_headers)
            ]

        assert [response.status_code for response in responses] == [200, 200]
        assert {response.json()["email"] for response in responses} == {test_user.email}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("remote_user", "expected"),
        [
            pytest.param("tinyauth-alice", (200, 404), id="same-user-reaches-the-file-lookup"),
            pytest.param("tinyauth-other", (401, 401), id="switched-user-is-refused-everywhere"),
        ],
    )
    async def test_proxy_user_switch_is_refused_on_every_route(
        self, client: AsyncClient, remote_user: str, expected: tuple
    ):
        with (
            patch("app.api.auth.settings", _forward_auth_only()),
            patch("app.utils.auth.settings", _forward_auth_only()),
        ):
            signed_in = (await client.post(SYNC_URL, headers=_proxy_headers())).json()
            headers = {
                **_proxy_headers(user=remote_user),
                "Authorization": f"Bearer {signed_in['access_token']}",
            }
            me = await client.get("/api/v1/users/me", headers=headers)
            image = await client.get(
                f"/api/v1/images/{signed_in['id']}/missing.jpg", headers=headers
            )

        assert (me.status_code, image.status_code) == expected

    @pytest.mark.asyncio
    async def test_repeated_remote_user_is_refused_after_sign_in(self, client: AsyncClient):
        with (
            patch("app.api.auth.settings", _forward_auth_only()),
            patch("app.utils.auth.settings", _forward_auth_only()),
        ):
            signed_in = (await client.post(SYNC_URL, headers=_proxy_headers())).json()
            response = await client.get(
                "/api/v1/users/me",
                headers=[
                    ("Remote-User", "tinyauth-alice"),
                    *_proxy_headers(user="tinyauth-other").items(),
                    ("Authorization", f"Bearer {signed_in['access_token']}"),
                ],
            )

        assert response.status_code == 400
        assert "Remote-User" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_bearer_matching_non_ascii_remote_user_is_accepted(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        subject = f"{uuid4()}voilà"
        bearer = await _proxy_user_bearer(db_session, subject)

        with patch("app.utils.auth.settings", _forward_auth_only()):
            response = await client.get(
                "/api/v1/users/me",
                headers={**_proxy_headers(user=subject.encode()), **bearer},
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "remote_user",
        ["tinyauth-other", "legacy-subject"],
        ids=["other-user", "same-subject-of-another-provider"],
    )
    async def test_bearer_for_a_remote_user_the_account_does_not_hold_returns_401(
        self, client: AsyncClient, test_user: User, auth_headers: dict, remote_user: str
    ):
        if remote_user == "legacy-subject":
            remote_user = test_user.external_id
        with patch("app.utils.auth.settings", _forward_auth_only()):
            response = await client.get(
                "/api/v1/users/me",
                headers={**_proxy_headers(user=remote_user), **auth_headers},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("user", "other"), TRAILING_BYTE_PAIRS, ids=["trailing-nbsp", "trailing-nel"]
    )
    async def test_bearer_for_a_remote_user_differing_in_a_trailing_byte_returns_401(
        self, client: AsyncClient, db_session: AsyncSession, user: str, other: str
    ):
        prefix = str(uuid4())
        bearer = await _proxy_user_bearer(db_session, f"{prefix}{user}")

        with patch("app.utils.auth.settings", _forward_auth_only()):
            response = await client.get(
                "/api/v1/users/me",
                headers={**_proxy_headers(user=f"{prefix}{other}".encode()), **bearer},
            )

        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "headers",
        [
            {"Remote-User": "tinyauth-other"},
            {"Remote-User": "tinyauth-other", "X-Forward-Auth-Secret": "w" * 32},
            {"Remote-User": "tinyauth-other", "X-Forward-Auth-Secret": ""},
            {"X-Forward-Auth-Secret": PROXY_SECRET},
            {"Remote-User": "", "X-Forward-Auth-Secret": PROXY_SECRET},
        ],
        ids=["no-secret", "wrong-secret", "empty-secret", "no-remote-user", "empty-remote-user"],
    )
    async def test_untrusted_or_absent_remote_user_is_ignored(
        self, client: AsyncClient, test_user: User, auth_headers: dict, headers: dict
    ):
        with patch("app.utils.auth.settings", _forward_auth_only()):
            response = await client.get("/api/v1/users/me", headers={**headers, **auth_headers})

        assert response.status_code == 200
        assert response.json()["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_remote_user_is_ignored_when_forward_auth_is_not_configured(
        self, client: AsyncClient, test_user: User, auth_headers: dict
    ):
        with patch("app.utils.auth.settings", _settings(forward_auth_secret=None)):
            response = await client.get(
                "/api/v1/users/me",
                headers={**_proxy_headers(user="tinyauth-other"), **auth_headers},
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_proxy_headers_alone_do_not_authenticate(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_only()):
            await client.post(SYNC_URL, headers=_proxy_headers())
            response = await client.get("/api/v1/users/me", headers=_proxy_headers())

        assert response.status_code == 401
