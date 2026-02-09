import logging
import os
from dataclasses import dataclass, field

import httpx

from app.schemas.notification import EmailConfig, ExpoPushConfig, MattermostConfig, NtfyConfig

logger = logging.getLogger(__name__)


# ntfy Provider
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
            "Title": notification.title,
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.server}/{notification.topic or self.topic}",
                    headers=headers,
                    content=notification.message,
                )

                if response.status_code == 200:
                    return {"success": True, "response": response.json()}
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}",
                    }
        except Exception as e:
            logger.exception("ntfy send failed")
            return {"success": False, "error": str(e)}

    async def test_connection(self) -> bool:
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
            return result.get("success", False)
        except Exception:
            return False


# Mattermost Provider
@dataclass
class MattermostAttachment:
    title: str
    text: str = ""
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.webhook_url, json=payload)

                if response.status_code == 200:
                    return {"success": True}
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}",
                    }
        except Exception as e:
            logger.exception("Mattermost send failed")
            return {"success": False, "error": str(e)}

    async def test_connection(self) -> bool:
        try:
            result = await self.send(
                MattermostMessage(text="This is a test message from Wardrowbe.")
            )
            return result.get("success", False)
        except Exception:
            return False


# Email Provider
@dataclass
class EmailMessage:
    to: str
    subject: str
    html_body: str
    text_body: str = ""


class EmailProvider:
    def __init__(self, config: EmailConfig):
        self.to_address = config.address
        self.smtp_host = os.getenv("SMTP_HOST")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
        self.from_name = os.getenv("SMTP_FROM_NAME", "Wardrowbe")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)

    def is_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user)

    async def send(self, message: EmailMessage) -> dict:
        if not self.is_configured():
            return {"success": False, "error": "SMTP not configured"}

        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            import aiosmtplib

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
        except ImportError:
            return {"success": False, "error": "aiosmtplib not installed"}
        except Exception as e:
            logger.exception("Email send failed")
            return {"success": False, "error": str(e)}

    async def test_connection(self) -> bool:
        if not self.is_configured():
            return False

        try:
            result = await self.send(
                EmailMessage(
                    to=self.to_address,
                    subject="Wardrowbe - Test Notification",
                    html_body="<p>This is a test email from Wardrowbe.</p>",
                    text_body="This is a test email from Wardrowbe.",
                )
            )
            return result.get("success", False)
        except Exception:
            return False


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
            async with httpx.AsyncClient(timeout=30.0) as client:
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

    async def test_connection(self) -> bool:
        try:
            result = await self.send(
                ExpoPushMessage(
                    to=self.push_token,
                    title="Wardrowbe Test",
                    body="Push notifications are working!",
                )
            )
            return result.get("success", False)
        except Exception:
            return False
