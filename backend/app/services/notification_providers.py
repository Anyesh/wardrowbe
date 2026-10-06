import base64
import html
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol

import aiosmtplib
import httpx
from pydantic import BaseModel

from app.config import get_settings
from app.models.notification import NotificationSettings, NotificationStatus
from app.schemas.notification import (
    EmailConfig,
    ExpoPushConfig,
    MattermostConfig,
    NotificationChannel,
    NtfyConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class WeatherSummary:
    temperature: float | int | None
    condition: str | None
    forecast: bool = False


@dataclass
class NotificationMessage:
    """Channel-neutral content; each provider renders the fields its medium can show.

    `title`, `body` and `short_body` are plain text for compact push surfaces. Long-form
    channels (email, chat) render `heading`, `greeting`, `weather` and the structured
    `lead`/`highlights`/`tip` sections, falling back to `title`/`body` when they are unset.
    """

    title: str
    body: str
    url: str | None = None
    url_label: str = "Open Wardrowbe"
    tags: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    heading: str | None = None
    greeting: str | None = None
    short_body: str | None = None
    weather: WeatherSummary | None = None
    lead: str | None = None
    highlights: list[str] = field(default_factory=list)
    tip: str | None = None

    @property
    def full_heading(self) -> str:
        return self.heading or self.title

    @property
    def has_sections(self) -> bool:
        return bool(self.lead or self.highlights or self.tip)


def _header_value(value: str) -> str:
    # httpx encodes header values as ASCII, so ntfy's documented RFC 2047 form carries the rest.
    if value.isascii():
        return value
    return f"=?UTF-8?B?{base64.b64encode(value.encode()).decode()}?="


@dataclass
class NtfyNotification:
    topic: str
    title: str
    message: str
    tags: list[str] = field(default_factory=list)
    priority: int = 3  # 1-5, 3 is default
    click: str | None = None
    attach: str | None = None
    actions: list[dict] | None = None


class NtfyProvider:
    def __init__(self, config: NtfyConfig):
        self.server = config.server.rstrip("/")
        self.topic = config.topic
        self.token = config.token

    async def send(self, notification: NtfyNotification) -> dict:
        headers = {
            "Title": _header_value(notification.title),
            "Priority": str(notification.priority),
        }

        if notification.tags:
            headers["Tags"] = ",".join(notification.tags)

        if notification.click:
            headers["Click"] = notification.click

        if notification.attach:
            headers["Attach"] = notification.attach

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        if notification.actions:
            actions = []
            for action in notification.actions:
                actions.append(f"{action['type']}, {action['label']}, {action['url']}")
            headers["Actions"] = "; ".join(actions)

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.server}/{notification.topic or self.topic}",
                    headers=headers,
                    content=notification.message,
                )

                if response.status_code == 200:
                    return {"success": True, "response": response.json()}
                else:
                    error = f"HTTP {response.status_code}: {response.text}"
                    logger.warning("ntfy request failed: %s", error)
                    return {"success": False, "error": error}
        except Exception as e:
            logger.exception("ntfy send failed")
            return {"success": False, "error": str(e)}

    async def deliver(self, message: NotificationMessage) -> dict:
        return await self.send(
            NtfyNotification(
                topic=self.topic,
                title=message.title,
                message=message.body,
                tags=message.tags,
                click=message.url,
            )
        )

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.send(
                NtfyNotification(
                    topic=self.topic,
                    title="Wardrowbe Test",
                    message="This is a test notification from Wardrowbe.",
                    tags=["white_check_mark", "shirt"],
                    priority=2,
                )
            )
            if result.get("success"):
                return True, "Test notification sent successfully"
            return False, result.get("error", "Unknown error")
        except Exception as e:
            return False, str(e)


# Mattermost Provider
@dataclass
class MattermostAttachment:
    title: str
    text: str = ""
    title_link: str | None = None
    color: str = "#3B82F6"
    fields: list[dict] = field(default_factory=list)
    thumb_url: str | None = None
    image_url: str | None = None
    actions: list[dict] = field(default_factory=list)


@dataclass
class MattermostMessage:
    text: str
    username: str = "Wardrowbe"
    icon_emoji: str = ":shirt:"
    attachments: list[MattermostAttachment] = field(default_factory=list)


def _mattermost_weather(weather: WeatherSummary | None) -> str:
    if weather is None:
        return ""
    temperature = "?" if weather.temperature is None else weather.temperature
    return f" | {temperature}C {weather.condition or ''}"


def _mattermost_text(message: NotificationMessage) -> str:
    if not message.has_sections:
        return message.body
    parts = []
    if message.lead:
        parts.append(f"**{message.lead}**")
    if message.highlights:
        parts.append("\n".join(f"- {h}" for h in message.highlights))
    if message.tip:
        parts.append(f"_Tip: {message.tip}_")
    return "\n\n".join(parts)


class MattermostProvider:
    def __init__(self, config: MattermostConfig):
        self.webhook_url = config.webhook_url

    async def send(self, message: MattermostMessage) -> dict:
        payload = {
            "text": message.text,
            "username": message.username,
            "icon_emoji": message.icon_emoji,
        }

        if message.attachments:
            payload["attachments"] = [
                {
                    "title": a.title,
                    "title_link": a.title_link,
                    "text": a.text,
                    "color": a.color,
                    "fields": a.fields,
                    "thumb_url": a.thumb_url,
                    "image_url": a.image_url,
                    "actions": a.actions,
                }
                for a in message.attachments
            ]

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(self.webhook_url, json=payload)

                if response.status_code == 200:
                    return {"success": True}
                else:
                    error = f"HTTP {response.status_code}: {response.text}"
                    logger.warning("Mattermost request failed: %s", error)
                    return {"success": False, "error": error}
        except Exception as e:
            logger.exception("Mattermost send failed")
            return {"success": False, "error": str(e)}

    async def deliver(self, message: NotificationMessage) -> dict:
        return await self.send(
            MattermostMessage(
                text=message.greeting or "",
                attachments=[
                    MattermostAttachment(
                        title=f"{message.full_heading}{_mattermost_weather(message.weather)}",
                        title_link=message.url,
                        text=_mattermost_text(message),
                    )
                ],
            )
        )

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.send(
                MattermostMessage(text="This is a test message from Wardrowbe.")
            )
            if result.get("success"):
                return True, "Test notification sent successfully"
            return False, result.get("error", "Unknown error")
        except Exception as e:
            return False, str(e)


# Email Provider
@dataclass
class EmailMessage:
    to: str
    subject: str
    html_body: str
    text_body: str = ""


class EmailProvider:
    def __init__(self, config: EmailConfig):
        settings = get_settings()
        self.to_address = config.address
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_password = settings.smtp_password
        self.smtp_use_tls = settings.smtp_use_tls
        self.from_name = settings.smtp_from_name
        self.from_email = settings.smtp_from_email or self.smtp_user

    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user)

    async def send(self, message: EmailMessage) -> dict:
        if not self.is_configured():
            return {"success": False, "error": "SMTP not configured"}

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = message.to

            if message.text_body:
                msg.attach(MIMEText(message.text_body, "plain"))

            msg.attach(MIMEText(message.html_body, "html"))

            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=self.smtp_use_tls,
            )
            return {"success": True}
        except Exception as e:
            logger.exception("Email send failed")
            return {"success": False, "error": str(e)}

    async def deliver(self, message: NotificationMessage) -> dict:
        return await self.send(build_notification_email(self.to_address, message))

    async def test_connection(self) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "SMTP not configured"

        try:
            result = await self.send(
                EmailMessage(
                    to=self.to_address,
                    subject="Wardrowbe - Test Notification",
                    html_body="<p>This is a test email from Wardrowbe.</p>",
                    text_body="This is a test email from Wardrowbe.",
                )
            )
            if result.get("success"):
                return True, "Test email sent successfully"
            return False, result.get("error", "Unknown error")
        except Exception as e:
            return False, str(e)


# Expo Push Provider
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


@dataclass
class ExpoPushMessage:
    to: str
    title: str
    body: str
    data: dict | None = None
    sound: str = "default"
    badge: int | None = None
    channel_id: str = "outfit-suggestions"


class ExpoPushProvider:
    def __init__(self, config: ExpoPushConfig):
        self.push_token = config.push_token

    async def send(self, message: ExpoPushMessage) -> dict:
        payload = {
            "to": message.to or self.push_token,
            "title": message.title,
            "body": message.body,
            "sound": message.sound,
            "channelId": message.channel_id,
        }
        if message.data:
            payload["data"] = message.data
        if message.badge is not None:
            payload["badge"] = message.badge

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(
                    EXPO_PUSH_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    result = response.json()
                    ticket = result.get("data", {})
                    if ticket.get("status") == "ok":
                        return {"success": True, "ticket_id": ticket.get("id")}
                    else:
                        return {
                            "success": False,
                            "error": ticket.get("message", "Push send failed"),
                        }
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}",
                    }
        except Exception as e:
            logger.exception("Expo push send failed")
            return {"success": False, "error": str(e)}

    async def deliver(self, message: NotificationMessage) -> dict:
        return await self.send(
            ExpoPushMessage(
                to=self.push_token,
                title=message.title,
                body=message.short_body or message.body,
                data=message.data or None,
            )
        )

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.send(
                ExpoPushMessage(
                    to=self.push_token,
                    title="Wardrowbe Test",
                    body="Push notifications are working!",
                )
            )
            if result.get("success"):
                return True, "Test push notification sent successfully"
            return False, result.get("error", "Unknown error")
        except Exception as e:
            return False, str(e)


class NotificationProvider(Protocol):
    async def deliver(self, message: NotificationMessage) -> dict: ...

    async def test_connection(self) -> tuple[bool, str]: ...


@dataclass(frozen=True)
class ChannelSpec:
    config: type[BaseModel]
    provider: Callable[..., NotificationProvider]


CHANNELS: dict[NotificationChannel, ChannelSpec] = {
    NotificationChannel.ntfy: ChannelSpec(NtfyConfig, NtfyProvider),
    NotificationChannel.mattermost: ChannelSpec(MattermostConfig, MattermostProvider),
    NotificationChannel.email: ChannelSpec(EmailConfig, EmailProvider),
    NotificationChannel.expo_push: ChannelSpec(ExpoPushConfig, ExpoPushProvider),
}


def _channel_spec(channel: str) -> ChannelSpec:
    spec = CHANNELS.get(channel)
    if spec is None:
        raise ValueError(f"Unknown channel: {channel}")
    return spec


def parse_channel_config(channel: str, config: dict) -> BaseModel:
    return _channel_spec(channel).config(**config)


def build_provider(channel: str, config: dict) -> NotificationProvider:
    spec = _channel_spec(channel)
    return spec.provider(spec.config(**config))


@dataclass
class NotificationResult:
    channel: str
    status: NotificationStatus
    error: str | None = None
    response: dict | None = None


async def send_via_channel(
    setting: NotificationSettings, message: NotificationMessage
) -> NotificationResult:
    try:
        result = await build_provider(setting.channel, setting.config).deliver(message)
    except Exception as e:
        logger.exception("Failed to send via %s", setting.channel)
        return NotificationResult(
            channel=setting.channel, status=NotificationStatus.failed, error=str(e)
        )

    if result.get("success"):
        return NotificationResult(
            channel=setting.channel, status=NotificationStatus.sent, response=result
        )
    return NotificationResult(
        channel=setting.channel, status=NotificationStatus.failed, error=result.get("error")
    )


def _html_text(text: str) -> str:
    return "<br>".join(html.escape(line, quote=False) for line in text.split("\n"))


def _email_weather_html(weather: WeatherSummary | None) -> str:
    if weather is None:
        return ""
    temperature = "?" if weather.temperature is None else weather.temperature
    condition = html.escape(weather.condition or "Unknown", quote=False)
    forecast_note = " (forecast)" if weather.forecast else ""
    return f"""
    <p style="color: #6B7280; margin: 0;">
        {temperature}C, {condition}{forecast_note}
    </p>
    """


def _email_highlights_html(highlights: list[str]) -> str:
    if not highlights:
        return ""
    items_html = "".join(
        f'<li style="color: #4B5563; margin: 5px 0;">{html.escape(h, quote=False)}</li>'
        for h in highlights
    )
    return f"""
    <ul style="margin: 15px 0; padding-left: 20px;">
        {items_html}
    </ul>
    """


def _email_tip_html(tip: str | None) -> str:
    if not tip:
        return ""
    return f"""
    <div style="background: #F3F4F6; border-radius: 8px; padding: 12px; margin: 15px 0; border: 1px solid #E5E7EB;">
        <p style="color: #4B5563; margin: 0;">
            <strong style="color: #1F2937;">Tip:</strong> {html.escape(tip, quote=False)}
        </p>
    </div>
    """


def _email_cta_html(message: NotificationMessage) -> str:
    if not message.url:
        return ""
    return f"""
    <div style="text-align: center; margin: 30px 0;">
        <a href="{html.escape(message.url)}"
           style="background: #111827; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; display: inline-block; margin: 5px;">
            {html.escape(message.url_label, quote=False)}
        </a>
    </div>
    """


def _email_text(message: NotificationMessage) -> str:
    lead = message.lead if message.has_sections else message.body
    parts = [f"Wardrowbe - {message.full_heading}"]
    if lead:
        parts.append(lead)
    if message.highlights:
        parts.append("\n".join(f"- {h}" for h in message.highlights))
    if message.tip:
        parts.append(f"Tip: {message.tip}")
    if message.url:
        parts.append(f"{message.url_label}: {message.url}")
    return "\n\n".join(parts)


def build_notification_email(to: str, message: NotificationMessage) -> EmailMessage:
    settings_url = get_settings().app_link("/dashboard/notifications")
    lead = message.lead if message.has_sections else message.body
    lead_html = ""
    if lead:
        lead_html = f"""
        <p style="color: #1F2937; font-weight: 600; margin: 0 0 10px 0;">
            {_html_text(lead)}
        </p>"""
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #1F2937; margin: 0;">Wardrowbe</h1>
    </div>

    <div style="background: #F9FAFB; border-radius: 12px; padding: 20px; margin-bottom: 20px;">
        <h2 style="color: #1F2937; margin: 0 0 10px 0;">
            {html.escape(message.full_heading, quote=False)}
        </h2>
        {_email_weather_html(message.weather)}
    </div>

    <div style="background: #F3F4F6; border-radius: 8px; padding: 15px; margin: 20px 0;">{lead_html}
        {_email_highlights_html(message.highlights)}
    </div>

    {_email_tip_html(message.tip)}

    {_email_cta_html(message)}

    <div style="text-align: center; color: #9CA3AF; font-size: 12px; margin-top: 40px;">
        <p>Sent by Wardrowbe</p>
        <p>
            <a href="{html.escape(settings_url)}" style="color: #6B7280;">
                Manage notification settings
            </a>
        </p>
    </div>
</body>
</html>
"""
    return EmailMessage(
        to=to,
        subject=message.full_heading,
        html_body=html_body,
        text_body=_email_text(message),
    )


def build_family_invite_email(
    to: str,
    family_name: str,
    inviter_name: str,
    invite_token: str,
) -> EmailMessage:
    settings = get_settings()
    home_url = settings.app_link()
    invite_url = settings.app_link(f"/invite?token={invite_token}")
    subject = f"{inviter_name} invited you to join {family_name} on Wardrowbe"
    body_text = (
        f'{inviter_name} invited you to join the family "{family_name}" on Wardrowbe. '
        f"Click here to accept: {invite_url}"
    )
    html_body = f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #111827;">You&rsquo;re invited!</h2>
    <p style="color: #374151; line-height: 1.6;">
        <strong>{html.escape(inviter_name)}</strong> invited you to join the family
        <strong>{html.escape(family_name)}</strong> on Wardrowbe.
    </p>
    <div style="text-align: center; margin: 30px 0;">
        <a href="{html.escape(invite_url)}"
           style="background: #111827; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; display: inline-block;">
            Accept Invitation
        </a>
    </div>
    <p style="color: #9CA3AF; font-size: 13px;">
        If you don&rsquo;t have a Wardrowbe account yet, you&rsquo;ll be asked to create one first.
    </p>
    <hr style="border: none; border-top: 1px solid #E5E7EB; margin: 20px 0;">
    <p style="color: #9CA3AF; font-size: 12px;">Sent by <a href="{html.escape(home_url)}" style="color: #9CA3AF;">Wardrowbe</a></p>
</div>"""
    return EmailMessage(to=to, subject=subject, html_body=html_body, text_body=body_text)
