from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.services.notification_providers import EmailProvider


class TestFamilyInviteEmail:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("smtp", "send_result"),
        [
            ({}, None),
            (
                {"smtp_host": "smtp.example.com", "smtp_user": "mailer"},
                {"success": False, "error": "SMTPUTF8 is not supported by this server"},
            ),
        ],
        ids=["smtp-unconfigured", "send-failed"],
    )
    async def test_invite_reports_an_email_that_did_not_go_out(
        self, client: AsyncClient, test_user, auth_headers, monkeypatch, smtp, send_result
    ):
        settings = Settings(_env_file=None, **smtp)
        monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)
        send = AsyncMock(return_value=send_result)

        await client.post("/api/v1/families", json={"name": "Household"}, headers=auth_headers)
        with patch.object(EmailProvider, "send", send):
            response = await client.post(
                "/api/v1/families/me/invite",
                json={"email": "guest@example.com"},
                headers=auth_headers,
            )

        assert response.status_code == 201
        assert response.json()["email_sent"] is False
        assert send.await_count == (1 if smtp else 0)


class TestFamilyInviteEmailValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("submitted", "stored"),
        [
            (" Bob@Home.local", "bob@home.local"),
            ("o'brien@example.com", "o'brien@example.com"),
            ("user@münchen.de", "user@münchen.de"),
        ],
    )
    async def test_invite_accepts_and_mails_what_sign_in_accepts(
        self, client: AsyncClient, test_user, auth_headers, monkeypatch, submitted, stored
    ):
        settings = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_user="mailer")
        monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)
        send = AsyncMock(return_value={"success": True})
        await client.post("/api/v1/families", json={"name": "Household"}, headers=auth_headers)

        with patch.object(EmailProvider, "send", send):
            response = await client.post(
                "/api/v1/families/me/invite",
                json={"email": submitted},
                headers=auth_headers,
            )

        assert response.status_code == 201
        assert response.json()["email"] == stored
        assert response.json()["email_sent"] is True
        send.assert_awaited_once()
        assert send.call_args.args[0].to == stored

    @pytest.mark.asyncio
    async def test_invite_rejects_malformed_email(
        self, client: AsyncClient, test_user, auth_headers
    ):
        await client.post("/api/v1/families", json={"name": "Household"}, headers=auth_headers)

        response = await client.post(
            "/api/v1/families/me/invite",
            json={"email": "not-an-email"},
            headers=auth_headers,
        )

        assert response.status_code == 422
