"""Outfit notifications must render as they did on main before the channel registry.

`fixtures/outfit_notifications_main.json` is the output of main's per-channel builders
(commit 7a8faac) for the fixture below. Each intended difference is applied explicitly.
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

MAIN = json.loads(
    (Path(__file__).parent / "fixtures" / "outfit_notifications_main.json").read_text()
)
APP_URL = "https://wardrobe.example.com"
HISTORY_URL = f"{APP_URL}/dashboard/history"
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
            "html_body": email.html_body,
            "text_body": email.text_body,
        }
    call = post_mock.call_args
    rendered = {"url": call.args[0]}
    rendered.update({k: v for k, v in call.kwargs.items() if k in ("json", "content")})
    if channel == "ntfy":
        rendered["headers"] = call.kwargs["headers"]
    return rendered


def _collapse_whitespace(markup: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r">\s+<", "><", markup)).strip()


DAYS = ["today", "tomorrow"]


@pytest.mark.parametrize("day", DAYS)
@pytest.mark.asyncio
async def test_ntfy_matches_main_with_degree_sign_in_rfc2047_title(day):
    main = MAIN[day]["ntfy"]
    new = await _render("ntfy", day)

    title = str(make_header(decode_header(new["headers"].pop("Title"))))
    main_title = main["headers"].pop("Title")
    assert title == main_title.replace("20C", "20°C")
    assert new == main


@pytest.mark.parametrize("day", DAYS)
@pytest.mark.asyncio
async def test_mattermost_matches_main_with_linked_title(day):
    main = MAIN[day]["mattermost"]
    new = await _render("mattermost", day)

    [attachment] = new["json"]["attachments"]
    assert attachment.pop("title_link") == HISTORY_URL
    assert new == main


@pytest.mark.parametrize("day", DAYS)
@pytest.mark.asyncio
async def test_expo_matches_main(day):
    assert await _render("expo_push", day) == MAIN[day]["expo_push"]


@pytest.mark.parametrize("day", DAYS)
@pytest.mark.asyncio
async def test_email_matches_main(day):
    main = MAIN[day]["email"]
    new = await _render("email", day)

    assert new["to"] == main["to"]
    assert new["subject"] == main["subject"]
    assert _collapse_whitespace(new["html_body"]) == _collapse_whitespace(main["html_body"])
    day_label = day.title()
    expected_text = (
        main["text_body"]
        .replace(
            f"Wardrowbe - {day_label}'s Outfit\n\nOccasion: Casual\n",
            f"Wardrowbe - {day_label}'s Outfit: Casual\n",
        )
        .replace("View outfit:", "View Outfit:")
    )
    assert new["text_body"] == expected_text
