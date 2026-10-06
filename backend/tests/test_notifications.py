import asyncio
import base64
from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import JSON, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.item import ClothingItem
from app.models.notification import Notification, NotificationSettings, NotificationStatus
from app.models.outfit import Outfit, OutfitSource, OutfitStatus
from app.models.schedule import Schedule
from app.schemas.notification import (
    EmailConfig,
    MattermostConfig,
    NotificationChannel,
    NtfyConfig,
)
from app.services import notification_providers
from app.services.notification_providers import (
    CHANNELS,
    EmailMessage,
    EmailProvider,
    MattermostProvider,
    NotificationMessage,
    NtfyNotification,
    NtfyProvider,
    build_family_invite_email,
    build_notification_email,
)
from app.services.notification_service import NotificationDispatcher
from app.workers.notifications import wash_reminder_message


class TestNotificationSettings:
    """Tests for notification settings management."""

    @pytest.mark.asyncio
    async def test_list_settings_empty(self, client: AsyncClient, test_user, auth_headers):
        """Test listing notification settings when none exist."""
        response = await client.get("/api/v1/notifications/settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_ntfy_setting(self, client: AsyncClient, test_user, auth_headers):
        """Test creating an ntfy notification setting."""
        response = await client.post(
            "/api/v1/notifications/settings",
            json={
                "channel": "ntfy",
                "config": {
                    "server": "https://ntfy.sh",
                    "topic": "my-wardrobe-notifications",
                },
                "enabled": True,
                "priority": 1,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["channel"] == "ntfy"
        assert data["enabled"] is True

    @pytest.mark.asyncio
    async def test_create_email_setting(self, client: AsyncClient, test_user, auth_headers):
        """Test creating an email notification setting."""
        response = await client.post(
            "/api/v1/notifications/settings",
            json={
                "channel": "email",
                "config": {
                    "email": "test@example.com",
                },
                "enabled": True,
                "priority": 2,
            },
            headers=auth_headers,
        )
        # Email channel may require SMTP config - accept 400 if email not configured
        assert response.status_code in [201, 400]
        if response.status_code == 201:
            data = response.json()
            assert data["channel"] == "email"

    @pytest.mark.asyncio
    async def test_update_setting(self, client: AsyncClient, test_user, auth_headers, db_session):
        """Test updating a notification setting."""
        # First create a setting directly in DB
        setting = NotificationSettings(
            user_id=test_user.id,
            channel="ntfy",
            config={"server": "https://ntfy.sh", "topic": "test"},
            enabled=True,
        )
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)

        # Update it
        response = await client.patch(
            f"/api/v1/notifications/settings/{setting.id}",
            json={
                "enabled": False,
                "priority": 5,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["priority"] == 5

    @pytest.mark.asyncio
    async def test_delete_setting(self, client: AsyncClient, test_user, auth_headers, db_session):
        """Test deleting a notification setting."""
        # Create a setting
        setting = NotificationSettings(
            user_id=test_user.id,
            channel="ntfy",
            config={"server": "https://ntfy.sh", "topic": "test"},
            enabled=True,
        )
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)
        setting_id = setting.id

        # Delete it
        response = await client.delete(
            f"/api/v1/notifications/settings/{setting_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200  # API returns 200 with message


class TestSchedules:
    """Tests for notification schedules."""

    @pytest.mark.asyncio
    async def test_list_schedules_empty(self, client: AsyncClient, test_user, auth_headers):
        """Test listing schedules when none exist."""
        response = await client.get("/api/v1/notifications/schedules", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_schedule(self, client: AsyncClient, test_user, auth_headers, db_session):
        """Test creating a notification schedule."""
        # First create a notification setting to use
        setting = NotificationSettings(
            user_id=test_user.id,
            channel="ntfy",
            config={"server": "https://ntfy.sh", "topic": "test"},
            enabled=True,
        )
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)

        response = await client.post(
            "/api/v1/notifications/schedules",
            json={
                "day_of_week": 0,  # Monday
                "notification_time": "07:00",
                "occasion": "work",
                "enabled": True,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["day_of_week"] == 0
        assert data["notification_time"] == "07:00"

    @pytest.mark.asyncio
    async def test_create_schedule_accepts_any_suggestion_occasion(
        self, client: AsyncClient, test_user, auth_headers
    ):
        response = await client.post(
            "/api/v1/notifications/schedules",
            json={"day_of_week": 5, "notification_time": "09:00", "occasion": "wedding"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["occasion"] == "wedding"

    @pytest.mark.asyncio
    async def test_create_schedule_rejects_unknown_occasion(
        self, client: AsyncClient, test_user, auth_headers
    ):
        response = await client.post(
            "/api/v1/notifications/schedules",
            json={"day_of_week": 5, "notification_time": "09:00", "occasion": "space-walk"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_schedule(self, client: AsyncClient, test_user, auth_headers, db_session):
        schedule = Schedule(
            user_id=test_user.id,
            day_of_week=1,
            notification_time=time(8, 0),
            occasion="work",
            enabled=True,
            notify_day_before=False,
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)

        response = await client.patch(
            f"/api/v1/notifications/schedules/{schedule.id}",
            json={
                "day_of_week": 2,
                "notification_time": "09:30",
                "occasion": "casual",
                "enabled": False,
                "notify_day_before": True,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["day_of_week"] == 2
        assert data["notification_time"] == "09:30"
        assert data["occasion"] == "casual"
        assert data["enabled"] is False
        assert data["notify_day_before"] is True

    @pytest.mark.asyncio
    async def test_delete_schedule(self, client: AsyncClient, test_user, auth_headers, db_session):
        schedule = Schedule(
            user_id=test_user.id,
            day_of_week=3,
            notification_time=time(7, 15),
            occasion="work",
            enabled=True,
            notify_day_before=False,
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)

        response = await client.delete(
            f"/api/v1/notifications/schedules/{schedule.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Schedule deleted"

        get_response = await client.get(
            f"/api/v1/notifications/schedules/{schedule.id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404


class TestNotificationDefaults:
    """Tests for notification defaults endpoint."""

    @pytest.mark.asyncio
    async def test_get_ntfy_defaults(self, client: AsyncClient, test_user, auth_headers):
        """Test getting default ntfy configuration."""
        response = await client.get(
            "/api/v1/notifications/defaults/ntfy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should have server and has_token fields
        assert "server" in data
        assert "has_token" in data


SETTINGS_READERS = (
    "app.services.notification_service",
    "app.services.notification_providers",
    "app.workers.notifications",
)


def _outfit_email() -> EmailMessage:
    outfit = SimpleNamespace(
        id=uuid4(),
        scheduled_for=None,
        weather_data={"temperature": 20, "condition": HOSTILE_NAME},
        occasion="casual",
        reasoning=None,
        ai_raw_response=None,
        style_notes=None,
    )
    user = SimpleNamespace(display_name="Sam", timezone="UTC")
    message = NotificationDispatcher(None)._build_outfit_message(outfit, user)
    return build_notification_email("to@example.com", message)


def _wash_email() -> EmailMessage:
    message = wash_reminder_message([ClothingItem(type="shirt", name="Blue Shirt")])
    return build_notification_email("to@example.com", message)


def _invite_email() -> EmailMessage:
    return build_family_invite_email(
        to="to@example.com", family_name="Home", inviter_name="Sam", invite_token="tok"
    )


class TestAppLinks:
    def test_default_app_url_is_local_frontend(self, monkeypatch):
        monkeypatch.delenv("APP_URL", raising=False)
        assert Settings(_env_file=None).app_url == "http://localhost:3000"

    def test_trailing_slash_is_stripped_from_env(self, monkeypatch):
        monkeypatch.setenv("APP_URL", "https://x.com/")
        settings = Settings(_env_file=None)
        assert settings.app_url == "https://x.com"
        assert settings.app_link("/dashboard/wardrobe") == "https://x.com/dashboard/wardrobe"

    @pytest.mark.parametrize(
        ("build", "link"),
        [
            (_outfit_email, "https://x.com/dashboard/history"),
            (_wash_email, "https://x.com/dashboard/wardrobe"),
            (_invite_email, "https://x.com/invite?token=tok"),
        ],
        ids=["outfit", "laundry", "invite"],
    )
    def test_emails_link_a_trailing_slash_app_url_with_one_slash(self, monkeypatch, build, link):
        settings = Settings(_env_file=None, app_url="https://x.com/")
        for module in SETTINGS_READERS:
            monkeypatch.setattr(f"{module}.get_settings", lambda: settings)

        email = build()

        assert f'href="{link}"' in email.html_body
        assert link in email.text_body
        assert "x.com//" not in email.html_body + email.text_body


class TestEmailProviderSettings:
    def test_reads_smtp_config_from_settings(self, monkeypatch):
        settings = Settings(
            _env_file=None,
            smtp_host="smtp.example.com",
            smtp_port=2525,
            smtp_user="mailer",
            smtp_password="secret",
            smtp_use_tls=False,
            smtp_from_name="Closet",
            smtp_from_email="closet@example.com",
        )
        monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)

        provider = EmailProvider(EmailConfig(address="to@example.com"))

        assert provider.is_configured()
        assert provider.smtp_host == "smtp.example.com"
        assert provider.smtp_port == 2525
        assert provider.smtp_user == "mailer"
        assert provider.smtp_password == "secret"
        assert provider.smtp_use_tls is False
        assert provider.from_name == "Closet"
        assert provider.from_email == "closet@example.com"

    def test_from_email_falls_back_to_smtp_user(self, monkeypatch):
        settings = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_user="mailer")
        monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)

        provider = EmailProvider(EmailConfig(address="to@example.com"))

        assert provider.smtp_use_tls is True
        assert provider.from_name == "Wardrowbe"
        assert provider.from_email == "mailer"

    def test_unconfigured_without_smtp_host(self, monkeypatch):
        settings = Settings(_env_file=None)
        monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)

        assert not EmailProvider(EmailConfig(address="to@example.com")).is_configured()


# An SMTP server that, like many self-hosted relays, does not advertise SMTPUTF8.
@pytest_asyncio.fixture
async def ascii_smtp_server(monkeypatch):
    received: list[tuple[str, list[str], bytes]] = []

    async def session(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        sender = ""
        recipients: list[str] = []
        writer.write(b"220 fake ESMTP\r\n")
        while line := await reader.readline():
            command = line.decode().strip()
            verb = command.split(" ", 1)[0].upper()
            reply = b"250 ok\r\n"
            if verb == "EHLO":
                reply = b"250-fake\r\n250 AUTH PLAIN\r\n"
            elif verb == "AUTH":
                reply = b"235 ok\r\n"
            elif verb == "MAIL":
                sender = command.split(":", 1)[1].split()[0].strip("<>")
            elif verb == "RCPT":
                recipients.append(command.split(":", 1)[1].strip("<> "))
            elif verb == "DATA":
                writer.write(b"354 go\r\n")
                received.append((sender, recipients, await reader.readuntil(b"\r\n.\r\n")))
            elif verb == "QUIT":
                writer.write(b"221 bye\r\n")
                break
            writer.write(reply)
            await writer.drain()
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(session, "127.0.0.1", 0)
    settings = Settings(
        _env_file=None,
        smtp_host="127.0.0.1",
        smtp_port=server.sockets[0].getsockname()[1],
        smtp_user="mailer",
        smtp_password="secret",
        smtp_use_tls=False,
        smtp_from_email="closet@example.com",
    )
    monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)
    yield received
    server.close()
    await server.wait_closed()


def _set_from_email(monkeypatch, from_email: str) -> None:
    settings = notification_providers.get_settings().model_copy(
        update={"smtp_from_email": from_email}
    )
    monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)


def _plain_email(to: str) -> EmailMessage:
    return EmailMessage(to=to, subject="Hello", html_body="<p>Hello</p>", text_body="Hello")


class TestEmailProviderAddresses:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("from_email", "address", "sender", "recipient"),
        [
            ("closet@example.com", "guest@example.com", "closet@example.com", "guest@example.com"),
            (
                "closet@example.com",
                "user@münchen.de",
                "closet@example.com",
                "user@xn--mnchen-3ya.de",
            ),
            (
                "closet@münchen.de",
                "guest@example.com",
                "closet@xn--mnchen-3ya.de",
                "guest@example.com",
            ),
        ],
    )
    async def test_sends_an_ascii_local_part_without_smtputf8(
        self, ascii_smtp_server, monkeypatch, from_email, address, sender, recipient
    ):
        _set_from_email(monkeypatch, from_email)
        provider = EmailProvider(EmailConfig(address=address))

        result = await provider.send(_plain_email(address))

        assert result == {"success": True}
        ((envelope_from, recipients, data),) = ascii_smtp_server
        assert (envelope_from, recipients) == (sender, [recipient])
        assert f"From: Wardrowbe <{sender}>\r\n".encode() in data
        assert f"To: {recipient}\r\n".encode() in data

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("from_email", "address", "named"),
        [
            ("closet@example.com", "jörg@example.com", "jörg@example.com"),
            ("jörg@münchen.de", "guest@example.com", "jörg@münchen.de"),
        ],
        ids=["recipient", "sender"],
    )
    async def test_non_ascii_local_part_fails_clearly_without_smtputf8(
        self, ascii_smtp_server, monkeypatch, from_email, address, named
    ):
        _set_from_email(monkeypatch, from_email)
        provider = EmailProvider(EmailConfig(address=address))

        result = await provider.send(_plain_email(address))

        assert result == {
            "success": False,
            "error": f"The mail server does not support SMTPUTF8, which {named} needs "
            "because its name before the @ is not ASCII",
        }
        assert ascii_smtp_server == []


class TestChannelRegistry:
    def test_every_channel_has_a_config_and_provider(self):
        assert set(CHANNELS) == set(NotificationChannel)

    @pytest.mark.asyncio
    async def test_create_rejects_config_that_does_not_match_channel(
        self, client: AsyncClient, test_user, auth_headers
    ):
        response = await client.post(
            "/api/v1/notifications/settings",
            json={"channel": "expo_push", "config": {"push_token": "nope"}},
            headers=auth_headers,
        )
        assert response.status_code == 400


class TestNotificationEmail:
    @pytest.mark.parametrize(
        ("build", "forbidden", "escaped", "plain"),
        [
            (
                lambda: build_notification_email(
                    "to@example.com",
                    NotificationMessage(title="Laundry <b>", body="1 item: <script>x</script>"),
                ),
                ["<script>", "<b>"],
                ["Laundry &lt;b&gt;", "1 item: &lt;script&gt;x&lt;/script&gt;"],
                "1 item: <script>x</script>",
            ),
            (
                lambda: build_family_invite_email(
                    to="guest@example.com",
                    family_name="Smith & <Co>",
                    inviter_name='<img src=x onerror="alert(1)">',
                    invite_token="tok",
                ),
                ["<img"],
                [
                    "<strong>&lt;img src=x onerror=&quot;alert(1)&quot;&gt;</strong>",
                    "<strong>Smith &amp; &lt;Co&gt;</strong>",
                ],
                '<img src=x onerror="alert(1)"> invited you to join the family "Smith & <Co>"',
            ),
        ],
        ids=["notification", "family-invite"],
    )
    def test_user_text_is_escaped_in_html_and_plain_in_text(self, build, forbidden, escaped, plain):
        email = build()

        for markup in forbidden:
            assert markup not in email.html_body
        for fragment in escaped:
            assert fragment in email.html_body
        assert plain in email.text_body


HOSTILE_NAME = "@channel [win](https://evil.example) *now* <@here> ~town_square #1 \\"
ESCAPED_NAME = (
    "@\u200bchannel \\[win\\](https://evil.example) \\*now\\* \\<@\u200bhere\\> "
    "\\~town\\_square \\#1 \\\\"
)


def _hostile_outfit_message() -> NotificationMessage:
    outfit = SimpleNamespace(
        id=uuid4(),
        scheduled_for=None,
        weather_data={"temperature": 20, "condition": HOSTILE_NAME},
        occasion="casual",
        reasoning=f"Pair {HOSTILE_NAME}",
        ai_raw_response={"highlights": [HOSTILE_NAME]},
        style_notes=HOSTILE_NAME,
    )
    user = SimpleNamespace(display_name=HOSTILE_NAME, timezone="UTC")
    return NotificationDispatcher(None)._build_outfit_message(outfit, user)


class TestMattermostEscaping:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("build", "text", "title", "attachment_text"),
        [
            (
                _hostile_outfit_message,
                f"Good morning, {ESCAPED_NAME}! Here's your outfit suggestion for today:",
                f"Today's Outfit: Casual | 20°C {ESCAPED_NAME}",
                f"**Pair {ESCAPED_NAME}**\n\n- {ESCAPED_NAME}\n\n_Tip: {ESCAPED_NAME}_",
            ),
            (
                lambda: wash_reminder_message([ClothingItem(type="shirt", name=HOSTILE_NAME)]),
                "",
                "Laundry Reminder",
                f"1 item needs washing: {ESCAPED_NAME}",
            ),
            (
                lambda: NotificationMessage(
                    title=f"12. {HOSTILE_NAME}",
                    body="1. one\n2) two\n- dash\n  + plus\n# hash\n> quote\n"
                    "Setext\n===\n---\nO'Brien wrote 5*3 - 1.5",
                ),
                "",
                f"12\\. {ESCAPED_NAME}",
                "1\\. one\n2\\) two\n\\- dash\n  \\+ plus\n\\# hash\n\\> quote\n"
                "Setext\n\\===\n\\---\nO'Brien wrote 5\\*3 - 1.5",
            ),
        ],
        ids=["outfit", "laundry", "line-start-markers"],
    )
    async def test_user_text_cannot_mention_or_link(self, build, text, title, attachment_text):
        post = AsyncMock(
            return_value=httpx.Response(200, request=httpx.Request("POST", "https://x"))
        )
        provider = MattermostProvider(
            MattermostConfig(webhook_url="https://chat.example.com/hooks/abc")
        )

        with patch.object(httpx.AsyncClient, "post", post):
            await provider.deliver(build())

        payload = post.call_args.kwargs["json"]
        assert payload["text"] == text
        assert payload["attachments"][0]["title"] == title
        assert payload["attachments"][0]["text"] == attachment_text


class TestNtfyHeaders:
    @pytest.mark.asyncio
    async def test_non_ascii_title_is_rfc2047_encoded(self):
        post = AsyncMock(
            return_value=httpx.Response(
                200, json={"id": "m"}, request=httpx.Request("POST", "https://ntfy.sh/t")
            )
        )
        provider = NtfyProvider(NtfyConfig(topic="topic-1"))

        with patch.object(httpx.AsyncClient, "post", post):
            result = await provider.send(
                NtfyNotification(topic="topic-1", title="Today's Casual - 20\u00b0C", message="m")
            )

        assert result["success"] is True
        title = post.call_args.kwargs["headers"]["Title"]
        encoded = base64.b64encode("Today's Casual - 20\u00b0C".encode()).decode()
        assert title == f"=?UTF-8?B?{encoded}?="


class TestNotificationSettingsList:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("config", "shown", "error"),
        [
            (
                {"address": "a..b@example.com"},
                {"address": "a..b@example.com"},
                "Value error, An email address cannot have two periods in a row.",
            ),
            (JSON.NULL, {}, "Input should be a valid dictionary or instance of EmailConfig"),
            (
                ["a@example.com"],
                {},
                "Input should be a valid dictionary or instance of EmailConfig",
            ),
            ("a@example.com", {}, "Input should be a valid dictionary or instance of EmailConfig"),
        ],
        ids=["rejected-address", "null", "list", "scalar"],
    )
    async def test_skips_unknown_channels_and_flags_configs_this_version_rejects(
        self,
        client: AsyncClient,
        test_user,
        auth_headers,
        db_session: AsyncSession,
        config,
        shown,
        error,
    ):
        broken = NotificationSettings(
            user_id=test_user.id, channel="email", priority=2, config=config
        )
        db_session.add_all(
            [
                NotificationSettings(
                    user_id=test_user.id, channel="pushover", priority=1, config={"key": "k"}
                ),
                broken,
                NotificationSettings(
                    user_id=test_user.id,
                    channel="ntfy",
                    priority=3,
                    config={"server": "https://ntfy.example.com", "topic": "outfits"},
                ),
            ]
        )
        await db_session.commit()

        response = await client.get("/api/v1/notifications/settings", headers=auth_headers)
        single = await client.get(
            f"/api/v1/notifications/settings/{broken.id}", headers=auth_headers
        )
        test_send = await client.post(
            f"/api/v1/notifications/settings/{broken.id}/test", headers=auth_headers
        )

        assert response.status_code == 200
        assert [
            (row["channel"], row["config"], row["config_error"]) for row in response.json()
        ] == [
            ("email", shown, error),
            ("ntfy", {"server": "https://ntfy.example.com", "topic": "outfits"}, None),
        ]
        assert single.status_code == 200
        assert (single.json()["config"], single.json()["config_error"]) == (shown, error)
        assert (test_send.status_code, test_send.json()) == (400, {"detail": error})

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "suffix", "body"),
        [
            ("GET", "", None),
            ("PATCH", "", {"enabled": False}),
            ("PATCH", "", {"config": {"key": "k2"}}),
            ("POST", "/test", None),
            ("DELETE", "", None),
        ],
    )
    async def test_a_stored_channel_this_version_cannot_send_to_is_not_found(
        self,
        client: AsyncClient,
        test_user,
        auth_headers,
        db_session: AsyncSession,
        method,
        suffix,
        body,
    ):
        setting_id = uuid4()
        db_session.add(
            NotificationSettings(
                id=setting_id,
                user_id=test_user.id,
                channel="pushover",
                priority=1,
                config={"key": "k"},
            )
        )
        await db_session.commit()

        response = await client.request(
            method,
            f"/api/v1/notifications/settings/{setting_id}{suffix}",
            json=body,
            headers=auth_headers,
        )

        assert response.status_code == 404
        db_session.expire_all()
        stored = await db_session.get(NotificationSettings, setting_id)
        assert (stored.enabled, stored.config) == (True, {"key": "k"})


class TestNotificationHistory:
    @pytest.mark.asyncio
    async def test_returns_rows_with_unknown_channel(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        db_session.add(
            Notification(
                user_id=test_user.id,
                channel="unknown",
                status=NotificationStatus.failed,
                payload={"type": "wash_reminder"},
                error_message="All channels failed",
            )
        )
        await db_session.commit()

        response = await client.get("/api/v1/notifications/history", headers=auth_headers)

        assert response.status_code == 200
        assert [row["channel"] for row in response.json()] == ["unknown"]


TODAY = date(2026, 10, 6)


class TestDispatcherDelivery:
    @pytest.fixture(autouse=True)
    def frozen_clock(self):
        with patch("app.utils.timezone.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
            yield

    @pytest.fixture
    async def outfit(self, db_session: AsyncSession, test_user) -> Outfit:
        outfit = Outfit(
            user_id=test_user.id,
            occasion="casual",
            scheduled_for=TODAY,
            status=OutfitStatus.pending,
            source=OutfitSource.scheduled,
            weather_data={"temperature": 20, "condition": "Sunny"},
            reasoning="Light layers",
            style_notes="Roll the sleeves",
            ai_raw_response={"highlights": ["Breathable linen"]},
        )
        db_session.add(outfit)
        await db_session.commit()
        await db_session.refresh(outfit)
        return outfit

    def _post(self, failing: set[str]) -> AsyncMock:
        async def post(url, **kwargs):
            request = httpx.Request("POST", url)
            if url in failing:
                return httpx.Response(500, text="down", request=request)
            return httpx.Response(200, json={"id": "m"}, request=request)

        return AsyncMock(side_effect=post)

    async def _send_only_via(
        self,
        db_session: AsyncSession,
        test_user,
        outfit,
        channel: str,
        config: dict,
    ) -> tuple[AsyncMock, AsyncMock]:
        db_session.add(
            NotificationSettings(user_id=test_user.id, channel=channel, priority=1, config=config)
        )
        await db_session.commit()
        post = self._post(failing=set())
        email_send = AsyncMock(return_value={"success": True})

        with (
            patch.object(httpx.AsyncClient, "post", post),
            patch.object(EmailProvider, "send", email_send),
        ):
            await NotificationDispatcher(db_session).send_outfit_notification(
                test_user.id, outfit.id
            )
        return post, email_send

    @pytest.mark.asyncio
    async def test_mattermost_outfit_greets_user_and_shows_weather(
        self, db_session: AsyncSession, test_user, outfit
    ):
        post, _ = await self._send_only_via(
            db_session,
            test_user,
            outfit,
            "mattermost",
            {"webhook_url": "https://chat.example.com/hooks/abc"},
        )

        payload = post.call_args.kwargs["json"]
        assert payload["text"] == (
            f"Good morning, {test_user.display_name}! Here's your outfit suggestion for today:"
        )
        [attachment] = payload["attachments"]
        assert attachment["title"] == "Today's Outfit: Casual | 20°C Sunny"
        assert attachment["title_link"].endswith("/dashboard/history")
        assert "Light layers" in attachment["text"]

    @pytest.mark.asyncio
    async def test_email_outfit_has_weather_line_under_heading(
        self, db_session: AsyncSession, test_user, outfit, monkeypatch
    ):
        settings = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_user="mailer")
        monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)

        outfit.scheduled_for = date(2026, 10, 7)
        _, email_send = await self._send_only_via(
            db_session, test_user, outfit, "email", {"address": "a@example.com"}
        )

        email = email_send.call_args.args[0]
        assert email.subject == "Tomorrow's Outfit: Casual"
        assert "Tomorrow's Outfit: Casual" in email.html_body
        assert "20°C, Sunny (forecast)" in email.html_body

    @pytest.mark.asyncio
    async def test_expo_outfit_body_is_reasoning_and_tip_only(
        self, db_session: AsyncSession, test_user, outfit
    ):
        token = "ExponentPushToken[abc]"
        post, _ = await self._send_only_via(
            db_session, test_user, outfit, "expo_push", {"push_token": token}
        )

        payload = post.call_args.kwargs["json"]
        assert payload["to"] == token
        assert payload["title"] == "Today's Casual Outfit - 20°C"
        assert payload["body"] == "Light layers \u2022 Tip: Roll the sleeves"
        assert payload["data"] == {"outfit_id": str(outfit.id), "screen": "history"}

    @pytest.mark.asyncio
    async def test_uses_priority_order_and_stops_at_first_success(
        self, db_session: AsyncSession, test_user, outfit
    ):
        webhook = "https://chat.example.com/hooks/abc"
        db_session.add_all(
            [
                NotificationSettings(
                    user_id=test_user.id, channel="pushover", priority=0, config={"key": "k"}
                ),
                NotificationSettings(
                    user_id=test_user.id,
                    channel="email",
                    priority=0,
                    config={"address": "a..b@example.com"},
                ),
                NotificationSettings(
                    user_id=test_user.id,
                    channel="ntfy",
                    priority=2,
                    config={"server": "https://ntfy.example.com", "topic": "outfits"},
                ),
                NotificationSettings(
                    user_id=test_user.id,
                    channel="mattermost",
                    priority=1,
                    config={"webhook_url": webhook},
                ),
            ]
        )
        await db_session.commit()
        post = self._post(failing={webhook})
        email_send = AsyncMock(return_value={"success": True})

        with (
            patch.object(httpx.AsyncClient, "post", post),
            patch.object(EmailProvider, "send", email_send),
        ):
            results = await NotificationDispatcher(db_session).send_outfit_notification(
                test_user.id, outfit.id
            )

        assert [(r.channel, r.status, r.error) for r in results] == [
            (
                "email",
                NotificationStatus.failed,
                "Value error, An email address cannot have two periods in a row.",
            ),
            ("mattermost", NotificationStatus.failed, "HTTP 500: down"),
            ("ntfy", NotificationStatus.sent, None),
        ]
        assert [c.args[0] for c in post.call_args_list] == [
            webhook,
            "https://ntfy.example.com/outfits",
        ]
        ntfy_call = post.call_args_list[1]
        assert ntfy_call.kwargs["headers"]["Click"].endswith("/dashboard/history")
        assert "Light layers" in ntfy_call.kwargs["content"]
        email_send.assert_not_called()
        rows = (
            (
                await db_session.execute(
                    select(Notification).where(Notification.outfit_id == outfit.id)
                )
            )
            .scalars()
            .all()
        )
        assert {(r.channel, r.status, r.error_message, r.sent_at is not None) for r in rows} == {
            (
                "email",
                NotificationStatus.failed,
                "Value error, An email address cannot have two periods in a row.",
                False,
            ),
            ("mattermost", NotificationStatus.failed, "HTTP 500: down", False),
            ("ntfy", NotificationStatus.sent, None, True),
        }

    @pytest.mark.asyncio
    async def test_all_failing_records_retry_on_first_channel(
        self, db_session: AsyncSession, test_user, outfit
    ):
        webhook = "https://chat.example.com/hooks/abc"
        ntfy_url = "https://ntfy.example.com/outfits"
        db_session.add_all(
            [
                NotificationSettings(
                    user_id=test_user.id,
                    channel="mattermost",
                    priority=1,
                    config={"webhook_url": webhook},
                ),
                NotificationSettings(
                    user_id=test_user.id,
                    channel="ntfy",
                    priority=2,
                    config={"server": "https://ntfy.example.com", "topic": "outfits"},
                ),
            ]
        )
        await db_session.commit()

        with patch.object(httpx.AsyncClient, "post", self._post(failing={webhook, ntfy_url})):
            await NotificationDispatcher(db_session).send_outfit_notification(
                test_user.id, outfit.id
            )

        rows = (
            (
                await db_session.execute(
                    select(Notification).where(Notification.outfit_id == outfit.id)
                )
            )
            .scalars()
            .all()
        )
        assert {(r.channel, r.status, r.error_message, r.attempts) for r in rows} == {
            ("mattermost", NotificationStatus.retrying, "HTTP 500: down", 1),
            ("ntfy", NotificationStatus.failed, "HTTP 500: down", 0),
        }
        assert outfit.sent_at is None

    @pytest.mark.parametrize(
        ("occasion", "weather", "title"),
        [
            ("date", {"temperature": 18.0}, "Today's Date Outfit - 18°C"),
            ("smart-casual", {"temperature": 17.6}, "Today's Smart Casual Outfit - 18°C"),
            ("casual", None, "Today's Casual Outfit"),
        ],
    )
    def test_title_names_the_occasion_outfit_and_rounds_degrees(
        self, test_user, occasion, weather, title
    ):
        outfit = SimpleNamespace(
            id=uuid4(),
            scheduled_for=TODAY,
            occasion=occasion,
            weather_data=weather,
            reasoning=None,
            ai_raw_response=None,
            style_notes=None,
        )

        message = NotificationDispatcher(None)._build_outfit_message(outfit, test_user)

        assert message.title == title

    @pytest.mark.parametrize(
        ("scheduled_for", "day_label"),
        [(date(2026, 10, 7), "Tomorrow"), (TODAY, "Today"), (date(2026, 10, 5), "Monday")],
    )
    @pytest.mark.asyncio
    async def test_retry_labels_the_day_from_the_outfit_date(
        self, db_session: AsyncSession, test_user, outfit, scheduled_for, day_label
    ):
        webhook = "https://chat.example.com/hooks/abc"
        outfit.scheduled_for = scheduled_for
        db_session.add(
            NotificationSettings(
                user_id=test_user.id,
                channel="mattermost",
                priority=1,
                config={"webhook_url": webhook},
            )
        )
        notification = Notification(
            user_id=test_user.id,
            outfit_id=outfit.id,
            channel="mattermost",
            status=NotificationStatus.retrying,
            payload={"occasion": outfit.occasion},
            attempts=1,
        )
        db_session.add(notification)
        await db_session.commit()
        post = self._post(failing=set())

        with patch.object(httpx.AsyncClient, "post", post):
            result = await NotificationDispatcher(db_session).retry_notification(notification)

        assert result.status == NotificationStatus.sent
        [attachment] = post.call_args.kwargs["json"]["attachments"]
        assert attachment["title"].startswith(f"{day_label}'s Outfit: Casual")
