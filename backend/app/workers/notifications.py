import logging
import os
from datetime import UTC, datetime, timedelta

from arq import cron
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem
from app.models.learning import UserLearningProfile
from app.models.notification import Notification, NotificationSettings, NotificationStatus
from app.models.outfit import Outfit, OutfitSource, OutfitStatus
from app.models.schedule import Schedule
from app.models.user import User
from app.schemas.notification import EmailConfig, ExpoPushConfig, NtfyConfig
from app.services.learning_service import LearningService
from app.services.notification_providers import (
    EmailProvider,
    ExpoPushMessage,
    ExpoPushProvider,
    NtfyNotification,
    NtfyProvider,
    build_notification_email,
)
from app.services.notification_service import DeliveryStatus, NotificationDispatcher
from app.services.recommendation_service import RecommendationService
from app.services.weather_service import get_weather_service
from app.utils.redis_lock import distributed_lock
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)


async def reset_schedule_trigger(ctx: dict, schedule_id: str) -> None:
    try:
        db = get_db_session(ctx)
        try:
            result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
            sched = result.scalar_one_or_none()
            if sched:
                sched.last_triggered_at = None
                await db.commit()
                logger.info(
                    f"Reset last_triggered_at for schedule {schedule_id} after final retry failure"
                )
        finally:
            await db.close()
    except (OSError, ConnectionError) as e:
        logger.warning(f"Best-effort recovery failed for schedule {schedule_id}: {e}")


async def send_notification(ctx: dict, user_id: str, outfit_id: str):
    logger.info(f"Sending notification for outfit {outfit_id} to user {user_id}")

    db = get_db_session(ctx)
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
    logger.info("Checking for notifications to retry...")

    db = get_db_session(ctx)
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
            # Non-blocking lock: skip if another worker already retrying this one
            try:
                async with distributed_lock(
                    f"notif-retry:{notification.id}", timeout=30, blocking_timeout=0
                ):
                    # Re-read inside lock to check if status changed
                    await db.refresh(notification)
                    if notification.status != NotificationStatus.retrying:
                        continue

                    notification.attempts += 1
                    notification.last_attempt_at = datetime.now(UTC)

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

            except TimeoutError:
                logger.debug(
                    "Skipping notification %s retry — another worker holds the lock",
                    notification.id,
                )
                continue
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


async def process_scheduled_notification(ctx: dict, schedule_id: str):
    logger.info(f"Processing scheduled notification for schedule {schedule_id}")

    db = get_db_session(ctx)
    try:
        result = await db.execute(select(Schedule).where(Schedule.id == schedule_id))
        schedule = result.scalar_one_or_none()
        if not schedule:
            logger.warning(f"Schedule {schedule_id} not found, skipping")
            return {"status": "skipped", "reason": "not_found"}

        user_result = await db.execute(
            select(User)
            .options(selectinload(User.preferences))
            .where(User.id == schedule.user_id, User.is_active.is_(True))
        )
        user = user_result.scalar_one_or_none()
        if not user:
            logger.warning(f"User {schedule.user_id} not found or deleted, skipping")
            return {"status": "skipped", "reason": "user_not_found"}

        channels_result = await db.execute(
            select(NotificationSettings).where(
                and_(
                    NotificationSettings.user_id == schedule.user_id,
                    NotificationSettings.enabled == True,  # noqa: E712
                )
            )
        )
        if not channels_result.scalars().first():
            logger.warning(f"No enabled channels for user {schedule.user_id}, skipping")
            return {"status": "skipped", "reason": "no_channels"}

        is_for_tomorrow = schedule.notify_day_before
        weather_override = None

        if is_for_tomorrow and user.location_lat and user.location_lon:
            try:
                weather_service = get_weather_service()
                weather_override = await weather_service.get_tomorrow_weather(
                    user.location_lat, user.location_lon
                )
                logger.info(
                    f"Fetched tomorrow's forecast for user {user.id}: "
                    f"{weather_override.temperature}°C, {weather_override.condition}"
                )
            except Exception as e:
                logger.warning(f"Failed to fetch tomorrow's weather: {e}")

        recommendation_service = RecommendationService(db)
        outfit = await recommendation_service.generate_recommendation(
            user=user,
            occasion=schedule.occasion,
            source=OutfitSource.scheduled,
            weather_override=weather_override,
        )

        app_url = os.getenv("APP_URL", "http://localhost:3000")
        dispatcher = NotificationDispatcher(db, app_url)
        await dispatcher.send_outfit_notification(
            user_id=str(user.id),
            outfit_id=str(outfit.id),
            for_tomorrow=is_for_tomorrow,
        )

        await db.commit()

        logger.info(
            f"Processed schedule {schedule_id} for user {schedule.user_id} "
            f"(occasion={schedule.occasion}, outfit={outfit.id}, for_tomorrow={is_for_tomorrow})"
        )
        return {"status": "sent", "outfit_id": str(outfit.id)}

    except ValueError as e:
        logger.warning(f"Cannot generate outfit for schedule {schedule_id}: {e}")
        return {"status": "skipped", "reason": str(e)}
    except Exception:
        logger.exception(f"Failed to process schedule {schedule_id}")
        await db.rollback()
        if ctx.get("job_try", 1) >= 3:
            await reset_schedule_trigger(ctx, schedule_id)
        raise
    finally:
        await db.close()


async def check_scheduled_notifications(ctx: dict):
    logger.info("Checking scheduled notifications...")

    db = get_db_session(ctx)
    try:
        now_utc = datetime.now(UTC)
        current_utc_day = now_utc.weekday()
        current_utc_time = now_utc.time()
        tomorrow_utc_day = (current_utc_day + 1) % 7

        result = await db.execute(
            select(Schedule).where(
                and_(
                    Schedule.enabled == True,  # noqa: E712
                    (
                        (
                            (Schedule.notify_day_before == False)  # noqa: E712
                            & (Schedule.day_of_week == current_utc_day)
                        )
                        | (
                            (Schedule.notify_day_before == True)  # noqa: E712
                            & (Schedule.day_of_week == tomorrow_utc_day)
                        )
                    ),
                )
            )
        )
        schedules = list(result.scalars().all())

        to_enqueue: list[Schedule] = []
        for schedule in schedules:
            schedule_minutes = (
                schedule.notification_time.hour * 60 + schedule.notification_time.minute
            )
            current_minutes = current_utc_time.hour * 60 + current_utc_time.minute

            if abs(schedule_minutes - current_minutes) > 1:
                continue

            # Deduplication: skip if triggered within the last hour
            threshold = now_utc - timedelta(hours=1)
            if schedule.last_triggered_at and schedule.last_triggered_at >= threshold:
                logger.debug(
                    f"Skipping schedule {schedule.id} - triggered recently at "
                    f"{schedule.last_triggered_at}"
                )
                continue

            # Mark as triggered NOW to prevent duplicate enqueues on next cron tick
            schedule.last_triggered_at = now_utc
            to_enqueue.append(schedule)

            logger.info(
                f"Enqueuing notification job for schedule {schedule.id} "
                f"(user={schedule.user_id}, occasion={schedule.occasion})"
            )

        # Commit all last_triggered_at updates before enqueuing
        if to_enqueue:
            await db.commit()

        # Enqueue jobs after commit so dedup is persisted even if enqueue fails.
        # _job_id ensures idempotent enqueue: if multiple workers run the cron
        # concurrently, only the first enqueue for each schedule/minute wins.
        # arq silently ignores enqueue_job when a job with the same _job_id exists.
        minute_key = now_utc.strftime("%Y%m%d%H%M")
        enqueue_failures = 0
        for schedule in to_enqueue:
            try:
                await ctx["redis"].enqueue_job(
                    "process_scheduled_notification",
                    str(schedule.id),
                    _queue_name="arq:tagging",
                    _job_id=f"sched:{schedule.id}:{minute_key}",
                )
            except Exception as e:
                enqueue_failures += 1
                logger.error(f"Failed to enqueue job for schedule {schedule.id}: {e}")

        if enqueue_failures:
            logger.warning(f"{enqueue_failures}/{len(to_enqueue)} jobs failed to enqueue")

        logger.info(f"Checked {len(schedules)} schedules, enqueued {len(to_enqueue)} jobs")
        return {"checked": len(schedules), "enqueued": len(to_enqueue)}

    except Exception as e:
        logger.exception("Error in check_scheduled_notifications")
        return {"error": str(e)}
    finally:
        await db.close()


async def check_wash_reminders(ctx: dict):
    logger.info("Checking wash reminders...")

    # Non-blocking global lock: if another worker already running this job, skip.
    try:
        async with distributed_lock("wash-reminders-cron", timeout=600, blocking_timeout=0):
            return await _check_wash_reminders_inner(ctx)
    except TimeoutError:
        logger.debug("Skipping wash reminders — another worker holds the lock")
        return {"notified": 0, "skipped": "lock_held"}


async def _check_wash_reminders_inner(ctx: dict):
    db = get_db_session(ctx)
    try:
        result = await db.execute(
            select(ClothingItem).where(
                and_(
                    ClothingItem.needs_wash == True,  # noqa: E712
                    ClothingItem.is_archived == False,  # noqa: E712
                )
            )
        )
        dirty_items = list(result.scalars().all())

        if not dirty_items:
            logger.info("No items need washing")
            return {"notified": 0}

        user_items: dict[str, list] = {}
        for item in dirty_items:
            uid = str(item.user_id)
            if uid not in user_items:
                user_items[uid] = []
            user_items[uid].append(item)

        app_url = os.getenv("APP_URL", "http://localhost:3000")
        notified = 0

        for user_id, items in user_items.items():
            try:
                # Check if user has notification channels
                channels_result = await db.execute(
                    select(NotificationSettings).where(
                        and_(
                            NotificationSettings.user_id == user_id,
                            NotificationSettings.enabled == True,  # noqa: E712
                        )
                    )
                )
                channels = list(channels_result.scalars().all())
                if not channels:
                    continue

                # Check deduplication: don't send more than once per day
                one_day_ago = datetime.now(UTC) - timedelta(days=1)
                existing = await db.execute(
                    select(Notification).where(
                        and_(
                            Notification.user_id == user_id,
                            Notification.payload["type"].astext == "wash_reminder",
                            Notification.created_at >= one_day_ago,
                        )
                    )
                )
                if existing.scalars().first():
                    continue

                item_names = [i.name or i.type for i in items[:5]]
                count = len(items)
                summary = ", ".join(item_names)
                if count > 5:
                    summary += f" and {count - 5} more"

                title = "Laundry Reminder"
                body = f"{count} item{'s' if count != 1 else ''} need washing: {summary}"

                # Send via first enabled channel
                sent = False
                sent_channel = "unknown"
                for channel in channels:
                    try:
                        if channel.channel == "ntfy":
                            provider = NtfyProvider(NtfyConfig(**channel.config))
                            send_result = await provider.send(
                                NtfyNotification(
                                    title=title,
                                    message=body,
                                    click=f"{app_url}/dashboard/wardrobe",
                                    tags=["shirt", "droplet"],
                                )
                            )
                            sent = send_result.get("success", False)
                            sent_channel = "ntfy"
                        elif channel.channel == "email":
                            email_provider = EmailProvider(EmailConfig(**channel.config))
                            send_result = await email_provider.send(
                                build_notification_email(
                                    to=email_provider.to_address,
                                    subject=title,
                                    heading=title,
                                    body=body,
                                    cta_text="View Wardrobe",
                                    cta_url=f"{app_url}/dashboard/wardrobe",
                                    app_url=app_url,
                                )
                            )
                            sent = send_result.get("success", False)
                            sent_channel = "email"
                        elif channel.channel == "expo_push":
                            provider = ExpoPushProvider(ExpoPushConfig(**channel.config))
                            send_result = await provider.send(
                                ExpoPushMessage(
                                    title=title,
                                    body=body,
                                    data={"screen": "wardrobe"},
                                )
                            )
                            sent = send_result.get("success", False)
                            sent_channel = "expo_push"

                        if sent:
                            break
                    except Exception as e:
                        logger.warning(f"Failed to send wash reminder via {channel.channel}: {e}")

                # Create notification record
                notification = Notification(
                    user_id=user_id,
                    channel=sent_channel,
                    status=NotificationStatus.sent if sent else NotificationStatus.failed,
                    payload={
                        "type": "wash_reminder",
                        "item_count": count,
                        "title": title,
                        "body": body,
                    },
                    sent_at=datetime.now(UTC) if sent else None,
                    error_message=None if sent else "All channels failed",
                )
                db.add(notification)
                await db.commit()
                if sent:
                    notified += 1

            except Exception as e:
                logger.warning(f"Failed to send wash reminder for user {user_id}: {e}")
                continue

        logger.info(f"Sent wash reminders to {notified} users")
        return {"notified": notified}

    except Exception as e:
        logger.exception("Error in check_wash_reminders")
        return {"error": str(e)}
    finally:
        await db.close()


async def update_learning_profiles(ctx: dict):
    logger.info("Starting periodic learning profile updates...")

    db = get_db_session(ctx)
    try:
        now = datetime.now(UTC)
        one_hour_ago = now - timedelta(hours=1)

        # Find users with recent feedback who need profile updates
        # (accepted/rejected outfits in last hour)
        result = await db.execute(
            select(User.id)
            .join(Outfit, User.id == Outfit.user_id)
            .where(
                and_(
                    User.is_active.is_(True),
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
    functions = [
        send_notification,
        retry_failed_notifications,
        check_scheduled_notifications,
        process_scheduled_notification,
        check_wash_reminders,
        update_learning_profiles,
    ]

    cron_jobs = [
        # Retry failed notifications every 5 minutes
        cron(retry_failed_notifications, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        # Check scheduled notifications every minute
        cron(check_scheduled_notifications, minute=None),  # Every minute
        # Check wash reminders every 6 hours (at minute 15)
        cron(check_wash_reminders, minute=15, hour={0, 6, 12, 18}),
        # Update learning profiles hourly (at minute 30 to avoid overlap with other jobs)
        cron(update_learning_profiles, minute=30, hour=None),  # Every hour at :30
    ]

    # Redis settings are inherited from the main worker settings
    redis_settings = None  # Will be set from environment
