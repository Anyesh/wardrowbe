import logging

from arq import cron

from app.services.ai_service import AIService
from app.workers.db import close_db, init_db
from app.workers.notifications import (
    check_scheduled_notifications,
    check_wash_reminders,
    process_scheduled_notification,
    retry_failed_notifications,
    send_notification,
    update_learning_profiles,
)
from app.workers.settings import get_redis_settings
from app.workers.tagging import tag_item_image

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    logger.info("Worker starting up...")
    await init_db(ctx)
    ctx["ai_service"] = AIService()
    health = await ctx["ai_service"].check_health()
    logger.info(f"AI service health: {health}")


async def shutdown(ctx: dict) -> None:
    logger.info("Worker shutting down...")
    await close_db(ctx)


class WorkerSettings:
    functions = [
        tag_item_image,
        send_notification,
        retry_failed_notifications,
        check_scheduled_notifications,
        process_scheduled_notification,
        check_wash_reminders,
        update_learning_profiles,
    ]

    cron_jobs = [
        cron(retry_failed_notifications, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(check_scheduled_notifications, minute=None),
        cron(check_wash_reminders, minute=15, hour={0, 6, 12, 18}),
        cron(update_learning_profiles, minute=30, hour=None),
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = get_redis_settings()

    max_jobs = 5
    job_timeout = 600
    max_tries = 3
    health_check_interval = 30

    queue_name = "arq:tagging"
