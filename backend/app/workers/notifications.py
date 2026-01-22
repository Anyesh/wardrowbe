"""Notification background workers."""

import logging
import os
from datetime import UTC, datetime, timedelta

from arq import cron
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.learning import UserLearningProfile
from app.models.notification import Notification, NotificationSettings, NotificationStatus
from app.models.schedule import Schedule
from app.services.learning_service import LearningService
from app.services.notification_service import DeliveryStatus, NotificationDispatcher

logger = logging.getLogger(__name__)


async def get_db_session() -> AsyncSession:
    """Create a database session for workers."""
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


async def send_notification(ctx: dict, user_id: str, outfit_id: str):
    """
    Background job to send a notification for an outfit.
    Called when an outfit is generated and ready to be sent.
    """
    logger.info(f"Sending notification for outfit {outfit_id} to user {user_id}")

    db = await get_db_session()
    try:
        app_url = os.getenv("APP_URL", "http://localhost:3000")
        dispatcher = NotificationDispatcher(db, app_url)

        results = await dispatcher.send_outfit_notification(user_id=user_id, outfit_id=outfit_id)

        await db.commit()

        # Log results
        for result in results:
            logger.info(
                f"Notification result: channel={result.channel}, status={result.status.value}, "
                f"error={result.error}"
            )

        return {"success": any(r.status == DeliveryStatus.SENT for r in results)}

    except Exception:
        logger.exception(f"Failed to send notification for outfit {outfit_id}")
        await db.rollback()
        raise
    finally:
        await db.close()


async def retry_failed_notifications(ctx: dict):
    """
    Periodic job to retry failed notifications.
    Runs every minute via cron.
    """
    logger.info("Checking for notifications to retry...")

    db = await get_db_session()
    try:
        # Get notifications in retrying status
        result = await db.execute(
            select(Notification).where(
                and_(
                    Notification.status == NotificationStatus.retrying,
                    Notification.attempts < Notification.max_attempts,
                )
            )
        )
        notifications = list(result.scalars().all())

        if not notifications:
            logger.info("No notifications to retry")
            return {"retried": 0}

        retried = 0
        app_url = os.getenv("APP_URL", "http://localhost:3000")
        dispatcher = NotificationDispatcher(db, app_url)

        for notification in notifications:
            try:
                # Increment attempt counter
                notification.attempts += 1
                notification.last_attempt_at = datetime.now(UTC)

                # Retry via the existing notification (don't create new records)
                result = await dispatcher.retry_notification(notification)

                if result.status == DeliveryStatus.SENT:
                    notification.status = NotificationStatus.sent
                    notification.sent_at = datetime.now(UTC)
                    retried += 1
                elif notification.attempts >= notification.max_attempts:
                    notification.status = NotificationStatus.failed
                    notification.error_message = result.error or "Max retries exceeded"
                else:
                    notification.error_message = result.error

                await db.commit()

            except Exception as e:
                logger.exception(f"Failed to retry notification {notification.id}: {e}")
                if notification.attempts >= notification.max_attempts:
                    notification.status = NotificationStatus.failed
                    notification.error_message = str(e)
                    await db.commit()

        logger.info(f"Retried {retried} notifications")
        return {"retried": retried}

    except Exception as e:
        logger.exception("Error in retry_failed_notifications")
        await db.rollback()
        return {"retried": 0, "error": str(e)}
    finally:
        await db.close()


async def check_scheduled_notifications(ctx: dict):
    """
    Check if any users have scheduled notifications due now.
    Runs every minute via cron.

    Schedule times are stored in UTC, so we compare directly against UTC time.

    Supports two modes:
    - notify_day_before=False: Notify on the same day as the outfit (morning of)
    - notify_day_before=True: Notify evening before (e.g., Sunday evening for Monday outfit)
    """
    from sqlalchemy.orm import selectinload

    from app.models.outfit import OutfitSource
    from app.models.user import User
    from app.services.recommendation_service import RecommendationService
    from app.services.weather_service import get_weather_service

    logger.info("Checking scheduled notifications...")

    db = await get_db_session()
    try:
        now_utc = datetime.now(UTC)
        current_utc_day = now_utc.weekday()
        current_utc_time = now_utc.time()
        tomorrow_utc_day = (current_utc_day + 1) % 7

        # Find all enabled schedules that could trigger now:
        # 1. Same-day schedules (notify_day_before=False) where day_of_week == today
        # 2. Day-before schedules (notify_day_before=True) where day_of_week == tomorrow
        result = await db.execute(
            select(Schedule).where(
                and_(
                    Schedule.enabled.is_(True),
                    # Match same-day OR day-before schedules
                    (
                        (
                            (Schedule.notify_day_before.is_(False))
                            & (Schedule.day_of_week == current_utc_day)
                        )
                        | (
                            (Schedule.notify_day_before.is_(True))
                            & (Schedule.day_of_week == tomorrow_utc_day)
                        )
                    ),
                )
            )
        )
        schedules = list(result.scalars().all())

        # Create services once outside the loop
        app_url = os.getenv("APP_URL", "http://localhost:3000")
        recommendation_service = RecommendationService(db)
        dispatcher = NotificationDispatcher(db, app_url)
        weather_service = get_weather_service()

        triggered = 0
        for schedule in schedules:
            # Check if current UTC time matches schedule time (within 1 minute)
            schedule_minutes = (
                schedule.notification_time.hour * 60 + schedule.notification_time.minute
            )
            current_minutes = current_utc_time.hour * 60 + current_utc_time.minute

            if abs(schedule_minutes - current_minutes) > 1:
                continue

            # Deduplication: Skip if triggered within the last hour
            # This is more robust than same-day check for schedules near midnight
            threshold = now_utc - timedelta(hours=1)
            if schedule.last_triggered_at:
                if schedule.last_triggered_at >= threshold:
                    logger.debug(
                        f"Skipping schedule {schedule.id} - triggered recently at "
                        f"{schedule.last_triggered_at}"
                    )
                    continue

            # Get user for recommendation generation
            user_result = await db.execute(
                select(User)
                .options(selectinload(User.preferences))
                .where(User.id == schedule.user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                continue

            # Check if user has notification channels configured
            channels_result = await db.execute(
                select(NotificationSettings).where(
                    and_(
                        NotificationSettings.user_id == schedule.user_id,
                        NotificationSettings.enabled.is_(True),
                    )
                )
            )
            if not channels_result.scalars().first():
                continue

            try:
                # For day-before schedules, fetch tomorrow's weather forecast
                weather_override = None
                is_for_tomorrow = schedule.notify_day_before

                if is_for_tomorrow and user.location_lat and user.location_lon:
                    try:
                        weather_override = await weather_service.get_tomorrow_weather(
                            user.location_lat, user.location_lon
                        )
                        logger.info(
                            f"Fetched tomorrow's forecast for user {user.id}: "
                            f"{weather_override.temperature}°C, {weather_override.condition}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to fetch tomorrow's weather: {e}")
                        # Continue without weather override - will use today's weather

                # Generate outfit recommendation
                outfit = await recommendation_service.generate_recommendation(
                    user=user,
                    occasion=schedule.occasion,
                    source=OutfitSource.scheduled,
                    weather_override=weather_override,
                )

                # Send notification (with for_tomorrow flag for messaging)
                _results = await dispatcher.send_outfit_notification(
                    user_id=str(user.id),
                    outfit_id=str(outfit.id),
                    for_tomorrow=is_for_tomorrow,
                )

                # Mark as triggered to prevent duplicates (store in UTC)
                schedule.last_triggered_at = now_utc
                await db.commit()

                logger.info(
                    f"Triggered notification for user {schedule.user_id} "
                    f"(utc_day={current_utc_day}, utc_time={current_utc_time.strftime('%H:%M')}, "
                    f"occasion={schedule.occasion}, outfit={outfit.id}, for_tomorrow={is_for_tomorrow})"
                )
                triggered += 1

            except ValueError as e:
                # User-facing errors like "no location" or "no items"
                logger.warning(f"Cannot generate outfit for user {schedule.user_id}: {e}")
            except Exception as e:
                logger.exception(
                    f"Failed to generate/send notification for user {schedule.user_id}: {e}"
                )

        logger.info(f"Checked {len(schedules)} schedules, {triggered} triggered")
        return {"checked": len(schedules), "triggered": triggered}

    except Exception as e:
        logger.exception("Error in check_scheduled_notifications")
        return {"error": str(e)}
    finally:
        await db.close()


async def update_learning_profiles(ctx: dict):
    """
    Periodic job to update learning profiles for users with new feedback.

    This job runs hourly and recomputes learning profiles for users who:
    1. Have given feedback since their last profile computation
    2. Have not had their profile computed in the last hour

    The learning system uses Netflix/Spotify-style algorithms to learn user
    preferences from their feedback history.
    """
    logger.info("Starting periodic learning profile updates...")

    db = await get_db_session()
    try:
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        # Find users who need profile updates
        # Query users with learning profiles that are stale or don't exist
        from app.models.outfit import Outfit, OutfitStatus
        from app.models.user import User

        # Get users who have given feedback (accepted/rejected outfits) recently
        result = await db.execute(
            select(User.id)
            .join(Outfit, User.id == Outfit.user_id)
            .where(
                and_(
                    Outfit.status.in_([OutfitStatus.accepted, OutfitStatus.rejected]),
                    Outfit.responded_at >= one_hour_ago,
                )
            )
            .distinct()
        )
        users_with_recent_feedback = {row[0] for row in result.all()}

        if not users_with_recent_feedback:
            logger.info("No users with recent feedback to update")
            return {"updated": 0}

        learning_service = LearningService(db)
        updated_count = 0

        for user_id in users_with_recent_feedback:
            try:
                # Check if profile needs update (doesn't exist or is stale)
                profile_result = await db.execute(
                    select(UserLearningProfile).where(UserLearningProfile.user_id == user_id)
                )
                profile = profile_result.scalar_one_or_none()

                needs_update = (
                    profile is None
                    or profile.last_computed_at is None
                    or profile.last_computed_at < one_hour_ago
                )

                if needs_update:
                    await learning_service.recompute_learning_profile(user_id)
                    await learning_service.generate_insights(user_id)
                    updated_count += 1
                    logger.info(f"Updated learning profile for user {user_id}")

            except Exception as e:
                logger.warning(f"Failed to update learning profile for user {user_id}: {e}")
                continue

        logger.info(f"Completed learning profile updates: {updated_count} profiles updated")
        return {"updated": updated_count}

    except Exception as e:
        logger.exception("Error in update_learning_profiles")
        return {"error": str(e)}
    finally:
        await db.close()


class WorkerSettings:
    """ARQ worker settings for notification jobs."""

    functions = [
        send_notification,
        retry_failed_notifications,
        check_scheduled_notifications,
        update_learning_profiles,
    ]

    cron_jobs = [
        # Retry failed notifications every 5 minutes
        cron(retry_failed_notifications, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        # Check scheduled notifications every minute
        cron(check_scheduled_notifications, minute=None),  # Every minute
        # Update learning profiles hourly (at minute 30 to avoid overlap with other jobs)
        cron(update_learning_profiles, minute=30, hour=None),  # Every hour at :30
    ]

    # Redis settings are inherited from the main worker settings
    redis_settings = None  # Will be set from environment
