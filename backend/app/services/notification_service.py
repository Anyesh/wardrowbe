import logging
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func, literal, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.config import get_settings
from app.models.notification import Notification, NotificationSettings, NotificationStatus
from app.models.outfit import Outfit, OutfitItem, OutfitStatus
from app.models.schedule import Schedule
from app.models.user import User
from app.schemas.notification import NotificationChannel
from app.services.notification_providers import (
    NotificationMessage,
    NotificationResult,
    WeatherSummary,
    build_provider,
    format_temperature,
    send_via_channel,
)
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)

# A row written by another version (a channel since removed, or one added later) has no provider
# here, so it is neither listed nor sent to.
KNOWN_CHANNEL = NotificationSettings.channel.in_([channel.value for channel in NotificationChannel])

WEATHER_TAGS = (
    (("rain", "drizzle", "shower"), "umbrella"),
    (("sun", "clear"), "sunny"),
    (("cloud", "overcast"), "cloud"),
    (("snow", "sleet"), "snowflake"),
    (("wind",), "wind_face"),
)


# Returns the title word and the mid-sentence form, because a weekday stays capitalised
# mid-sentence while today and tomorrow do not.
def _outfit_day(scheduled_for: date | None, today: date) -> tuple[str, str]:
    if scheduled_for is None or scheduled_for == today:
        return "Today", "today"
    if scheduled_for == today + timedelta(days=1):
        return "Tomorrow", "tomorrow"
    weekday = scheduled_for.strftime("%A")
    return weekday, weekday


class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Notification Settings CRUD
    async def get_user_settings(self, user_id: UUID) -> list[NotificationSettings]:
        result = await self.db.execute(
            select(NotificationSettings)
            .where(NotificationSettings.user_id == user_id, KNOWN_CHANNEL)
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
                    KNOWN_CHANNEL,
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

    async def test_setting(self, setting: NotificationSettings) -> tuple[bool, str]:
        try:
            return await build_provider(setting.channel, setting.config).test_connection()
        except Exception as e:
            return False, str(e)

    async def get_user_schedules(self, user_id: UUID) -> list[Schedule]:
        result = await self.db.execute(select(Schedule).where(Schedule.user_id == user_id))
        return list(result.scalars().all())

    async def get_schedule_by_id(self, schedule_id: UUID, user_id: UUID) -> Schedule | None:
        result = await self.db.execute(
            select(Schedule).where(and_(Schedule.id == schedule_id, Schedule.user_id == user_id))
        )
        return result.scalar_one_or_none()

    async def create_schedule(
        self,
        user_id: UUID,
        day_of_week: int,
        notification_time: time,
        occasion: str,
        enabled: bool,
        notify_day_before: bool,
    ) -> Schedule:
        existing = await self.db.execute(
            select(Schedule).where(
                and_(
                    Schedule.user_id == user_id,
                    Schedule.day_of_week == day_of_week,
                    Schedule.notification_time == notification_time,
                    Schedule.occasion == occasion,
                    Schedule.notify_day_before == notify_day_before,
                )
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("An identical schedule already exists")

        schedule = Schedule(
            user_id=user_id,
            day_of_week=day_of_week,
            notification_time=notification_time,
            occasion=occasion,
            enabled=enabled,
            notify_day_before=notify_day_before,
        )
        self.db.add(schedule)
        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule

    async def update_schedule(
        self,
        schedule_id: UUID,
        user_id: UUID,
        day_of_week: int | None = None,
        notification_time: time | None = None,
        occasion: str | None = None,
        enabled: bool | None = None,
        notify_day_before: bool | None = None,
    ) -> Schedule | None:
        schedule = await self.get_schedule_by_id(schedule_id, user_id)
        if not schedule:
            return None

        if day_of_week is not None:
            schedule.day_of_week = day_of_week
        if notification_time is not None:
            schedule.notification_time = notification_time
        if occasion is not None:
            schedule.occasion = occasion
        if enabled is not None:
            schedule.enabled = enabled
        if notify_day_before is not None:
            schedule.notify_day_before = notify_day_before

        await self.db.flush()
        await self.db.refresh(schedule)
        return schedule

    async def delete_schedule(self, schedule_id: UUID, user_id: UUID) -> bool:
        schedule = await self.get_schedule_by_id(schedule_id, user_id)
        if not schedule:
            return False

        await self.db.delete(schedule)
        await self.db.flush()
        return True


class NotificationDispatcher:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def enabled_channels(self, user_id: UUID | str) -> list[NotificationSettings]:
        result = await self.db.execute(
            select(NotificationSettings)
            .where(
                and_(
                    NotificationSettings.user_id == user_id,
                    NotificationSettings.enabled == True,  # noqa: E712
                    KNOWN_CHANNEL,
                )
            )
            .order_by(NotificationSettings.priority)
        )
        return list(result.scalars().all())

    async def deliver(
        self, user_id: UUID | str, message: NotificationMessage
    ) -> list[NotificationResult]:
        results = []
        for channel in await self.enabled_channels(user_id):
            result = await send_via_channel(channel, message)
            results.append(result)
            if result.status == NotificationStatus.sent:
                break
        return results

    # Every attempt is kept with its own channel's error, including the failures a fallback
    # channel then covered, so the history shows why a higher-priority channel was skipped.
    def record_attempts(
        self,
        user_id: UUID | str,
        results: list[NotificationResult],
        payload: dict,
        outfit_id: UUID | None = None,
    ) -> list[Notification]:
        now = datetime.now(UTC)
        rows = [
            Notification(
                user_id=user_id,
                outfit_id=outfit_id,
                channel=result.channel,
                status=result.status,
                payload=payload,
                sent_at=now if result.status == NotificationStatus.sent else None,
                error_message=result.error,
            )
            for result in results
        ]
        self.db.add_all(rows)
        return rows

    async def send_outfit_notification(
        self, user_id: UUID, outfit_id: UUID
    ) -> list[NotificationResult]:
        user_result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active.is_(True))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        outfit_result = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == outfit_id)
            .options(selectinload(Outfit.items).selectinload(OutfitItem.item))
        )
        outfit = outfit_result.scalar_one_or_none()
        if not outfit:
            raise ValueError("Outfit not found")

        results = await self.deliver(user_id, self._build_outfit_message(outfit, user))
        if not results:
            return [
                NotificationResult(
                    channel="none",
                    status=NotificationStatus.failed,
                    error="No notification channels configured",
                )
            ]

        rows = self.record_attempts(
            user_id, results, {"occasion": outfit.occasion}, outfit_id=outfit_id
        )
        if results[-1].status == NotificationStatus.sent:
            await self._mark_outfit_sent(outfit, rows[-1].sent_at)
        else:
            # Only one row is retried, so that the retry job sends the outfit at most once rather
            # than once per failed channel.
            retry = next((r for r, res in zip(rows, results, strict=True) if res.retryable), None)
            if retry is not None:
                retry.status = NotificationStatus.retrying
                retry.attempts = 1
                retry.last_attempt_at = datetime.now(UTC)
        await self.db.flush()

        return results

    # A send can land after the user accepted, rejected or skipped the outfit, also while it was in
    # flight, so the row decides rather than the loaded object, which may be stale: only a pending
    # outfit moves to sent, because overwriting the verdict would drop it from learning and
    # analytics. The loaded object takes the row's values so a later flush cannot write it back.
    async def _mark_outfit_sent(self, outfit: Outfit, sent_at: datetime) -> None:
        result = await self.db.execute(
            update(Outfit)
            .where(Outfit.id == outfit.id)
            .values(
                status=case(
                    (
                        Outfit.status == OutfitStatus.pending,
                        literal(OutfitStatus.sent, Outfit.status.type),
                    ),
                    else_=Outfit.status,
                ),
                sent_at=func.coalesce(Outfit.sent_at, sent_at),
            )
            .returning(Outfit.status, Outfit.sent_at)
            .execution_options(synchronize_session=False)
        )
        stored = result.one_or_none()
        if stored is not None:
            set_committed_value(outfit, "status", stored.status)
            set_committed_value(outfit, "sent_at", stored.sent_at)

    async def retry_notification(self, notification: Notification) -> NotificationResult:
        user_result = await self.db.execute(
            select(User).where(User.id == notification.user_id, User.is_active.is_(True))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            return NotificationResult(
                channel=notification.channel,
                status=NotificationStatus.failed,
                error="User not found",
                retryable=False,
            )

        outfit_result = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == notification.outfit_id)
            .options(selectinload(Outfit.items).selectinload(OutfitItem.item))
        )
        outfit = outfit_result.scalar_one_or_none()
        if not outfit:
            return NotificationResult(
                channel=notification.channel,
                status=NotificationStatus.failed,
                error="Outfit not found",
                retryable=False,
            )

        channel_result = await self.db.execute(
            select(NotificationSettings).where(
                and_(
                    NotificationSettings.user_id == notification.user_id,
                    NotificationSettings.channel == notification.channel,
                    NotificationSettings.enabled == True,  # noqa: E712
                )
            )
        )
        channel_config = channel_result.scalar_one_or_none()
        if not channel_config:
            return NotificationResult(
                channel=notification.channel,
                status=NotificationStatus.failed,
                error=f"Channel {notification.channel} not configured or disabled",
                retryable=False,
            )

        result = await send_via_channel(channel_config, self._build_outfit_message(outfit, user))
        if result.status == NotificationStatus.sent:
            await self._mark_outfit_sent(outfit, datetime.now(UTC))
        return result

    # The day is derived at send time from the outfit's date rather than stored, so a retry that
    # lands after the user's midnight still names the outfit's day correctly.
    def _build_outfit_message(self, outfit: Outfit, user: User) -> NotificationMessage:
        today = get_user_today(user)
        for_tomorrow = outfit.scheduled_for == today + timedelta(days=1)
        day_label, day_phrase = _outfit_day(outfit.scheduled_for, today)
        weather = outfit.weather_data or {}
        temp = weather.get("temperature")
        condition = weather.get("condition")
        # "Date" alone reads as a calendar date, so the title always names the occasion's outfit.
        occasion = outfit.occasion.replace("-", " ").title()
        title = f"{day_label}'s {occasion} Outfit"
        if temp is not None:
            title = f"{title} - {format_temperature(temp)}"

        highlights = []
        if isinstance(outfit.ai_raw_response, dict):
            highlights = outfit.ai_raw_response.get("highlights", [])
        if not isinstance(highlights, list):
            highlights = []
        highlights = [str(h) for h in highlights[:3]]

        tip_line = f"Tip: {outfit.style_notes}" if outfit.style_notes else None
        highlight_lines = "\n".join(f"* {h}" for h in highlights) or None
        body_parts = list(filter(None, [outfit.reasoning, highlight_lines, tip_line]))
        short_parts = list(filter(None, [outfit.reasoning, tip_line]))

        greeting = "Good evening" if for_tomorrow else "Good morning"
        lowered = str(condition or "").lower()
        tag = next(
            (tag for words, tag in WEATHER_TAGS if any(w in lowered for w in words)),
            "shirt",
        )

        return NotificationMessage(
            title=title,
            body="\n\n".join(body_parts) if body_parts else "Your outfit is ready.",
            short_body=" \u2022 ".join(short_parts) if short_parts else "Your outfit is ready!",
            heading=f"{day_label}'s Outfit: {occasion}",
            greeting=(
                f"{greeting}, {user.display_name}! Here's your outfit suggestion for {day_phrase}:"
            ),
            weather=(
                WeatherSummary(
                    temperature=temp,
                    condition=str(condition) if condition is not None else None,
                    forecast=for_tomorrow,
                )
                if outfit.weather_data
                else None
            ),
            lead=outfit.reasoning,
            highlights=highlights,
            tip=outfit.style_notes,
            url=self.settings.app_link("/dashboard/history"),
            url_label="View Outfit",
            tags=[tag],
            data={"outfit_id": str(outfit.id), "screen": "history"},
        )
