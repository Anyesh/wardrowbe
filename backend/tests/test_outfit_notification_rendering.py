"""Outfit notifications must render as they did on main before the channel registry.

`fixtures/outfit_notifications_expected.json` started as the output of main's per-channel builders
(commit 7a8faac) for the outfit below, with the email HTML whitespace collapsed. It differs from
main only where the redesign meant to: the ntfy title carries the degree sign, the Mattermost
title links to the history page, and the email text puts the occasion in the heading.
"""

import json
import re
from datetime import UTC, date, datetime
from email.header import decode_header, make_header
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx
import pytest

from app.config import Settings
from app.services.notification_providers import EXPO_PUSH_URL, EmailProvider, send_via_channel
from app.services.notification_service import NotificationDispatcher

EXPECTED = json.loads(
    (Path(__file__).parent / "fixtures" / "outfit_notifications_expected.json").read_text()
)
APP_URL = "https://wardrobe.example.com"
OUTFIT = SimpleNamespace(
    id=UUID("00000000-0000-0000-0000-0000000000aa"),
    occasion="casual",
    weather_data={"temperature": 20, "condition": "Partly Cloudy"},
    reasoning="Light layers for a mild day",
    ai_raw_response={
        "highlights": ["Breathable linen", "Neutral palette", "Comfortable loafers", "Dropped"]
    },
    style_notes="Roll the sleeves",
)
USER = SimpleNamespace(display_name="Sam", timezone="UTC")
OUTFIT_DATES = {"today": date(2026, 10, 6), "tomorrow": date(2026, 10, 7)}
CHANNELS = {
    "ntfy": {"server": "https://ntfy.example.com", "topic": "outfits"},
    "mattermost": {"webhook_url": "https://chat.example.com/hooks/abc"},
    "email": {"address": "sam@example.com"},
    "expo_push": {"push_token": "ExponentPushToken[abc]"},
}


@pytest.fixture(autouse=True)
def frozen_clock():
    with patch("app.utils.timezone.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
        yield


@pytest.fixture(autouse=True)
def app_settings(monkeypatch):
    settings = Settings(_env_file=None, app_url=APP_URL)
    monkeypatch.setattr("app.services.notification_service.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.notification_providers.get_settings", lambda: settings)


async def _render(channel: str, day: str) -> dict:
    async def post(url, **kwargs):
        body = {"data": {"status": "ok", "id": "t"}} if url == EXPO_PUSH_URL else {"id": "m"}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    post_mock = AsyncMock(side_effect=post)
    send_mock = AsyncMock(return_value={"success": True})
    outfit = SimpleNamespace(**vars(OUTFIT), scheduled_for=OUTFIT_DATES[day])
    message = NotificationDispatcher(None)._build_outfit_message(outfit, USER)
    with (
        patch.object(httpx.AsyncClient, "post", post_mock),
        patch.object(EmailProvider, "send", send_mock),
    ):
        await send_via_channel(SimpleNamespace(channel=channel, config=CHANNELS[channel]), message)

    if channel == "email":
        email = send_mock.call_args.args[0]
        return {
            "to": email.to,
            "subject": email.subject,
            "html_body": _collapse_whitespace(email.html_body),
            "text_body": email.text_body,
        }
    call = post_mock.call_args
    rendered = {"url": call.args[0]}
    rendered.update({k: v for k, v in call.kwargs.items() if k in ("json", "content")})
    if channel == "ntfy":
        headers = dict(call.kwargs["headers"])
        headers["Title"] = str(make_header(decode_header(headers["Title"])))
        rendered["headers"] = headers
    return rendered


def _collapse_whitespace(markup: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r">\s+<", "><", markup)).strip()


@pytest.mark.parametrize("day", ["today", "tomorrow"])
@pytest.mark.parametrize("channel", ["ntfy", "mattermost", "email", "expo_push"])
@pytest.mark.asyncio
async def test_outfit_notification_renders_as_expected(channel, day):
    assert await _render(channel, day) == EXPECTED[day][channel]
