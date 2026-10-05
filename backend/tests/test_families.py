from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.services.notification_providers import EmailProvider


class TestFamilyInviteEmail:
    @pytest.mark.asyncio
    async def test_trailing_slash_app_url_gives_single_slash_invite_link(
        self, client: AsyncClient, test_user, auth_headers, monkeypatch
    ):
        settings = Settings(
            _env_file=None,
            app_url="https://x.com/",
            smtp_host="smtp.example.com",
            smtp_user="mailer",
        )
        monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)
        send = AsyncMock(return_value={"success": True})

        created = await client.post(
            "/api/v1/families", json={"name": "Household"}, headers=auth_headers
        )
        assert created.status_code == 201

        with patch.object(EmailProvider, "send", send):
            response = await client.post(
                "/api/v1/families/me/invite",
                json={"email": "guest@example.com"},
                headers=auth_headers,
            )

        assert response.status_code == 201
        send.assert_awaited_once()
        message = send.call_args.args[0]
        assert message.to == "guest@example.com"
        assert 'href="https://x.com/invite?token=' in message.html_body
        assert "https://x.com/invite?token=" in message.text_body
        assert "x.com//" not in message.html_body + message.text_body

    @pytest.mark.asyncio
    async def test_invite_skips_email_when_smtp_unconfigured(
        self, client: AsyncClient, test_user, auth_headers, monkeypatch
    ):
        settings = Settings(_env_file=None)
        monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)
        send = AsyncMock(return_value={"success": True})

        await client.post("/api/v1/families", json={"name": "Household"}, headers=auth_headers)
        with patch.object(EmailProvider, "send", send):
            response = await client.post(
                "/api/v1/families/me/invite",
                json={"email": "guest@example.com"},
                headers=auth_headers,
            )

        assert response.status_code == 201
        send.assert_not_awaited()
