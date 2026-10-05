from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _is_dev_mode
from app.config import Settings, get_settings
from app.models import User
from app.utils.auth import decode_token

PROXY_SECRET = "s" * 32
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


async def _user_by_external_id(db: AsyncSession, external_id: str) -> User | None:
    result = await db.execute(select(User).where(User.external_id == external_id))
    return result.scalar_one_or_none()


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
        assert decode_token(data["access_token"]).sub == "tinyauth-alice"
        user = await _user_by_external_id(db_session, "tinyauth-alice")
        assert user is not None
        assert str(user.id) == data["id"]

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
        assert decode_token(data["access_token"]).sub == "tinyauth-alice"
        assert await _user_by_external_id(db_session, "body-attacker") is None

    @pytest.mark.asyncio
    async def test_display_name_falls_back_to_remote_user(self, client: AsyncClient):
        headers = _proxy_headers()
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
    async def test_existing_user_with_same_email_is_adopted(
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
        assert decode_token(data["access_token"]).sub == "tinyauth-bob"
        await db_session.refresh(test_user)
        assert test_user.external_id == "tinyauth-bob"


class TestForwardAuthRejections:
    @pytest.mark.asyncio
    async def test_wrong_secret_returns_401(self, client: AsyncClient, db_session: AsyncSession):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(secret="x" * 32))

        assert response.status_code == 401
        assert await _user_by_external_id(db_session, "tinyauth-alice") is None

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
        assert await _user_by_external_id(db_session, "tinyauth-alice") is None

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
        assert await _user_by_external_id(db_session, "dev-user") is None

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
        assert await _user_by_external_id(db_session, "tinyauth-alice") is None

    @pytest.mark.asyncio
    async def test_missing_remote_user_returns_400(self, client: AsyncClient):
        headers = _proxy_headers()
        del headers["Remote-User"]
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=headers)

        assert response.status_code == 400
        assert "Remote-User" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_overlong_remote_user_returns_400(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(user="u" * 256))

        assert response.status_code == 400
        assert "Remote-User" in response.json()["detail"]
        assert await _user_by_external_id(db_session, "u" * 256) is None

    @pytest.mark.asyncio
    async def test_remote_user_at_the_column_limit_is_accepted(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_only()):
            response = await client.post(SYNC_URL, headers=_proxy_headers(user="u" * 255))

        assert response.status_code == 200
        assert decode_token(response.json()["access_token"]).sub == "u" * 255

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
        self, client: AsyncClient, user: bytes, expected: str
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
        assert decode_token(response.json()["access_token"]).sub == f"{prefix}{expected}"

    @pytest.mark.asyncio
    async def test_remote_users_differing_in_a_trailing_byte_get_separate_accounts(
        self, client: AsyncClient
    ):
        prefix = str(uuid4())
        with patch("app.api.auth.settings", _forward_auth_only()):
            first = await client.post(
                SYNC_URL,
                headers=_proxy_headers(
                    user=f"{prefix}voilà".encode(), email=f"{prefix}-a@example.com"
                ),
            )
            second = await client.post(
                SYNC_URL,
                headers=_proxy_headers(
                    user=f"{prefix}voilÃ".encode(), email=f"{prefix}-b@example.com"
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
    async def test_failed_attempts_are_limited_without_blocking_valid_ones(
        self, client: AsyncClient
    ):
        bad = _proxy_headers(secret="x" * 32)
        with patch("app.api.auth.settings", _forward_auth_only()):
            statuses = [(await client.post(SYNC_URL, headers=bad)).status_code for _ in range(11)]
            valid = await client.post(SYNC_URL, headers=_proxy_headers())

        assert statuses == [401] * 10 + [429]
        assert valid.status_code == 200

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
        with patch(
            "app.api.auth.settings", _settings(debug=True, forward_auth_secret=PROXY_SECRET)
        ):
            assert _is_dev_mode() is False

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
        assert decode_token(with_header.json()["access_token"]).sub == "tinyauth-alice"
        assert without_header.status_code == 401
        assert await _user_by_external_id(db_session, "dev-typed") is None

    @pytest.mark.asyncio
    async def test_oidc_and_secret_uses_forward_auth_when_header_present(self, client: AsyncClient):
        validator = AsyncMock()
        with (
            patch("app.api.auth.settings", _forward_auth_and_oidc()),
            patch("app.api.auth.validate_oidc_id_token", validator),
        ):
            response = await client.post(SYNC_URL, headers=_proxy_headers())

        assert response.status_code == 200
        assert decode_token(response.json()["access_token"]).sub == "tinyauth-alice"
        validator.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_oidc_and_secret_uses_oidc_when_header_absent(self, client: AsyncClient):
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
        assert decode_token(response.json()["access_token"]).sub == "oidc-carol"
        validator.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_oidc_token_through_proxy_without_remote_user_uses_oidc(
        self, client: AsyncClient
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
        assert decode_token(response.json()["access_token"]).sub == "oidc-dave"
        validator.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remote_user_wins_over_body_id_token(self, client: AsyncClient):
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
        assert decode_token(response.json()["access_token"]).sub == "tinyauth-alice"
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
    def test_short_secret_fails_validation(self):
        settings = Settings(secret_key="a-strong-custom-secret", forward_auth_secret="s" * 31)
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
    async def test_bearer_user_wins_over_remote_user_headers(
        self, client: AsyncClient, test_user: User, auth_headers: dict
    ):
        with patch("app.api.auth.settings", _forward_auth_only()):
            other = await client.post(SYNC_URL, headers=_proxy_headers(user="tinyauth-other"))
            assert other.status_code == 200
            response = await client.get(
                "/api/v1/users/me",
                headers={**_proxy_headers(user="tinyauth-other"), **auth_headers},
            )

        assert response.status_code == 200
        assert response.json()["email"] == test_user.email

    @pytest.mark.asyncio
    async def test_proxy_headers_alone_do_not_authenticate(self, client: AsyncClient):
        with patch("app.api.auth.settings", _forward_auth_only()):
            await client.post(SYNC_URL, headers=_proxy_headers())
            response = await client.get("/api/v1/users/me", headers=_proxy_headers())

        assert response.status_code == 401
