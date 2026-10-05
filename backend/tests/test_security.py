import html as html_mod
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.auth import _is_dev_mode
from app.api.outfits import StudioCreateRequest, SuggestionCreateRequest, SuggestRequest
from app.api.users import UserProfileUpdate
from app.config import DEFAULT_SECRET_KEY, Settings
from app.models import Family, FamilyInvite, User
from app.schemas.family import FamilyCreate, FamilyUpdate
from app.schemas.item import LogWearRequest
from app.schemas.notification import NtfyConfig, ScheduleBase, ScheduleUpdate
from app.schemas.preference import PreferenceUpdate
from app.schemas.user import UserSyncRequest
from app.services.user_service import UserService
from app.utils.garment_vocabulary import OCCASIONS

ITEM_ID = "00000000-0000-0000-0000-000000000001"
OCCASION_REQUESTS = {
    "suggest": lambda occasion: SuggestRequest(occasion=occasion),
    "authoring": lambda occasion: SuggestionCreateRequest(items=[ITEM_ID], occasion=occasion),
    "studio": lambda occasion: StudioCreateRequest(items=[ITEM_ID], occasion=occasion),
    "schedule": lambda occasion: ScheduleBase(
        day_of_week=0, notification_time="08:00", occasion=occasion
    ),
    "schedule-update": lambda occasion: ScheduleUpdate(occasion=occasion),
    "wear-log": lambda occasion: LogWearRequest(occasion=occasion),
    "default-occasion": lambda occasion: SimpleNamespace(
        occasion=PreferenceUpdate(default_occasion=occasion).default_occasion
    ),
}


# Every user-written name that reaches an email Subject header or a chat message.
NAME_REQUESTS = {
    "family-create": lambda name: FamilyCreate(name=name).name,
    "family-update": lambda name: FamilyUpdate(name=name).name,
    "profile-update": lambda name: UserProfileUpdate(display_name=name).display_name,
    "sign-in-sync": lambda name, email="jane@example.com": (
        UserSyncRequest(external_id="sub", email=email, display_name=name).display_name
    ),
}


class TestNamesAreSingleLine:
    # Sign-in flattens instead of refusing because the IdP owns that name and a refusal would lock
    # the user out on every login.
    @pytest.mark.parametrize("request_id", NAME_REQUESTS.keys())
    @pytest.mark.parametrize(
        ("name", "email", "synced"),
        [
            (
                "Smith\r\nBcc: victim@example.com",
                "jane@example.com",
                "Smith Bcc: victim@example.com",
            ),
            ("Smith\nFamily", "jane@example.com", "Smith Family"),
            ("Tab\tName", "jane@example.com", "Tab Name"),
            ("Nul\x00", "jane@example.com", "Nul"),
            ("Line\u2028Sep", "jane@example.com", "Line Sep"),
            ("Jane Doe\r\n", "jane@example.com", "Jane Doe"),
            ("\r\n\t\u2029", "jane.doe@example.com", "jane.doe"),
            ("x" * 150, "jane@example.com", "x" * 100),
            ("A" * 99 + "\tB", "jane@example.com", "A" * 99),
            ("   ", "jane.doe@example.com", "jane.doe"),
            ("\u200b", "jane.doe@example.com", "jane.doe"),
            (" \u2060\ufeff\u3000\u200b ", "jane.doe@example.com", "jane.doe"),
            ("\u200c", "jane.doe@example.com", "jane.doe"),
            ("\u200d", "jane.doe@example.com", "jane.doe"),
            ("\u200e", "jane.doe@example.com", "jane.doe"),
            ("\u00ad", "jane.doe@example.com", "jane.doe"),
            ("\u180e", "jane.doe@example.com", "jane.doe"),
            ("\u2061", "jane.doe@example.com", "jane.doe"),
            ("\u202e", "jane.doe@example.com", "jane.doe"),
            ("\u3164", "jane.doe@example.com", "jane.doe"),
            ("\u115f", "jane.doe@example.com", "jane.doe"),
            ("\u1160", "jane.doe@example.com", "jane.doe"),
            ("\uffa0", "jane.doe@example.com", "jane.doe"),
            ("\u2800", "jane.doe@example.com", "jane.doe"),
            ("\u034f", "jane.doe@example.com", "jane.doe"),
            ("\ufe0f", "jane.doe@example.com", "jane.doe"),
            ("\U000e0100", "jane.doe@example.com", "jane.doe"),
            ("\u17b4", "jane.doe@example.com", "jane.doe"),
            ("\u2065", "jane.doe@example.com", "jane.doe"),
            ("\ufff0", "jane.doe@example.com", "jane.doe"),
            ("\ufff9\ufffb", "jane.doe@example.com", "jane.doe"),
            ("\U00013430", "jane.doe@example.com", "jane.doe"),
            ("\u0301\u0308", "jane.doe@example.com", "jane.doe"),
            ("\u200c\u200d\u00ad\u3164", "jane.doe@example.com", "jane.doe"),
            pytest.param(
                "\u200b" * 100 + "Bob",
                "jane.doe@example.com",
                "jane.doe",
                id="cut-leaves-only-zero-width",
            ),
        ],
    )
    def test_every_request_refuses_a_broken_or_blank_name_but_sign_in_repairs_it(
        self, request_id, name, email, synced
    ):
        if request_id == "sign-in-sync":
            assert NAME_REQUESTS[request_id](name, email) == synced
        else:
            with pytest.raises(ValidationError):
                NAME_REQUESTS[request_id](name)

    @pytest.mark.parametrize("build", NAME_REQUESTS.values(), ids=NAME_REQUESTS.keys())
    @pytest.mark.parametrize(
        "name",
        [
            "Smith & Co ☃ Müller",
            "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645",
            "\U0001f468\u200d\U0001f469\u200d\U0001f467",
            "\U0001f98a",
            "\u2603\ufe0f",
            "\u06dd",
            "\u0600\u0661\u0662\u0663",
            "Rene\u0301",
            "\u0928\u092e\u0938\u094d\u0924\u0947",
        ],
    )
    def test_every_request_accepts_a_plain_name(self, build, name):
        assert build(name) == name

    @pytest.mark.asyncio
    async def test_family_with_a_header_breaking_name_is_never_created(self, client, auth_headers):
        response = await client.post(
            "/api/v1/families",
            json={"name": "Smith\r\nBcc: victim@example.com"},
            headers=auth_headers,
        )

        assert response.status_code == 422
        assert (await client.get("/api/v1/families/me", headers=auth_headers)).status_code == 404


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


class TestSharedOccasionVocabulary:
    @pytest.mark.parametrize("build", OCCASION_REQUESTS.values(), ids=OCCASION_REQUESTS.keys())
    @pytest.mark.parametrize("occasion", OCCASIONS)
    def test_every_request_accepts_every_occasion(self, build, occasion):
        assert build(occasion).occasion == occasion

    @pytest.mark.parametrize("build", OCCASION_REQUESTS.values(), ids=OCCASION_REQUESTS.keys())
    @pytest.mark.parametrize("occasion", ["space-walk", "pairing", ""])
    def test_every_request_rejects_unknown_occasions(self, build, occasion):
        with pytest.raises(ValidationError):
            build(occasion)

    @pytest.mark.parametrize("build", OCCASION_REQUESTS.values(), ids=OCCASION_REQUESTS.keys())
    def test_every_request_normalizes_case_and_whitespace(self, build):
        assert build("  Wedding ").occasion == "wedding"


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
        patch("app.api.auth.validate_oidc_id_token") as validate,
        patch("app.api.auth.rate_limit_by_ip", new_callable=AsyncMock),
        patch("app.api.auth.settings") as mock_settings,
    ):
        mock_settings.oidc_issuer_url = "https://auth.example.com"
        mock_settings.oidc_client_id = "test-client"
        mock_settings.oidc_configured = True
        mock_settings.oidc_mobile_client_id = None
        mock_settings.secret_key = "test-secret"
        yield validate


class TestAuthEmailValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("claim_email", "request_email", "display_name", "stored", "stored_name"),
        [
            pytest.param(
                "User@Example.com",
                "user@example.com",
                "Claim",
                "user@example.com",
                "Claim",
                id="case",
            ),
            pytest.param(
                "user@xn--mnchen-3ya.de",
                "user@münchen.de",
                "Claim",
                "user@münchen.de",
                "Claim",
                id="punycode-claim",
            ),
            pytest.param(
                "user@xn--mnchen-3ya.de", None, "Claim", "user@münchen.de", "Claim", id="claim-only"
            ),
            pytest.param(
                "jane.doe@example.com",
                None,
                "\r\n",
                "jane.doe@example.com",
                "jane.doe",
                id="claim-only-blank-name",
            ),
        ],
    )
    async def test_oidc_claim_matching_the_request_is_stored_normalised(
        self,
        client,
        db_session,
        oidc_claims,
        claim_email,
        request_email,
        display_name,
        stored,
        stored_name,
    ):
        external_id = f"claim-{uuid4()}"
        oidc_claims.return_value = {
            "sub": external_id,
            "email": claim_email,
            "email_verified": True,
        }
        body = {"external_id": external_id, "display_name": display_name, "id_token": "t"}
        if request_email is not None:
            body["email"] = request_email

        response = await client.post("/api/v1/auth/sync", json=body)

        assert response.status_code == 200
        assert response.json()["email"] == stored
        user = await UserService(db_session).get_by_external_id(external_id)
        assert (user.email, user.email_verified, user.display_name) == (stored, True, stored_name)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("claim_email", "request_email", "expected_status", "expected_detail"),
        [
            pytest.param(
                "real@example.com",
                "spoofed@example.com",
                401,
                "email does not match",
                id="mismatched",
            ),
            pytest.param("not-an-email", None, 400, "not a valid email address", id="malformed"),
            pytest.param("a@b@example.com", None, 400, "not a valid email address", id="two-ats"),
            pytest.param(["x@example.com"], None, 400, "not a valid email address", id="non-str"),
            pytest.param(
                "not-an-email",
                "user@example.com",
                400,
                "not a valid email address",
                id="malformed-with-request-email",
            ),
            pytest.param(None, None, 400, "email claim", id="missing"),
        ],
    )
    async def test_bad_missing_or_mismatched_oidc_claim_is_refused(
        self,
        client,
        db_session,
        oidc_claims,
        claim_email,
        request_email,
        expected_status,
        expected_detail,
    ):
        external_id = f"claim-{uuid4()}"
        oidc_claims.return_value = {"sub": external_id, "email_verified": True}
        if claim_email is not None:
            oidc_claims.return_value["email"] = claim_email
        body = {"external_id": external_id, "display_name": "Claim", "id_token": "t"}
        if request_email is not None:
            body["email"] = request_email

        response = await client.post("/api/v1/auth/sync", json=body)

        assert response.status_code == expected_status
        assert expected_detail in response.json()["detail"]
        assert await UserService(db_session).get_by_external_id(external_id) is None

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
        ("dev_mode", "email_template", "in_body", "expected_status"),
        [
            pytest.param(True, "{}@detached.invalid", True, 422, id="dev-exact"),
            pytest.param(True, "{}@DETACHED.Invalid", True, 422, id="dev-uppercase"),
            pytest.param(True, "  {}@detached.invalid ", True, 422, id="dev-padded"),
            pytest.param(False, "{}@Detached.INVALID", True, 422, id="oidc-body"),
            pytest.param(False, "{}@Detached.INVALID", False, 400, id="oidc-claim-only"),
        ],
    )
    async def test_sync_refuses_a_detached_placeholder_address(
        self,
        client,
        db_session,
        oidc_claims,
        dev_mode,
        email_template,
        in_body,
        expected_status,
    ):
        external_id = f"claim-{uuid4()}"
        email = email_template.format(uuid4())
        oidc_claims.return_value = {"sub": external_id, "email": email, "email_verified": True}
        body = {"external_id": external_id, "display_name": "Claim", "id_token": "fake-token"}
        if in_body:
            body["email"] = email
        with patch("app.api.auth._is_dev_mode", return_value=dev_mode):
            response = await client.post("/api/v1/auth/sync", json=body)

        assert response.status_code == expected_status
        assert await UserService(db_session).get_by_external_id(external_id) is None


class TestProviderMigrationRequiresVerifiedEmail:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("email_claim", "email_verified", "expected_status"),
        [
            pytest.param(True, False, 409, id="unverified-claim"),
            pytest.param(False, True, 409, id="no-email-claim"),
            pytest.param(True, True, 200, id="verified"),
            pytest.param(True, "true", 200, id="verified-as-string"),
            pytest.param(True, "false", 409, id="unverified-as-string"),
            pytest.param(True, "TRUE", 409, id="other-string"),
            pytest.param(True, 1, 409, id="non-boolean"),
            pytest.param(True, None, 409, id="claim-missing"),
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
        oidc_claims.return_value = {"sub": "new-provider-id"}
        if email_verified is not None:
            oidc_claims.return_value["email_verified"] = email_verified
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


DIFFERENT_EMAIL = "This invite was sent to a different email address"
UNVERIFIED_DETAIL = {
    "message": "Your sign-in provider has not verified this email address",
    "error_code": "EMAIL_NOT_VERIFIED",
}


class TestInviteRequiresVerifiedEmail:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("invited_email", "email_verified", "expected_status", "expected_detail"),
        [
            pytest.param(None, True, 200, None, id="verified"),
            pytest.param(None, False, 403, UNVERIFIED_DETAIL, id="unverified"),
            pytest.param(
                "someone-else@example.com", True, 403, DIFFERENT_EMAIL, id="different-email"
            ),
            pytest.param(
                "someone-else@example.com",
                False,
                403,
                DIFFERENT_EMAIL,
                id="different-email-checked-before-verification",
            ),
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
        expected_detail,
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

        assert (response.status_code, response.json().get("detail")) == (
            expected_status,
            expected_detail,
        )
        await db_session.refresh(test_user)
        assert (test_user.family_id == family.id) is (expected_status == 200)


class TestDetachedAccount:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("path", "email_of"),
        [
            pytest.param("/api/v1/auth/session", lambda body: body["email"], id="session"),
            pytest.param(
                "/api/v1/families/me", lambda body: body["members"][0]["email"], id="family"
            ),
        ],
    )
    async def test_reads_return_the_placeholder_address(
        self, client, db_session, test_user, auth_headers, path, email_of
    ):
        family = Family(name="Family", created_by=test_user.id, invite_code=uuid4().hex[:12])
        db_session.add(family)
        await db_session.flush()
        placeholder = f"{test_user.id}@detached.invalid"
        test_user.family_id = family.id
        test_user.email = placeholder
        test_user.email_verified = False
        await db_session.flush()

        response = await client.get(path, headers=auth_headers)

        assert response.status_code == 200
        assert email_of(response.json()) == placeholder


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
        settings = Settings(debug=True, secret_key="a-strong-custom-secret")
        with patch("app.api.auth.settings", settings):
            assert _is_dev_mode() is True

    def test_is_dev_mode_false_when_oidc_configured_even_with_debug(self):
        settings = Settings(
            debug=True,
            secret_key="a-strong-custom-secret",
            oidc_issuer_url="https://auth.example.com",
            oidc_client_id="test-client",
        )
        with patch("app.api.auth.settings", settings):
            assert _is_dev_mode() is False


class TestDefaultSecretKeyWithRealAuth:
    OIDC = {"oidc_issuer_url": "https://auth.example.com", "oidc_client_id": "test-client"}
    FORWARD_AUTH = {"forward_auth_secret": "p" * 32}

    @pytest.mark.parametrize("debug", [True, False])
    @pytest.mark.parametrize("auth", [OIDC, FORWARD_AUTH, {**OIDC, **FORWARD_AUTH}])
    def test_default_key_is_refused_when_a_real_auth_mode_is_configured(self, debug, auth):
        settings = Settings(debug=debug, secret_key=DEFAULT_SECRET_KEY, **auth)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            settings.validate_security()

    def test_default_key_is_allowed_in_pure_dev_mode(self):
        settings = Settings(debug=True, secret_key=DEFAULT_SECRET_KEY)
        assert settings.validate_security() is None
        assert settings.get_auth_mode() == "dev"

    def test_default_key_is_refused_without_debug(self):
        settings = Settings(debug=False, secret_key=DEFAULT_SECRET_KEY)
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            settings.validate_security()


class TestOidcConfigured:
    @pytest.mark.parametrize(
        ("issuer", "client_id", "expected"),
        [
            ("https://auth.example.com", "test-client", True),
            ("https://auth.example.com", None, False),
            (None, "test-client", False),
            (None, None, False),
        ],
    )
    def test_needs_both_issuer_and_client_id(self, issuer, client_id, expected):
        settings = Settings(
            secret_key="a-strong-custom-secret", oidc_issuer_url=issuer, oidc_client_id=client_id
        )
        assert settings.oidc_configured is expected
