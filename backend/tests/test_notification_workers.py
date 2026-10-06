"""Tests for notification worker concurrency fixes."""

import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.item import ClothingItem
from app.models.notification import Notification, NotificationSettings, NotificationStatus
from app.models.outfit import Outfit, OutfitSource, OutfitStatus
from app.models.schedule import Schedule
from app.models.user import User
from app.services.notification_providers import EXPO_PUSH_URL
from app.workers.notifications import (
    _check_wash_reminders_inner,
    check_scheduled_notifications,
    process_scheduled_notification,
    wash_reminder_message,
)
from app.workers.worker import WorkerSettings


@pytest_asyncio.fixture(autouse=True)
async def clean_schedules(db_session: AsyncSession):
    await db_session.execute(delete(Schedule))
    await db_session.commit()


@pytest_asyncio.fixture
async def schedule_user(db_session: AsyncSession) -> User:
    unique_id = uuid.uuid4()
    user = User(
        id=unique_id,
        external_id=f"sched-user-{unique_id}",
        email=f"sched-{unique_id}@example.com",
        display_name="Schedule User",
        timezone="UTC",
        is_active=True,
        onboarding_completed=True,
        location_lat=Decimal("40.71427800"),
        location_lon=Decimal("-74.00597200"),
        location_name="New York",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def ntfy_channel(db_session: AsyncSession, schedule_user: User) -> NotificationSettings:
    channel = NotificationSettings(
        user_id=schedule_user.id,
        channel="ntfy",
        enabled=True,
        config={"server": "https://ntfy.sh", "topic": "test-topic"},
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return channel


def _make_due_schedule(
    user: User,
    *,
    offset_minutes: int = 0,
    last_triggered_at: datetime | None = None,
    notify_day_before: bool = False,
) -> Schedule:
    now = datetime.now(UTC)
    target = now + timedelta(minutes=offset_minutes)
    day = now.weekday() if not notify_day_before else (now.weekday() + 1) % 7
    return Schedule(
        id=uuid.uuid4(),
        user_id=user.id,
        day_of_week=day,
        notification_time=time(target.hour, target.minute),
        occasion="casual",
        enabled=True,
        notify_day_before=notify_day_before,
        last_triggered_at=last_triggered_at,
    )


# ── check_scheduled_notifications ──


class TestCheckScheduledNotifications:
    @pytest.mark.asyncio
    async def test_due_schedule_gets_marked_and_enqueued(
        self, db_session: AsyncSession, schedule_user: User
    ):
        schedule = _make_due_schedule(schedule_user)
        db_session.add(schedule)
        await db_session.commit()

        enqueue_mock = AsyncMock()
        ctx = {"redis": MagicMock(enqueue_job=enqueue_mock)}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await check_scheduled_notifications(ctx)

        assert result["enqueued"] == 1
        enqueue_mock.assert_called_once()
        call_args = enqueue_mock.call_args
        assert call_args.args == ("process_scheduled_notification", str(schedule.id))
        assert call_args.kwargs["_queue_name"] == "arq:tagging"
        assert call_args.kwargs["_job_id"].startswith(f"sched:{schedule.id}:")
        await db_session.refresh(schedule)
        assert schedule.last_triggered_at is not None

    @pytest.mark.asyncio
    async def test_bad_stored_timezone_matches_schedule_as_utc(
        self, db_session: AsyncSession, schedule_user: User
    ):
        schedule_user.timezone = "Mars/Olympus_Mons"
        schedule = _make_due_schedule(schedule_user)
        db_session.add(schedule)
        await db_session.commit()

        ctx = {"redis": MagicMock(enqueue_job=AsyncMock())}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await check_scheduled_notifications(ctx)

        assert result["enqueued"] == 1

    @pytest.mark.asyncio
    async def test_recently_triggered_schedule_is_skipped(
        self, db_session: AsyncSession, schedule_user: User
    ):
        schedule = _make_due_schedule(
            schedule_user,
            last_triggered_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        db_session.add(schedule)
        await db_session.commit()

        ctx = {"redis": MagicMock(enqueue_job=AsyncMock())}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await check_scheduled_notifications(ctx)

        assert result["enqueued"] == 0

    @pytest.mark.asyncio
    async def test_schedule_outside_time_window_is_skipped(
        self, db_session: AsyncSession, schedule_user: User
    ):
        schedule = _make_due_schedule(schedule_user, offset_minutes=30)
        db_session.add(schedule)
        await db_session.commit()

        ctx = {"redis": MagicMock(enqueue_job=AsyncMock())}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await check_scheduled_notifications(ctx)

        assert result["enqueued"] == 0

    @pytest.mark.asyncio
    async def test_multiple_due_schedules_all_committed_before_enqueue(
        self, db_session: AsyncSession, schedule_user: User
    ):
        s1 = _make_due_schedule(schedule_user)
        s2 = _make_due_schedule(schedule_user)
        s2.occasion = "work"
        db_session.add_all([s1, s2])
        await db_session.commit()

        call_order: list[str] = []
        original_commit = db_session.commit

        async def tracking_commit():
            call_order.append("commit")
            await original_commit()

        enqueue_mock = AsyncMock(side_effect=lambda *a, **kw: call_order.append("enqueue"))
        ctx = {"redis": MagicMock(enqueue_job=enqueue_mock)}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch.object(db_session, "commit", side_effect=tracking_commit),
        ):
            result = await check_scheduled_notifications(ctx)

        assert result["enqueued"] == 2
        # commit happens before any enqueue
        assert call_order.index("commit") < call_order.index("enqueue")

    @pytest.mark.asyncio
    async def test_enqueue_failure_does_not_rollback_last_triggered_at(
        self, db_session: AsyncSession, schedule_user: User
    ):
        schedule = _make_due_schedule(schedule_user)
        db_session.add(schedule)
        await db_session.commit()

        enqueue_mock = AsyncMock(side_effect=ConnectionError("redis down"))
        ctx = {"redis": MagicMock(enqueue_job=enqueue_mock)}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await check_scheduled_notifications(ctx)

        # Schedule was still marked even though enqueue failed
        assert result["enqueued"] == 1
        await db_session.refresh(schedule)
        assert schedule.last_triggered_at is not None


# ── process_scheduled_notification ──


class TestProcessScheduledNotification:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("notify_day_before", "lat", "lon"),
        [
            pytest.param(False, "40.71427800", "-74.00597200", id="today"),
            pytest.param(True, "40.71427800", "-74.00597200", id="day-before"),
            pytest.param(True, "0", "37.00000000", id="day-before-on-the-equator"),
            pytest.param(True, "51.50000000", "0", id="day-before-on-greenwich"),
        ],
    )
    async def test_happy_path_generates_outfit_and_sends(
        self,
        db_session: AsyncSession,
        schedule_user: User,
        ntfy_channel,
        notify_day_before,
        lat,
        lon,
    ):
        schedule_user.location_lat = Decimal(lat)
        schedule_user.location_lon = Decimal(lon)
        schedule = _make_due_schedule(schedule_user, notify_day_before=notify_day_before)
        outfit = Outfit(
            user_id=schedule_user.id,
            occasion="casual",
            scheduled_for=datetime.now(UTC).date(),
            status=OutfitStatus.pending,
            source=OutfitSource.scheduled,
            reasoning="Light layers",
        )
        db_session.add_all([schedule, outfit])
        await db_session.commit()

        mock_rec_service = MagicMock()
        mock_rec_service.generate_recommendation = AsyncMock(return_value=outfit)
        post = _fake_post()

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch(
                "app.workers.notifications.RecommendationService",
                return_value=mock_rec_service,
            ),
            patch("app.workers.notifications.WeatherService") as weather_service,
            patch.object(httpx.AsyncClient, "post", post),
        ):
            weather_service.return_value.get_tomorrow_weather = AsyncMock()
            result = await process_scheduled_notification({"job_try": 1}, str(schedule.id))

        assert result == {"status": "sent", "outfit_id": str(outfit.id)}
        assert [c.args[0] for c in post.call_args_list] == ["https://ntfy.sh/test-topic"]
        forecast = weather_service.return_value.get_tomorrow_weather
        if notify_day_before:
            forecast.assert_awaited_once_with(Decimal(lat), Decimal(lon))
        else:
            forecast.assert_not_called()
        [row] = (
            (
                await db_session.execute(
                    select(Notification).where(Notification.outfit_id == outfit.id)
                )
            )
            .scalars()
            .all()
        )
        assert (row.channel, row.status) == ("ntfy", NotificationStatus.sent)

    @pytest.mark.asyncio
    async def test_bad_stored_timezone_targets_utc_today(
        self, db_session: AsyncSession, schedule_user: User, ntfy_channel
    ):
        schedule_user.timezone = "Mars/Olympus_Mons"
        schedule = _make_due_schedule(schedule_user)
        outfit = Outfit(
            user_id=schedule_user.id,
            occasion="casual",
            scheduled_for=datetime.now(UTC).date(),
            status=OutfitStatus.pending,
            source=OutfitSource.scheduled,
        )
        db_session.add_all([schedule, outfit])
        await db_session.commit()

        mock_rec_service = MagicMock()
        mock_rec_service.generate_recommendation = AsyncMock(return_value=outfit)

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch(
                "app.workers.notifications.RecommendationService",
                return_value=mock_rec_service,
            ),
            patch("app.workers.notifications.WeatherService"),
            patch.object(httpx.AsyncClient, "post", _fake_post()),
        ):
            result = await process_scheduled_notification({"job_try": 1}, str(schedule.id))

        assert result == {"status": "sent", "outfit_id": str(outfit.id)}
        kwargs = mock_rec_service.generate_recommendation.call_args.kwargs
        assert kwargs["scheduled_date"] == datetime.now(UTC).date()

    @pytest.mark.asyncio
    async def test_only_disabled_channels_returns_skipped(
        self, db_session: AsyncSession, schedule_user: User, ntfy_channel
    ):
        ntfy_channel.enabled = False
        schedule = _make_due_schedule(schedule_user)
        db_session.add(schedule)
        await db_session.commit()

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await process_scheduled_notification({"job_try": 1}, str(schedule.id))

        assert result == {"status": "skipped", "reason": "no_channels"}

    @pytest.mark.asyncio
    async def test_missing_schedule_returns_skipped(self, db_session: AsyncSession):
        ctx = {"job_try": 1}
        fake_id = str(uuid.uuid4())

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await process_scheduled_notification(ctx, fake_id)

        assert result == {"status": "skipped", "reason": "not_found"}

    @pytest.mark.asyncio
    async def test_deleted_user_returns_skipped(
        self, db_session: AsyncSession, schedule_user: User
    ):
        schedule_user.is_active = False
        await db_session.commit()

        schedule = _make_due_schedule(schedule_user)
        db_session.add(schedule)
        await db_session.commit()

        ctx = {"job_try": 1}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await process_scheduled_notification(ctx, str(schedule.id))

        assert result == {"status": "skipped", "reason": "user_not_found"}

    @pytest.mark.asyncio
    async def test_no_enabled_channels_returns_skipped(
        self, db_session: AsyncSession, schedule_user: User
    ):
        schedule = _make_due_schedule(schedule_user)
        db_session.add(schedule)
        await db_session.commit()

        ctx = {"job_try": 1}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await process_scheduled_notification(ctx, str(schedule.id))

        assert result == {"status": "skipped", "reason": "no_channels"}

    @pytest.mark.asyncio
    async def test_value_error_from_ai_returns_skipped(
        self, db_session: AsyncSession, schedule_user: User, ntfy_channel
    ):
        schedule = _make_due_schedule(schedule_user)
        db_session.add(schedule)
        await db_session.commit()

        mock_rec_service = MagicMock()
        mock_rec_service.generate_recommendation = AsyncMock(
            side_effect=ValueError("not enough items")
        )

        ctx = {"job_try": 1}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch(
                "app.workers.notifications.RecommendationService",
                return_value=mock_rec_service,
            ),
            patch("app.workers.notifications.WeatherService"),
        ):
            result = await process_scheduled_notification(ctx, str(schedule.id))

        assert result["status"] == "skipped"
        assert "not enough items" in result["reason"]

    @pytest.mark.asyncio
    async def test_generic_exception_rolls_back_and_reraises(
        self, db_session: AsyncSession, schedule_user: User, ntfy_channel
    ):
        schedule = _make_due_schedule(schedule_user)
        db_session.add(schedule)
        await db_session.commit()

        mock_rec_service = MagicMock()
        mock_rec_service.generate_recommendation = AsyncMock(
            side_effect=RuntimeError("AI service down")
        )

        ctx = {"job_try": 1}

        with pytest.raises(RuntimeError, match="AI service down"):
            with (
                patch("app.workers.notifications.get_db_session", return_value=db_session),
                patch.object(db_session, "close", new_callable=AsyncMock),
                patch(
                    "app.workers.notifications.RecommendationService",
                    return_value=mock_rec_service,
                ),
                patch("app.workers.notifications.WeatherService"),
            ):
                await process_scheduled_notification(ctx, str(schedule.id))


def _shirts(count: int) -> list[ClothingItem]:
    return [ClothingItem(type="shirt", name=f"Shirt {n}") for n in range(1, count + 1)]


class TestWashReminderMessage:
    @pytest.mark.parametrize(
        ("items", "body"),
        [
            (_shirts(1), "1 item needs washing: Shirt 1"),
            (_shirts(3), "3 items need washing: Shirt 1, Shirt 2, Shirt 3"),
            (
                _shirts(7),
                "7 items need washing: Shirt 1, Shirt 2, Shirt 3, Shirt 4, Shirt 5 and 2 more",
            ),
            ([ClothingItem(type="jeans")], "1 item needs washing: jeans"),
        ],
        ids=["singular", "plural", "summarised", "unnamed"],
    )
    def test_body_lists_the_items(self, items, body):
        assert wash_reminder_message(items).body == body

    def test_links_to_the_wardrobe(self, monkeypatch):
        settings = Settings(_env_file=None, app_url="https://x.com")
        monkeypatch.setattr("app.workers.notifications.get_settings", lambda: settings)

        message = wash_reminder_message(_shirts(1))

        assert message.title == "Laundry Reminder"
        assert message.url == "https://x.com/dashboard/wardrobe"
        assert message.url_label == "View Wardrobe"
        assert message.data == {"screen": "wardrobe"}


def _http_response(url: str, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", url)
    if status_code != 200:
        return httpx.Response(status_code, text="boom", request=request)
    if url == EXPO_PUSH_URL:
        return httpx.Response(200, json={"data": {"status": "ok", "id": "t1"}}, request=request)
    return httpx.Response(200, json={"id": "m1"}, request=request)


def _fake_post(failures: dict[str, int] | None = None) -> AsyncMock:
    async def post(url, **kwargs):
        return _http_response(url, (failures or {}).get(url, 200))

    return AsyncMock(side_effect=post)


def _posts_to(post: AsyncMock, urls: set[str]) -> list:
    return [c for c in post.call_args_list if c.args[0] in urls]


class TestWashReminderChannels:
    @pytest_asyncio.fixture
    async def dirty_user(self, db_session: AsyncSession, schedule_user: User) -> User:
        db_session.add(
            ClothingItem(
                user_id=schedule_user.id,
                image_path="items/jeans.jpg",
                type="jeans",
                name="Black Jeans",
                needs_wash=True,
            )
        )
        await db_session.commit()
        return schedule_user

    async def _add_channel(
        self, db_session: AsyncSession, user: User, channel: str, config: dict, priority: int
    ) -> None:
        db_session.add(
            NotificationSettings(
                user_id=user.id,
                channel=channel,
                enabled=True,
                priority=priority,
                config=config,
            )
        )
        await db_session.commit()

    async def _run(self, db_session: AsyncSession, post: AsyncMock) -> None:
        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch.object(httpx.AsyncClient, "post", post),
        ):
            await _check_wash_reminders_inner({})

    async def _reminders(self, db_session: AsyncSession, user: User) -> list[Notification]:
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.payload["type"].astext == "wash_reminder",
            )
        )
        return list(result.scalars().all())

    @pytest.mark.asyncio
    async def test_bad_stored_timezone_still_gets_reminder(
        self, db_session: AsyncSession, dirty_user: User
    ):
        dirty_user.timezone = "Mars/Olympus_Mons"
        await db_session.commit()
        topic = f"laundry-{uuid.uuid4().hex[:12]}"
        await self._add_channel(
            db_session, dirty_user, "ntfy", {"server": "https://ntfy.sh", "topic": topic}, 1
        )

        await self._run(db_session, _fake_post())

        [reminder] = await self._reminders(db_session, dirty_user)
        assert reminder.status == NotificationStatus.sent

    @pytest.mark.parametrize(
        ("channel", "config", "url"),
        [
            (
                "mattermost",
                {"webhook_url": "https://chat.example.com/hooks/{key}"},
                "https://chat.example.com/hooks/{key}",
            ),
            (
                "ntfy",
                {"server": "https://ntfy.example.com", "topic": "laundry-{key}"},
                "https://ntfy.example.com/laundry-{key}",
            ),
            ("expo_push", {"push_token": "ExponentPushToken[{key}]"}, EXPO_PUSH_URL),
        ],
    )
    @pytest.mark.asyncio
    async def test_single_channel_user_gets_reminder_on_the_stored_target(
        self, db_session: AsyncSession, dirty_user: User, channel, config, url
    ):
        # Earlier tests leave dirty items behind, so a unique key picks out this user's send.
        key = uuid.uuid4().hex
        stored = {name: value.format(key=key) for name, value in config.items()}
        await self._add_channel(db_session, dirty_user, channel, stored, 1)
        post = _fake_post()

        await self._run(db_session, post)

        [call] = [c for c in post.call_args_list if key in str(c)]
        assert call.args[0] == url.format(key=key)
        assert "Black Jeans" in str(call.kwargs)
        [reminder] = await self._reminders(db_session, dirty_user)
        assert reminder.channel == channel
        assert reminder.status == NotificationStatus.sent

    @pytest.mark.asyncio
    async def test_tries_channels_in_priority_order_until_one_succeeds(
        self, db_session: AsyncSession, dirty_user: User
    ):
        topic = f"laundry-{uuid.uuid4().hex[:12]}"
        ntfy_url = f"https://ntfy.example.com/{topic}"
        webhook = f"https://chat.example.com/hooks/{uuid.uuid4().hex}"
        token = f"ExponentPushToken[{uuid.uuid4().hex}]"
        await self._add_channel(db_session, dirty_user, "expo_push", {"push_token": token}, 3)
        await self._add_channel(
            db_session,
            dirty_user,
            "ntfy",
            {"server": "https://ntfy.example.com", "topic": topic},
            2,
        )
        await self._add_channel(db_session, dirty_user, "mattermost", {"webhook_url": webhook}, 1)
        post = _fake_post({webhook: 500})

        await self._run(db_session, post)

        calls = _posts_to(post, {webhook, ntfy_url})
        assert [c.args[0] for c in calls] == [webhook, ntfy_url]
        assert not [c for c in _posts_to(post, {EXPO_PUSH_URL}) if c.kwargs["json"]["to"] == token]
        rows = {
            (r.channel, r.status, r.error_message, r.sent_at is not None)
            for r in await self._reminders(db_session, dirty_user)
        }
        assert rows == {
            ("mattermost", NotificationStatus.failed, "HTTP 500: boom", False),
            ("ntfy", NotificationStatus.sent, None, True),
        }

    @pytest.mark.asyncio
    async def test_broken_channel_is_logged_and_next_channel_still_tried(
        self, db_session: AsyncSession, dirty_user: User, caplog
    ):
        webhook = f"https://chat.example.com/hooks/{uuid.uuid4().hex}"
        await self._add_channel(db_session, dirty_user, "ntfy", {"server": "https://x.com"}, 1)
        await self._add_channel(db_session, dirty_user, "mattermost", {"webhook_url": webhook}, 2)
        post = _fake_post()

        await self._run(db_session, post)

        assert len(_posts_to(post, {webhook})) == 1
        broken = [
            r for r in caplog.records if "ntfy" in r.getMessage() and r.levelname == "WARNING"
        ]
        assert broken
        rows = {
            (r.channel, r.status, r.error_message)
            for r in await self._reminders(db_session, dirty_user)
        }
        assert rows == {
            ("ntfy", NotificationStatus.failed, "Field required"),
            ("mattermost", NotificationStatus.sent, None),
        }

    @pytest.mark.asyncio
    async def test_all_channels_failing_records_each_error_and_retries_next_run(
        self, db_session: AsyncSession, dirty_user: User
    ):
        topic = f"laundry-{uuid.uuid4().hex[:12]}"
        ntfy_url = f"https://ntfy.example.com/{topic}"
        webhook = f"https://chat.example.com/hooks/{uuid.uuid4().hex}"
        await self._add_channel(db_session, dirty_user, "mattermost", {"webhook_url": webhook}, 1)
        await self._add_channel(
            db_session,
            dirty_user,
            "ntfy",
            {"server": "https://ntfy.example.com", "topic": topic},
            2,
        )

        await self._run(db_session, _fake_post({webhook: 500, ntfy_url: 503}))

        failed = {
            (r.channel, r.status, r.error_message, r.sent_at)
            for r in await self._reminders(db_session, dirty_user)
        }
        assert failed == {
            ("mattermost", NotificationStatus.failed, "HTTP 500: boom", None),
            ("ntfy", NotificationStatus.failed, "HTTP 503: boom", None),
        }

        await self._run(db_session, _fake_post())

        rows = {(r.channel, r.status) for r in await self._reminders(db_session, dirty_user)}
        assert rows == {
            ("mattermost", NotificationStatus.failed),
            ("ntfy", NotificationStatus.failed),
            ("mattermost", NotificationStatus.sent),
        }


# ── Worker registry ──


class TestWorkerFunctionRegistry:
    def test_process_scheduled_notification_is_registered(self):
        func_names = [f.__name__ for f in WorkerSettings.functions]
        assert "process_scheduled_notification" in func_names

    def test_all_enqueued_functions_are_registered(self):
        func_names = {f.__name__ for f in WorkerSettings.functions}
        required = {
            "tag_item_image",
            "send_notification",
            "process_scheduled_notification",
            "retry_failed_notifications",
            "check_scheduled_notifications",
            "check_wash_reminders",
            "update_learning_profiles",
        }
        missing = required - func_names
        assert not missing, f"Functions enqueued but not registered in WorkerSettings: {missing}"
