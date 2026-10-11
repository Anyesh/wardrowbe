from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import PropertyMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import delete, inspect, update

from app.api.auth import SYNC_RATE_LIMIT, create_access_token
from app.config import Settings, get_settings
from app.models import User, UserIdentity
from app.schemas.auth import IDENTITY_TOKEN
from app.services.user_service import UserService
from app.utils.auth import decode_token, get_current_session
from tests.identity_helpers import (
    add_users_with_identities,
    legacy_token,
    user_of_subject,
)

USER_ID, IDENTITY_ID = uuid4(), uuid4()
SYNC_LIMIT = SYNC_RATE_LIMIT[1]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(**claims) -> str:
    now = datetime.utcnow()
    return jwt.encode(
        {"exp": now + timedelta(days=1), "iat": now, **claims},
        get_settings().secret_key,
        algorithm="HS256",
    )


class TestJWTToken:
    @pytest.mark.parametrize(
        ("mint", "expected"),
        [
            pytest.param(
                lambda: create_access_token(USER_ID, IDENTITY_ID),
                (str(USER_ID), str(IDENTITY_ID), IDENTITY_TOKEN),
                id="identity",
            ),
            pytest.param(
                lambda: legacy_token("legacy-sub"), ("legacy-sub", None, None), id="legacy"
            ),
        ],
    )
    def test_decode_valid_token(self, mint, expected):
        payload = decode_token(mint())
        assert (payload.sub, payload.iid, payload.sub_type) == expected

    def test_decode_expired_token(self):
        token = create_access_token(USER_ID, IDENTITY_ID, expires_delta=timedelta(hours=-1))

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401


class TestAuthConfig:
    @pytest.mark.asyncio
    async def test_get_auth_config(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/config")
        assert response.status_code == 200
        data = response.json()
        assert "oidc" in data
        assert "dev_mode" in data
        assert isinstance(data["oidc"]["enabled"], bool)

    @pytest.mark.asyncio
    async def test_auth_config_dev_mode(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/config")
        data = response.json()
        assert data["dev_mode"] is True
        assert data["oidc"]["enabled"] is False


@contextmanager
def _sign_in_mode(mode: str):
    with (
        patch.object(Settings, "dev_mode", new_callable=PropertyMock, return_value=mode == "dev"),
        patch.object(
            Settings, "oidc_configured", new_callable=PropertyMock, return_value=mode == "oidc"
        ),
        patch("app.api.auth.validate_oidc_id_token") as validate,
    ):
        yield validate


class TestAuthSync:
    """Tests for auth sync endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["dev", "oidc"])
    async def test_successful_syncs_do_not_consume_the_rate_limit(
        self, client: AsyncClient, mode: str
    ):
        body = {"external_id": "steady", "email": "steady@example.com", "display_name": "S"}
        with _sign_in_mode(mode) as validate:
            validate.return_value = {"sub": "steady", "email": "steady@example.com"}
            statuses = [
                (await client.post("/api/v1/auth/sync", json={**body, "id_token": "t"})).status_code
                for _ in range(SYNC_LIMIT + 1)
            ]

        assert statuses == [200] * (SYNC_LIMIT + 1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("id_token", "claims"),
        [
            pytest.param(None, None, id="missing-id-token"),
            pytest.param("t", ValueError("Invalid token"), id="invalid-id-token"),
            pytest.param("t", {"sub": "someone-else"}, id="subject-mismatch"),
            pytest.param("t", {"sub": "forger", "email": "real@example.com"}, id="email-mismatch"),
        ],
    )
    async def test_forged_oidc_syncs_are_limited_without_blocking_valid_ones(
        self, client: AsyncClient, id_token: str | None, claims: dict | Exception | None
    ):
        forged = {
            "external_id": "forger",
            "email": "forged@example.com",
            "display_name": "F",
            "id_token": id_token,
        }
        with _sign_in_mode("oidc") as validate:
            if isinstance(claims, Exception):
                validate.side_effect = claims
            else:
                validate.return_value = claims
            statuses = [
                (await client.post("/api/v1/auth/sync", json=forged)).status_code
                for _ in range(SYNC_LIMIT + 1)
            ]
            validate.side_effect = None
            validate.return_value = {"sub": "honest", "email": "honest@example.com"}
            valid = await client.post(
                "/api/v1/auth/sync",
                json={
                    "external_id": "honest",
                    "email": "honest@example.com",
                    "display_name": "H",
                    "id_token": "t",
                },
            )

        assert statuses == [401] * SYNC_LIMIT + [429]
        assert valid.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("mode", "email_of", "expected"),
        [
            pytest.param("dev", lambda user: None, 400, id="dev-missing-email"),
            pytest.param("oidc", lambda user: None, 400, id="oidc-missing-email"),
            pytest.param("oidc", lambda user: user.email, 409, id="oidc-unverified-email-in-use"),
        ],
    )
    async def test_user_state_errors_do_not_consume_the_rate_limit(
        self, client: AsyncClient, test_user, mode: str, email_of, expected: int
    ):
        email = email_of(test_user)
        with _sign_in_mode(mode) as validate:
            validate.return_value = {"sub": "newcomer", "email": email, "email_verified": False}
            statuses = [
                (
                    await client.post(
                        "/api/v1/auth/sync",
                        json={
                            "external_id": "newcomer",
                            "email": email,
                            "display_name": "N",
                            "id_token": "t",
                        },
                    )
                ).status_code
                for _ in range(SYNC_LIMIT + 1)
            ]

        assert statuses == [expected] * (SYNC_LIMIT + 1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("avatar_url", "stored_avatar"),
        [
            pytest.param(
                "https://idp.example.com/a.png", "https://idp.example.com/a.png", id="kept"
            ),
            pytest.param("https://idp.example.com/" + "a" * 600, None, id="over-column-dropped"),
        ],
    )
    async def test_sync_new_user(self, client: AsyncClient, db_session, avatar_url, stored_avatar):
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "new-user-123",
                "email": "newuser@example.com",
                "display_name": "New User",
                "avatar_url": avatar_url,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["display_name"] == "New User"
        assert "access_token" in data
        assert data["is_new_user"] is True
        user = await user_of_subject(db_session, "new-user-123")
        assert user.avatar_url == stored_avatar

    @pytest.mark.asyncio
    async def test_sync_existing_user(self, client: AsyncClient, test_user):
        """Test syncing an existing user returns existing data."""
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": test_user.external_id,
                "email": test_user.email,
                "display_name": "Updated Name",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["is_new_user"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"external_id": "test-123"}, id="no-display-name"),
            pytest.param(
                {"external_id": "s" * 256, "email": "a@example.com", "display_name": "A"},
                id="subject-over-column",
            ),
        ],
    )
    async def test_sync_refuses_a_malformed_body(self, client: AsyncClient, body):
        response = await client.post("/api/v1/auth/sync", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_sync_null_email_dev_mode_returns_400(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "test-123",
                "email": None,
                "display_name": "Test User",
            },
        )
        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_sync_omitted_email_dev_mode_returns_400(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "test-123",
                "display_name": "Test User",
            },
        )
        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "email", ["admin@nas.local", "alice@fae2e.test", "me@pi.localhost", "bob@home.arpa"]
    )
    async def test_sync_then_session_accepts_special_use_domains(
        self, client: AsyncClient, email: str
    ):
        synced = await client.post(
            "/api/v1/auth/sync",
            json={"external_id": f"nas-{email}", "email": email, "display_name": "NAS User"},
        )
        assert synced.status_code == 200
        token = synced.json()["access_token"]

        session = await client.get(
            "/api/v1/auth/session", headers={"Authorization": f"Bearer {token}"}
        )
        assert session.status_code == 200
        assert session.json()["email"] == email

    @pytest.mark.asyncio
    async def test_sync_normalises_email_case_and_whitespace(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/sync",
            json={"external_id": "nas-upper", "email": "  Admin@NAS.Local ", "display_name": "A"},
        )
        assert response.status_code == 200
        assert response.json()["email"] == "admin@nas.local"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("email", ["not-an-email", "x@nowhere.invalid", "x@hidden.onion"])
    async def test_sync_rejects_malformed_or_non_lan_reserved_email(
        self, client: AsyncClient, email: str
    ):
        response = await client.post(
            "/api/v1/auth/sync",
            json={"external_id": f"garbage-{email}", "email": email, "display_name": "G"},
        )
        assert response.status_code == 422


class TestMobileCallback:
    @pytest.mark.asyncio
    async def test_mobile_callback_redirects_with_params(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/mobile-callback",
            params={"code": "test-auth-code", "state": "test-state"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("wardrowbe://auth/callback?")
        assert "code=test-auth-code" in location
        assert "state=test-state" in location

    @pytest.mark.asyncio
    async def test_mobile_callback_redirects_without_params(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/mobile-callback",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "wardrowbe://auth/callback"

    @pytest.mark.asyncio
    async def test_mobile_callback_preserves_error_params(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/mobile-callback",
            params={"error": "access_denied", "error_description": "User cancelled"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=access_denied" in location
        assert "error_description=User+cancelled" in location

    @pytest.mark.asyncio
    async def test_mobile_callback_only_redirects_to_app_scheme(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/mobile-callback",
            params={"code": "x", "redirect": "https://evil.com"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("wardrowbe://")
        assert not location.startswith("https://evil.com")


class TestProtectedRoutes:
    """Tests for authentication requirement on protected routes."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_fails(self, client: AsyncClient):
        """Test that unauthenticated requests to protected routes fail."""
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_fails(self, client: AsyncClient):
        """Test that invalid token is rejected."""
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["identity", "legacy"])
    async def test_valid_token_succeeds(self, client: AsyncClient, test_user, auth_headers, kind):
        if kind != "identity":
            auth_headers = _bearer(legacy_token(test_user.external_id))
        response = await client.get("/api/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("is_active", "expected"),
        [
            pytest.param(True, (200, 404), id="active-reaches-the-file-lookup"),
            pytest.param(False, (403, 401), id="inactive-is-refused-everywhere"),
        ],
    )
    async def test_deactivated_account_token_is_refused_on_every_route(
        self, client: AsyncClient, db_session, test_user, auth_headers, is_active, expected
    ):
        test_user.is_active = is_active
        await db_session.commit()

        me = await client.get("/api/v1/users/me", headers=auth_headers)
        image = await client.get(f"/api/v1/images/{test_user.id}/missing.jpg", headers=auth_headers)

        assert (me.status_code, image.status_code) == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "mint",
        [
            pytest.param(
                lambda user, own, other: legacy_token(f"nobody-{uuid4()}"), id="unknown-legacy-sub"
            ),
            pytest.param(
                lambda user, own, other: _token(
                    sub=str(user.id), iid=str(own.id), sub_type="session"
                ),
                id="unknown-sub-type",
            ),
            pytest.param(
                lambda user, own, other: _token(
                    sub=other.subject, iid=str(other.id), sub_type=IDENTITY_TOKEN
                ),
                id="identity-sub-is-an-external-id",
            ),
            pytest.param(
                lambda user, own, other: _token(
                    sub=str(user.id), iid=str(other.id), sub_type=IDENTITY_TOKEN
                ),
                id="identity-of-another-user",
            ),
            pytest.param(
                lambda user, own, other: _token(
                    sub=str(user.id), iid="not-a-uuid", sub_type=IDENTITY_TOKEN
                ),
                id="unparsable-iid",
            ),
            pytest.param(
                lambda user, own, other: _token(sub=str(user.id), sub_type=IDENTITY_TOKEN),
                id="missing-iid",
            ),
        ],
    )
    async def test_token_not_bound_to_the_user_is_refused(
        self, client: AsyncClient, db_session, test_user, test_user_identity, mint
    ):
        other = User(
            external_id=f"other-{uuid4()}", email=f"other-{uuid4()}@example.com", display_name="O"
        )
        (other_identity,) = await add_users_with_identities(db_session, other)
        await db_session.commit()

        response = await client.get(
            "/api/v1/users/me", headers=_bearer(mint(test_user, test_user_identity, other_identity))
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_replaced_identity_token_is_refused(
        self, client: AsyncClient, db_session, test_user, auth_headers
    ):
        await db_session.execute(
            update(UserIdentity).where(UserIdentity.user_id == test_user.id).values(provider="dev")
        )
        await db_session.commit()

        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": f"replacement-{uuid4()}",
                "email": test_user.email,
                "display_name": "Replacement",
            },
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(test_user.id)
        old = await client.get("/api/v1/users/me", headers=auth_headers)
        new = await client.get("/api/v1/users/me", headers=_bearer(response.json()["access_token"]))
        assert (old.status_code, new.status_code) == (401, 200)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("then", ["sign-in-elsewhere", "re-adopt-by-email"])
    async def test_revoked_identity_stays_revoked(
        self, client: AsyncClient, db_session, test_user, then
    ):
        subject = test_user.external_id
        token = legacy_token(subject)
        await db_session.execute(
            delete(UserIdentity).where(
                UserIdentity.user_id == test_user.id, UserIdentity.subject == subject
            )
        )
        await db_session.execute(
            update(User)
            .where(User.id == test_user.id, User.external_id == subject)
            .values(external_id=None)
        )
        await db_session.commit()
        email = (
            f"elsewhere-{uuid4()}@example.com" if then == "sign-in-elsewhere" else test_user.email
        )

        response = await client.post(
            "/api/v1/auth/sync",
            json={"external_id": subject, "email": email, "display_name": "Back"},
        )

        assert response.status_code == 200
        signed_into_revoked = response.json()["id"] == str(test_user.id)
        assert signed_into_revoked is (then == "re-adopt-by-email")
        assert (await client.get("/api/v1/users/me", headers=_bearer(token))).status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["identity", "legacy"])
    async def test_token_user_has_preferences_loaded(
        self, db_session, test_user_with_preferences, test_user_identity, kind
    ):
        user = test_user_with_preferences
        token = (
            create_access_token(user.id, test_user_identity.id)
            if kind == "identity"
            else legacy_token(user.external_id)
        )
        db_session.expunge_all()

        found = await UserService(db_session).get_by_token(decode_token(token))

        assert found.id == user.id
        assert "preferences" not in inspect(found).unloaded
        assert found.preferences.color_favorites == ["black", "navy", "white"]


@pytest.mark.asyncio
async def test_session_of_a_user_without_a_pre_upgrade_sign_in(db_session, test_user):
    test_user.external_id = None
    await db_session.commit()

    session = await get_current_session(test_user)

    assert (session.user_id, session.external_id) == (test_user.id, None)
