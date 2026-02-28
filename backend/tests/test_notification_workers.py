"""Tests for notification worker concurrency fixes."""

import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationSettings
from app.models.schedule import Schedule
from app.models.user import User
from app.workers.notifications import check_scheduled_notifications, process_scheduled_notification
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
    async def test_happy_path_generates_outfit_and_sends(
        self, db_session: AsyncSession, schedule_user: User, ntfy_channel
    ):
        schedule = _make_due_schedule(schedule_user)
        db_session.add(schedule)
        await db_session.commit()

        mock_outfit = MagicMock()
        mock_outfit.id = uuid.uuid4()

        mock_rec_service = MagicMock()
        mock_rec_service.generate_recommendation = AsyncMock(return_value=mock_outfit)

        mock_dispatcher = MagicMock()
        mock_dispatcher.send_outfit_notification = AsyncMock(return_value=[])

        ctx = {"job_try": 1}

        with (
            patch("app.workers.notifications.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch(
                "app.workers.notifications.RecommendationService",
                return_value=mock_rec_service,
            ),
            patch(
                "app.workers.notifications.NotificationDispatcher",
                return_value=mock_dispatcher,
            ),
            patch("app.workers.notifications.WeatherService"),
        ):
            result = await process_scheduled_notification(ctx, str(schedule.id))

        assert result["status"] == "sent"
        assert result["outfit_id"] == str(mock_outfit.id)
        mock_rec_service.generate_recommendation.assert_called_once()
        mock_dispatcher.send_outfit_notification.assert_called_once()

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
