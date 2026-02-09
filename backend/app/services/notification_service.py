import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.notification import Notification, NotificationSettings, NotificationStatus
from app.models.outfit import Outfit, OutfitItem
from app.models.user import User
from app.schemas.notification import EmailConfig, ExpoPushConfig, MattermostConfig, NtfyConfig
from app.services.notification_providers import (
    EmailMessage,
    EmailProvider,
    ExpoPushMessage,
    ExpoPushProvider,
    MattermostAttachment,
    MattermostMessage,
    MattermostProvider,
    NtfyNotification,
    NtfyProvider,
)

logger = logging.getLogger(__name__)


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class NotificationResult:
    channel: str
    status: DeliveryStatus
    error: str | None = None
    response: dict | None = None


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Notification Settings CRUD
    async def get_user_settings(self, user_id: UUID) -> list[NotificationSettings]:
        result = await self.db.execute(
            select(NotificationSettings)
            .where(NotificationSettings.user_id == user_id)
            .order_by(NotificationSettings.priority)
        )
        return list(result.scalars().all())

    async def get_setting_by_id(
        self, setting_id: UUID, user_id: UUID
    ) -> NotificationSettings | None:
        result = await self.db.execute(
            select(NotificationSettings).where(
                and_(
                    NotificationSettings.id == setting_id,
                    NotificationSettings.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create_setting(
        self, user_id: UUID, channel: str, enabled: bool, priority: int, config: dict
    ) -> NotificationSettings:
        # Check if channel already exists
        existing = await self.db.execute(
            select(NotificationSettings).where(
                and_(
                    NotificationSettings.user_id == user_id,
                    NotificationSettings.channel == channel,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Channel {channel} already configured")

        setting = NotificationSettings(
            user_id=user_id,
            channel=channel,
            enabled=enabled,
            priority=priority,
            config=config,
        )
        self.db.add(setting)
        await self.db.flush()
        await self.db.refresh(setting)
        return setting

    async def update_setting(
        self,
        setting_id: UUID,
        user_id: UUID,
        enabled: bool | None = None,
        priority: int | None = None,
        config: dict | None = None,
    ) -> NotificationSettings | None:
        setting = await self.get_setting_by_id(setting_id, user_id)
        if not setting:
            return None

        if enabled is not None:
            setting.enabled = enabled
        if priority is not None:
            setting.priority = priority
        if config is not None:
            setting.config = config

        await self.db.flush()
        await self.db.refresh(setting)
        return setting

    async def delete_setting(self, setting_id: UUID, user_id: UUID) -> bool:
        setting = await self.get_setting_by_id(setting_id, user_id)
        if not setting:
            return False

        await self.db.delete(setting)
        await self.db.flush()
        return True

    async def test_setting(self, setting_id: UUID, user_id: UUID) -> tuple[bool, str]:
        setting = await self.get_setting_by_id(setting_id, user_id)
        if not setting:
            return False, "Setting not found"

        try:
            if setting.channel == "ntfy":
                provider = NtfyProvider(NtfyConfig(**setting.config))
                success = await provider.test_connection()
            elif setting.channel == "mattermost":
                provider = MattermostProvider(MattermostConfig(**setting.config))
                success = await provider.test_connection()
            elif setting.channel == "email":
                provider = EmailProvider(EmailConfig(**setting.config))
                success = await provider.test_connection()
            elif setting.channel == "expo_push":
                provider = ExpoPushProvider(ExpoPushConfig(**setting.config))
                success = await provider.test_connection()
            else:
                return False, f"Unknown channel: {setting.channel}"

            if success:
                return True, "Test notification sent successfully"
            else:
                return False, "Failed to send test notification"
        except Exception as e:
            return False, str(e)


class NotificationDispatcher:
    def __init__(self, db: AsyncSession, app_url: str):
        self.db = db
        self.app_url = app_url.rstrip("/")

    async def send_outfit_notification(
        self, user_id: UUID, outfit_id: UUID, for_tomorrow: bool = False
    ) -> list[NotificationResult]:
        # Get user
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        # Get outfit with items loaded
        outfit_result = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == outfit_id)
            .options(selectinload(Outfit.items).selectinload(OutfitItem.item))
        )
        outfit = outfit_result.scalar_one_or_none()
        if not outfit:
            raise ValueError("Outfit not found")

        # Get enabled channels sorted by priority
        channels_result = await self.db.execute(
            select(NotificationSettings)
            .where(
                and_(
                    NotificationSettings.user_id == user_id,
                    NotificationSettings.enabled,
                )
            )
            .order_by(NotificationSettings.priority)
        )
        channels = list(channels_result.scalars().all())

        if not channels:
            return [
                NotificationResult(
                    channel="none",
                    status=DeliveryStatus.FAILED,
                    error="No notification channels configured",
                )
            ]

        results = []
        success = False

        for channel_config in channels:
            if success:
                break

            result = await self._send_via_channel(channel_config, outfit, user, for_tomorrow)
            results.append(result)

            if result.status == DeliveryStatus.SENT:
                success = True

                # Record notification
                notification = Notification(
                    user_id=user_id,
                    outfit_id=outfit_id,
                    channel=channel_config.channel,
                    status=NotificationStatus.sent,
                    payload={"occasion": outfit.occasion},
                    sent_at=datetime.now(UTC),
                )
                self.db.add(notification)

                # Update outfit status
                outfit.sent_at = datetime.now(UTC)
                outfit.status = "sent"

                await self.db.flush()

        if not success:
            # Record failed notification for retry
            notification = Notification(
                user_id=user_id,
                outfit_id=outfit_id,
                channel=channels[0].channel if channels else "unknown",
                status=NotificationStatus.retrying,
                payload={"occasion": outfit.occasion},
                attempts=1,
                last_attempt_at=datetime.now(UTC),
                error_message=results[-1].error if results else "Unknown error",
            )
            self.db.add(notification)
            await self.db.flush()

        return results

    async def retry_notification(self, notification: Notification) -> NotificationResult:
        # Get user
        user_result = await self.db.execute(select(User).where(User.id == notification.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return NotificationResult(
                channel=notification.channel,
                status=DeliveryStatus.FAILED,
                error="User not found",
            )

        # Get outfit with items loaded
        outfit_result = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == notification.outfit_id)
            .options(selectinload(Outfit.items).selectinload(OutfitItem.item))
        )
        outfit = outfit_result.scalar_one_or_none()
        if not outfit:
            return NotificationResult(
                channel=notification.channel,
                status=DeliveryStatus.FAILED,
                error="Outfit not found",
            )

        # Get the channel config for this notification's channel
        channel_result = await self.db.execute(
            select(NotificationSettings).where(
                and_(
                    NotificationSettings.user_id == notification.user_id,
                    NotificationSettings.channel == notification.channel,
                    NotificationSettings.enabled,
                )
            )
        )
        channel_config = channel_result.scalar_one_or_none()
        if not channel_config:
            return NotificationResult(
                channel=notification.channel,
                status=DeliveryStatus.FAILED,
                error=f"Channel {notification.channel} not configured or disabled",
            )

        # Attempt to send
        return await self._send_via_channel(channel_config, outfit, user)

    async def _send_via_channel(
        self,
        channel_config: NotificationSettings,
        outfit: Outfit,
        user: User,
        for_tomorrow: bool = False,
    ) -> NotificationResult:
        try:
            if channel_config.channel == "ntfy":
                provider = NtfyProvider(NtfyConfig(**channel_config.config))
                message = self._build_ntfy_notification(outfit, user, for_tomorrow)
                result = await provider.send(message)

            elif channel_config.channel == "mattermost":
                provider = MattermostProvider(MattermostConfig(**channel_config.config))
                message = self._build_mattermost_message(outfit, user, for_tomorrow)
                result = await provider.send(message)

            elif channel_config.channel == "email":
                provider = EmailProvider(EmailConfig(**channel_config.config))
                message = self._build_email_message(outfit, user, for_tomorrow)
                result = await provider.send(message)

            elif channel_config.channel == "expo_push":
                provider = ExpoPushProvider(ExpoPushConfig(**channel_config.config))
                message = self._build_expo_push_message(outfit, user, for_tomorrow)
                result = await provider.send(message)

            else:
                return NotificationResult(
                    channel=channel_config.channel,
                    status=DeliveryStatus.FAILED,
                    error=f"Unknown channel: {channel_config.channel}",
                )

            if result.get("success"):
                return NotificationResult(
                    channel=channel_config.channel,
                    status=DeliveryStatus.SENT,
                    response=result,
                )
            else:
                return NotificationResult(
                    channel=channel_config.channel,
                    status=DeliveryStatus.FAILED,
                    error=result.get("error"),
                )

        except Exception as e:
            logger.exception(f"Failed to send via {channel_config.channel}")
            return NotificationResult(
                channel=channel_config.channel,
                status=DeliveryStatus.FAILED,
                error=str(e),
            )

    def _build_ntfy_notification(
        self, outfit: Outfit, user: User, for_tomorrow: bool = False
    ) -> NtfyNotification:
        # Weather info for title
        weather = outfit.weather_data or {}
        temp = weather.get("temperature")
        condition = weather.get("condition", "").lower()

        # Day prefix for messages
        day_label = "Tomorrow" if for_tomorrow else "Today"

        # Build title with weather (ASCII-safe for HTTP headers)
        if temp is not None:
            title = f"{day_label}'s {outfit.occasion.title()} - {temp}C"
        else:
            title = f"{day_label}'s {outfit.occasion.title()} Outfit"

        # Build message body with structured data
        parts = []

        # Add headline if available (stored in reasoning field)
        if outfit.reasoning:
            parts.append(outfit.reasoning)

        # Add highlights from ai_raw_response if available
        highlights = []
        if outfit.ai_raw_response and isinstance(outfit.ai_raw_response, dict):
            highlights = outfit.ai_raw_response.get("highlights", [])

        if highlights and isinstance(highlights, list):
            # Format highlights as bullet points
            highlight_lines = [f"* {h}" for h in highlights[:3]]  # Limit to 3
            parts.append("\n".join(highlight_lines))

        # Add styling tip if available
        if outfit.style_notes:
            parts.append(f"Tip: {outfit.style_notes}")

        message = "\n\n".join(parts) if parts else "Your outfit is ready."

        # Choose a single contextual tag based on weather
        tag = "shirt"  # default
        if condition:
            if any(w in condition for w in ["rain", "drizzle", "shower"]):
                tag = "umbrella"
            elif any(w in condition for w in ["sun", "clear"]):
                tag = "sunny"
            elif any(w in condition for w in ["cloud", "overcast"]):
                tag = "cloud"
            elif any(w in condition for w in ["snow", "sleet"]):
                tag = "snowflake"
            elif any(w in condition for w in ["wind"]):
                tag = "wind_face"

        return NtfyNotification(
            topic="",  # Will be set by provider
            title=title,
            message=message,
            tags=[tag],
            priority=3,
            click=f"{self.app_url}/dashboard/history",
        )

    def _build_mattermost_message(
        self, outfit: Outfit, user: User, for_tomorrow: bool = False
    ) -> MattermostMessage:
        weather_text = ""
        if outfit.weather_data:
            weather = outfit.weather_data
            weather_text = f" | {weather.get('temperature', '?')}C {weather.get('condition', '')}"

        day_label = "Tomorrow" if for_tomorrow else "Today"
        greeting = "Good evening" if for_tomorrow else "Good morning"

        # Build message text with structured data
        text_parts = []

        # Add headline (stored in reasoning)
        if outfit.reasoning:
            text_parts.append(f"**{outfit.reasoning}**")

        # Add highlights from ai_raw_response as markdown list
        highlights = []
        if outfit.ai_raw_response and isinstance(outfit.ai_raw_response, dict):
            highlights = outfit.ai_raw_response.get("highlights", [])

        if highlights and isinstance(highlights, list):
            highlight_lines = [f"- {h}" for h in highlights[:3]]
            text_parts.append("\n".join(highlight_lines))

        # Add styling tip
        if outfit.style_notes:
            text_parts.append(f"_Tip: {outfit.style_notes}_")

        attachment_text = "\n\n".join(text_parts) if text_parts else "Your outfit is ready!"

        attachment = MattermostAttachment(
            title=f"{day_label}'s Outfit: {outfit.occasion.title()}{weather_text}",
            text=attachment_text,
            color="#3B82F6",
        )

        return MattermostMessage(
            text=f"{greeting}, {user.display_name}! Here's your outfit suggestion for {day_label.lower()}:",
            attachments=[attachment],
        )

    def _build_email_message(
        self, outfit: Outfit, user: User, for_tomorrow: bool = False
    ) -> EmailMessage:
        weather_html = ""
        if outfit.weather_data:
            weather = outfit.weather_data
            forecast_note = " (forecast)" if for_tomorrow else ""
            weather_html = f"""
            <p style="color: #6B7280; margin: 0;">
                {weather.get("temperature", "?")}C, {weather.get("condition", "Unknown")}{forecast_note}
            </p>
            """

        day_label = "Tomorrow" if for_tomorrow else "Today"

        # Build highlights HTML
        highlights_html = ""
        highlights = []
        if outfit.ai_raw_response and isinstance(outfit.ai_raw_response, dict):
            highlights = outfit.ai_raw_response.get("highlights", [])

        if highlights and isinstance(highlights, list):
            items_html = "".join(
                f'<li style="color: #4B5563; margin: 5px 0;">{h}</li>' for h in highlights[:3]
            )
            highlights_html = f"""
            <ul style="margin: 15px 0; padding-left: 20px;">
                {items_html}
            </ul>
            """

        # Build styling tip HTML
        styling_tip_html = ""
        if outfit.style_notes:
            styling_tip_html = f"""
            <div style="background: #F3F4F6; border-radius: 8px; padding: 12px; margin: 15px 0; border: 1px solid #E5E7EB;">
                <p style="color: #4B5563; margin: 0;">
                    <strong style="color: #1F2937;">Tip:</strong> {outfit.style_notes}
                </p>
            </div>
            """

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
                    {day_label}'s Outfit: {outfit.occasion.title()}
                </h2>
                {weather_html}
            </div>

            <div style="background: #F3F4F6; border-radius: 8px; padding: 15px; margin: 20px 0;">
                <p style="color: #1F2937; font-weight: 600; margin: 0 0 10px 0;">
                    {outfit.reasoning or "Your outfit is ready!"}
                </p>
                {highlights_html}
            </div>

            {styling_tip_html}

            <div style="text-align: center; margin: 30px 0;">
                <a href="{self.app_url}/dashboard/history"
                   style="background: #3B82F6; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; display: inline-block; margin: 5px;">
                    View Outfit
                </a>
            </div>

            <div style="text-align: center; color: #9CA3AF; font-size: 12px; margin-top: 40px;">
                <p>Sent by Wardrowbe</p>
                <p>
                    <a href="{self.app_url}/dashboard/notifications" style="color: #6B7280;">
                        Manage notification settings
                    </a>
                </p>
            </div>
        </body>
        </html>
        """

        # Build text body with highlights
        text_parts = [
            f"Wardrowbe - {day_label}'s Outfit",
            "",
            f"Occasion: {outfit.occasion.title()}",
            "",
            outfit.reasoning or "Your outfit is ready!",
        ]

        if highlights:
            text_parts.append("")
            for h in highlights[:3]:
                text_parts.append(f"- {h}")

        if outfit.style_notes:
            text_parts.append("")
            text_parts.append(f"Tip: {outfit.style_notes}")

        text_parts.append("")
        text_parts.append(f"View outfit: {self.app_url}/dashboard/history")

        text_body = "\n".join(text_parts)

        return EmailMessage(
            to=user.email,
            subject=f"{day_label}'s Outfit: {outfit.occasion.title()}",
            html_body=html_body,
            text_body=text_body,
        )

    def _build_expo_push_message(
        self, outfit: Outfit, user: User, for_tomorrow: bool = False
    ) -> ExpoPushMessage:
        weather = outfit.weather_data or {}
        temp = weather.get("temperature")
        day_label = "Tomorrow" if for_tomorrow else "Today"

        if temp is not None:
            title = f"{day_label}'s {outfit.occasion.title()} - {temp}\u00b0C"
        else:
            title = f"{day_label}'s {outfit.occasion.title()} Outfit"

        parts = []
        if outfit.reasoning:
            parts.append(outfit.reasoning)
        if outfit.style_notes:
            parts.append(f"Tip: {outfit.style_notes}")

        body = " \u2022 ".join(parts) if parts else "Your outfit is ready!"

        return ExpoPushMessage(
            to="",  # Provider uses its stored token
            title=title,
            body=body,
            data={"outfit_id": str(outfit.id), "screen": "history"},
        )
