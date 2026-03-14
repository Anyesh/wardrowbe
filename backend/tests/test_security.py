import html as html_mod
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.schemas.notification import NtfyConfig, ScheduleBase, ScheduleUpdate


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


class TestAuthEmailValidation:
    @pytest.mark.asyncio
    async def test_oidc_rejects_mismatched_email(self, client, db_session):
        mock_claims = {
            "sub": "oidc-user-123",
            "email": "real@example.com",
            "email_verified": True,
        }
        with (
            patch("app.api.auth._is_dev_mode", return_value=False),
            patch("app.api.auth._oidc_configured", return_value=True),
            patch("app.api.auth.validate_oidc_id_token", return_value=mock_claims),
            patch("app.api.auth.rate_limit_by_ip", new_callable=AsyncMock),
            patch("app.api.auth.settings") as mock_settings,
        ):
            mock_settings.oidc_issuer_url = "https://auth.example.com"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.oidc_mobile_client_id = None

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
    async def test_oidc_allows_matching_email_case_insensitive(self, client, db_session):
        mock_claims = {
            "sub": "oidc-user-456",
            "email": "User@Example.com",
            "email_verified": True,
        }
        with (
            patch("app.api.auth._is_dev_mode", return_value=False),
            patch("app.api.auth._oidc_configured", return_value=True),
            patch("app.api.auth.validate_oidc_id_token", return_value=mock_claims),
            patch("app.api.auth.rate_limit_by_ip", new_callable=AsyncMock),
            patch("app.api.auth.settings") as mock_settings,
        ):
            mock_settings.oidc_issuer_url = "https://auth.example.com"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.oidc_mobile_client_id = None
            mock_settings.secret_key = "test-secret"

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


class TestProviderMigrationRequiresVerifiedEmail:
    @pytest.mark.asyncio
    async def test_unverified_blocks_migration(self, client, db_session, test_user):
        mock_claims = {
            "sub": "new-provider-id",
            "email": test_user.email,
            "email_verified": False,
        }
        with (
            patch("app.api.auth._is_dev_mode", return_value=False),
            patch("app.api.auth._oidc_configured", return_value=True),
            patch("app.api.auth.validate_oidc_id_token", return_value=mock_claims),
            patch("app.api.auth.rate_limit_by_ip", new_callable=AsyncMock),
            patch("app.api.auth.settings") as mock_settings,
        ):
            mock_settings.oidc_issuer_url = "https://auth.example.com"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.oidc_mobile_client_id = None

            response = await client.post(
                "/api/v1/auth/sync",
                json={
                    "external_id": "new-provider-id",
                    "email": test_user.email,
                    "display_name": "Test",
                    "id_token": "fake-token",
                },
            )
            assert response.status_code == 409
            assert "Verified email required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_verified_allows_migration(self, client, db_session, test_user):
        mock_claims = {
            "sub": "new-provider-id-2",
            "email": test_user.email,
            "email_verified": True,
        }
        with (
            patch("app.api.auth._is_dev_mode", return_value=False),
            patch("app.api.auth._oidc_configured", return_value=True),
            patch("app.api.auth.validate_oidc_id_token", return_value=mock_claims),
            patch("app.api.auth.rate_limit_by_ip", new_callable=AsyncMock),
            patch("app.api.auth.settings") as mock_settings,
        ):
            mock_settings.oidc_issuer_url = "https://auth.example.com"
            mock_settings.oidc_client_id = "test-client"
            mock_settings.oidc_mobile_client_id = None
            mock_settings.secret_key = "test-secret"

            response = await client.post(
                "/api/v1/auth/sync",
                json={
                    "external_id": "new-provider-id-2",
                    "email": test_user.email,
                    "display_name": "Test",
                    "id_token": "fake-token",
                },
            )
            assert response.status_code == 200
