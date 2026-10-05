import html as html_mod
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.auth import _is_dev_mode
from app.config import Settings
from app.models import Family, FamilyInvite, User
from app.schemas.notification import NtfyConfig, ScheduleBase, ScheduleUpdate
from app.services.user_service import UserService


class TestAIEndpointSchemeValidation:
    @pytest.mark.asyncio
    async def test_rejects_non_http_scheme(self, client, auth_headers):
        response = await client.post(
            "/api/v1/users/me/preferences/test-ai-endpoint",
            json={"url": "ftp://example.com/file"},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "HTTP" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_allows_localhost(self, client, auth_headers):
        response = await client.post(
            "/api/v1/users/me/preferences/test-ai-endpoint",
            json={"url": "http://127.0.0.1:11434/v1"},
            headers=auth_headers,
        )
        # Should not be rejected for being private — this is self-hosted OSS
        assert response.status_code != 400 or "HTTP" not in response.json().get("detail", "")


class TestOccasionValidation:
    def test_rejects_sql_injection(self):
        from app.api.outfits import SuggestRequest

        with pytest.raises(ValidationError):
            SuggestRequest(occasion="'; DROP TABLE outfits; --")

    def test_rejects_long_value(self):
        from app.api.outfits import SuggestRequest

        with pytest.raises(ValidationError):
            SuggestRequest(occasion="a" * 100)

    def test_accepts_valid(self):
        from app.api.outfits import SuggestRequest

        req = SuggestRequest(occasion="casual")
        assert req.occasion == "casual"

    def test_normalizes_case(self):
        from app.api.outfits import SuggestRequest

        req = SuggestRequest(occasion="FORMAL")
        assert req.occasion == "formal"

    def test_strips_whitespace(self):
        from app.api.outfits import SuggestRequest

        req = SuggestRequest(occasion="  office  ")
        assert req.occasion == "office"


class TestEmailHtmlEscaping:
    def test_strips_script_tags(self):
        malicious = '<script>alert("xss")</script>'
        escaped = html_mod.escape(malicious)
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    def test_preserves_normal_text(self):
        normal = "A casual outfit for sunny weather"
        assert html_mod.escape(normal) == normal


class TestBulkUploadLimit:
    @pytest.mark.asyncio
    async def test_rejects_over_20_images(self, client, auth_headers):
        files = [("images", (f"img{i}.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")) for i in range(21)]
        response = await client.post(
            "/api/v1/items/bulk",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Maximum 20" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_limit_is_configurable(self, client, auth_headers):
        from app.api import items as items_api

        original = items_api.settings.max_bulk_upload_count
        items_api.settings.max_bulk_upload_count = 5
        try:
            files = [
                ("images", (f"img{i}.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")) for i in range(6)
            ]
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                headers=auth_headers,
            )
            assert response.status_code == 400
            assert "Maximum 5" in response.json()["detail"]
        finally:
            items_api.settings.max_bulk_upload_count = original


class TestNtfyServerValidation:
    def test_rejects_non_http(self):
        with pytest.raises(ValidationError):
            NtfyConfig(server="ftp://ntfy.example.com", topic="test-topic")

    def test_rejects_long_url(self):
        with pytest.raises(ValidationError):
            NtfyConfig(server="https://" + "a" * 500, topic="test-topic")

    def test_accepts_valid(self):
        config = NtfyConfig(server="https://ntfy.sh", topic="test-topic")
        assert config.server == "https://ntfy.sh"

    def test_strips_trailing_slash(self):
        config = NtfyConfig(server="https://ntfy.sh/", topic="test-topic")
        assert config.server == "https://ntfy.sh"

    def test_accepts_http(self):
        config = NtfyConfig(server="http://ntfy.local:8080", topic="test-topic")
        assert config.server == "http://ntfy.local:8080"


class TestScheduleOccasionValidation:
    def test_rejects_invalid(self):
        with pytest.raises(ValidationError):
            ScheduleBase(day_of_week=0, notification_time="08:00", occasion="invalid-occasion")

    def test_accepts_valid(self):
        schedule = ScheduleBase(day_of_week=0, notification_time="08:00", occasion="casual")
        assert schedule.occasion == "casual"

    def test_update_rejects_invalid(self):
        with pytest.raises(ValidationError):
            ScheduleUpdate(occasion="invalid-occasion")

    def test_update_accepts_valid(self):
        update = ScheduleUpdate(occasion="formal")
        assert update.occasion == "formal"


class TestMattermostWebhookValidation:
    def test_rejects_non_https(self):
        from app.schemas.notification import MattermostConfig

        with pytest.raises(ValidationError):
            MattermostConfig(webhook_url="http://mattermost.example.com/hooks/abc")

    def test_rejects_missing_hooks(self):
        from app.schemas.notification import MattermostConfig

        with pytest.raises(ValidationError):
            MattermostConfig(webhook_url="https://mattermost.example.com/api/abc")

    def test_accepts_valid(self):
        from app.schemas.notification import MattermostConfig

        config = MattermostConfig(webhook_url="https://mattermost.example.com/hooks/abc123")
        assert "hooks" in config.webhook_url


class TestHealthEndpointInfoLeak:
    @pytest.mark.asyncio
    async def test_ai_health_strips_sensitive_info(self, client):
        mock_health = {
            "status": "healthy",
            "endpoints": [
                {
                    "name": "ollama",
                    "url": "http://10.0.0.5:11434/v1",
                    "status": "healthy",
                    "vision_model": "llava:13b",
                    "text_model": "mistral:7b",
                    "available_models": ["llava:13b", "mistral:7b"],
                }
            ],
        }
        with patch("app.api.health.get_ai_service") as mock_svc:
            mock_instance = AsyncMock()
            mock_instance.check_health.return_value = mock_health
            mock_svc.return_value = mock_instance

            response = await client.get("/api/v1/health/ai")
            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "healthy"
            ep = data["endpoints"][0]
            assert ep["name"] == "ollama"
            assert ep["status"] == "healthy"
            assert "url" not in ep
            assert "vision_model" not in ep
            assert "text_model" not in ep
            assert "available_models" not in ep


@pytest.fixture
def oidc_claims():
    with (
        patch("app.api.auth._is_dev_mode", return_value=False),
        patch("app.api.auth._oidc_configured", return_value=True),
        patch("app.api.auth.validate_oidc_id_token") as validate,
        patch("app.api.auth.rate_limit_by_ip", new_callable=AsyncMock),
        patch("app.api.auth.settings") as mock_settings,
    ):
        mock_settings.oidc_issuer_url = "https://auth.example.com"
        mock_settings.oidc_client_id = "test-client"
        mock_settings.oidc_mobile_client_id = None
        mock_settings.secret_key = "test-secret"
        yield validate


class TestAuthEmailValidation:
    @pytest.mark.asyncio
    async def test_oidc_rejects_mismatched_email(self, client, db_session, oidc_claims):
        oidc_claims.return_value = {
            "sub": "oidc-user-123",
            "email": "real@example.com",
            "email_verified": True,
        }
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "oidc-user-123",
                "email": "spoofed@example.com",
                "display_name": "Test",
                "id_token": "fake-token",
            },
        )
        assert response.status_code == 401
        assert "email does not match" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_oidc_allows_matching_email_case_insensitive(
        self, client, db_session, oidc_claims
    ):
        oidc_claims.return_value = {
            "sub": "oidc-user-456",
            "email": "User@Example.com",
            "email_verified": True,
        }
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "oidc-user-456",
                "email": "user@example.com",
                "display_name": "Test User",
                "id_token": "fake-token",
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("claims", "expected_verified"),
        [
            pytest.param({"email_verified": True}, True, id="oidc-verified"),
            pytest.param({"email_verified": False}, False, id="oidc-unverified"),
            pytest.param(None, True, id="dev"),
        ],
    )
    async def test_new_user_records_whether_email_was_verified(
        self, client, db_session, oidc_claims, claims, expected_verified
    ):
        external_id = f"new-{uuid4()}"
        email = f"{external_id}@example.com"
        oidc_claims.return_value = {"sub": external_id, "email": email, **(claims or {})}
        with patch("app.api.auth._is_dev_mode", return_value=claims is None):
            response = await client.post(
                "/api/v1/auth/sync",
                json={
                    "external_id": external_id,
                    "email": email,
                    "display_name": "New",
                    "id_token": "fake-token",
                },
            )

        assert response.status_code == 200
        assert response.json()["is_new_user"] is True
        user = await UserService(db_session).get_by_external_id(external_id)
        assert user.email_verified is expected_verified

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("dev_mode", "email_template"),
        [
            pytest.param(True, "{}@detached.invalid", id="dev-exact"),
            pytest.param(True, "{}@DETACHED.Invalid", id="dev-uppercase"),
            pytest.param(True, "  {}@detached.invalid ", id="dev-padded"),
            pytest.param(False, "{}@Detached.INVALID", id="oidc-uppercase"),
        ],
    )
    async def test_sync_refuses_a_detached_placeholder_address(
        self, client, db_session, oidc_claims, dev_mode, email_template
    ):
        external_id = f"claim-{uuid4()}"
        email = email_template.format(uuid4())
        oidc_claims.return_value = {"sub": external_id, "email": email, "email_verified": True}
        with patch("app.api.auth._is_dev_mode", return_value=dev_mode):
            response = await client.post(
                "/api/v1/auth/sync",
                json={
                    "external_id": external_id,
                    "email": email,
                    "display_name": "Claim",
                    "id_token": "fake-token",
                },
            )

        assert (response.status_code, response.json()["detail"]) == (
            409,
            "Email already in use by another account.",
        )
        assert await UserService(db_session).get_by_external_id(external_id) is None


class TestProviderMigrationRequiresVerifiedEmail:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("email_claim", "email_verified", "expected_status"),
        [
            pytest.param(True, False, 409, id="unverified-claim"),
            pytest.param(False, True, 409, id="no-email-claim"),
            pytest.param(True, True, 200, id="verified"),
        ],
    )
    async def test_migration_requires_verified_email_claim(
        self,
        client,
        db_session,
        test_user,
        oidc_claims,
        email_claim,
        email_verified,
        expected_status,
    ):
        original_external_id = test_user.external_id
        oidc_claims.return_value = {"sub": "new-provider-id", "email_verified": email_verified}
        if email_claim:
            oidc_claims.return_value["email"] = test_user.email
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "new-provider-id",
                "email": test_user.email,
                "display_name": "Test",
                "id_token": "fake-token",
            },
        )

        assert response.status_code == expected_status
        await db_session.refresh(test_user)
        if expected_status == 409:
            assert "provider that verifies" in response.json()["detail"]
            assert test_user.external_id == original_external_id
        else:
            assert test_user.external_id == "new-provider-id"


class TestInviteRequiresVerifiedEmail:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("invited_email", "email_verified", "expected_status", "expected_error"),
        [
            pytest.param(None, True, 200, None, id="verified"),
            pytest.param(None, False, 403, "EMAIL_NOT_VERIFIED", id="unverified"),
            pytest.param("someone-else@example.com", True, 403, None, id="different-email"),
        ],
    )
    async def test_join_by_token(
        self,
        client,
        db_session,
        test_user,
        auth_headers,
        invited_email,
        email_verified,
        expected_status,
        expected_error,
    ):
        run = uuid4()
        inviter = User(
            external_id=f"inviter-{run}", email=f"inviter-{run}@example.com", display_name="Inviter"
        )
        db_session.add(inviter)
        await db_session.flush()
        family = Family(name="Family", created_by=inviter.id, invite_code=run.hex[:12])
        db_session.add(family)
        await db_session.flush()
        db_session.add(
            FamilyInvite(
                family_id=family.id,
                email=invited_email or test_user.email,
                token=f"token-{run}",
                invited_by=inviter.id,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        test_user.email_verified = email_verified
        await db_session.flush()

        response = await client.post(
            "/api/v1/families/join-by-token", json={"token": f"token-{run}"}, headers=auth_headers
        )

        assert response.status_code == expected_status
        if expected_error is not None:
            assert response.json()["detail"]["error_code"] == expected_error
        await db_session.refresh(test_user)
        assert (test_user.family_id == family.id) is (expected_status == 200)


class TestDevModeAuthDecoupledFromSecretKey:
    def test_get_auth_mode_dev_with_custom_secret_key(self):
        settings = Settings(debug=True, secret_key="a-strong-custom-secret")
        assert settings.get_auth_mode() == "dev"
        assert settings.validate_security() is None

    def test_get_auth_mode_oidc_takes_precedence_over_debug(self):
        settings = Settings(
            debug=True,
            secret_key="a-strong-custom-secret",
            oidc_issuer_url="https://auth.example.com",
            oidc_client_id="test-client",
        )
        assert settings.get_auth_mode() == "oidc"
        assert settings.validate_security() is None

    def test_is_dev_mode_true_with_custom_secret_and_no_oidc(self):
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.debug = True
            mock_settings.oidc_issuer_url = None
            mock_settings.oidc_client_id = None

            assert _is_dev_mode() is True

    def test_is_dev_mode_false_when_oidc_configured_even_with_debug(self):
        with patch("app.api.auth.settings") as mock_settings:
            mock_settings.debug = True
            mock_settings.oidc_issuer_url = "https://auth.example.com"
            mock_settings.oidc_client_id = "test-client"

            assert _is_dev_mode() is False
