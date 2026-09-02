import logging
from datetime import UTC, datetime, timedelta

from arq import cron
from arq.jobs import Job, JobStatus
from sqlalchemy import and_, or_, select, update

from app.config import get_settings
from app.models.item import ClothingItem, ItemStatus
from app.services.ai_service import AIService
from app.workers.background_removal import remove_item_background_job
from app.workers.db import close_db, get_db_session, init_db
from app.workers.notifications import (
    check_scheduled_notifications,
    check_wash_reminders,
    process_scheduled_notification,
    retry_failed_notifications,
    send_notification,
    update_learning_profiles,
)
from app.workers.settings import get_redis_settings
from app.workers.tagging import TAGGING_MAX_TRIES, tag_item_image, worker_job_timeout_seconds

logger = logging.getLogger(__name__)

settings = get_settings()

# How long a never-started `processing` row is left alone before its job is
# checked in Redis at all, to avoid racing the normal
# commit-status-then-enqueue-then-set-job-id sequence every enqueue site uses.
NULL_START_GRACE_SECONDS = 60


def stale_processing_cutoff_seconds() -> int:
    # Must exceed job_timeout, because a job that is still running has not yet
    # had a chance to write its own terminal status. A shorter cutoff condemns
    # live jobs, and the user then retries an item that is still being worked on.
    return WorkerSettings.job_timeout + 120


async def recover_stale_processing_items(ctx: dict) -> None:
    # Condemn only rows whose job Redis can't account for - never a row with a
    # job that's still alive, however old `updated_at`/`ai_started_at` is. A
    # blind time-based condemn (the previous design) has the same failure mode
    # as the bug this exists to fix: it wrongly kills items still legitimately
    # queued behind a large batch, or behind a worker that was briefly down.
    redis = ctx.get("redis")
    if redis is None:
        return  # can't verify job state without it; never blind-condemn
    started_cutoff = datetime.now(UTC) - timedelta(seconds=stale_processing_cutoff_seconds())
    null_start_cutoff = datetime.now(UTC) - timedelta(seconds=NULL_START_GRACE_SECONDS)
    db = get_db_session(ctx)
    try:
        candidates = await db.execute(
            select(ClothingItem.id, ClothingItem.ai_job_id, ClothingItem.processing_kind).where(
                ClothingItem.status == ItemStatus.processing,
                or_(
                    and_(
                        ClothingItem.ai_started_at.is_not(None),
                        ClothingItem.ai_started_at < started_cutoff,
                    ),
                    and_(
                        ClothingItem.ai_started_at.is_(None),
                        ClothingItem.updated_at < null_start_cutoff,
                    ),
                ),
            )
        )
        condemned = 0
        for item_id, ai_job_id, processing_kind in candidates.all():
            lost = ai_job_id is None
            if not lost:
                job_status = await Job(ai_job_id, redis, _queue_name="arq:tagging").status()
                lost = job_status in (JobStatus.not_found, JobStatus.complete)
            if lost:
                # A background-removal row never touched AI tagging, so
                # condemning it must not write ai_raw_response/ai_failed_at -
                # doing so would start a bogus AI retry cooldown
                # (claim_error_items_for_retry keys off ai_failed_at).
                if processing_kind == "background_removal":
                    values = {"status": ItemStatus.error}
                else:
                    values = {
                        "status": ItemStatus.error,
                        "ai_raw_response": {"error": "Job lost or timed out"},
                        "ai_failed_at": datetime.now(UTC),
                    }
                result = await db.execute(
                    update(ClothingItem)
                    .where(ClothingItem.id == item_id, ClothingItem.status == ItemStatus.processing)
                    .values(**values)
                )
                condemned += result.rowcount
        await db.commit()
        if condemned:
            logger.warning("Marked %d stale processing items as error", condemned)
    finally:
        await db.close()


async def startup(ctx: dict) -> None:
    logger.info("Worker starting up...")
    await init_db(ctx)
    if get_settings().ai_enabled:
        ctx["ai_service"] = AIService()
        health = await ctx["ai_service"].check_health()
        logger.info(f"AI service health: {health}")
    else:
        ctx["ai_service"] = None
        logger.info("Internal AI disabled; skipping AI client init and health check")
    await recover_stale_processing_items(ctx)


async def shutdown(ctx: dict) -> None:
    logger.info("Worker shutting down...")
    await close_db(ctx)


class WorkerSettings:
    functions = [
        tag_item_image,
        remove_item_background_job,
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
        cron(recover_stale_processing_items, minute={0, 15, 30, 45}),
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = get_redis_settings()

    # The only AI concurrency bound (see ai_tagging_concurrency in config.py).
    # The cron jobs above share this pool and arq drains one queue oldest-first,
    # so during a large import they run after the backlog whatever this value is.
    max_jobs = get_settings().ai_tagging_concurrency
    job_timeout = worker_job_timeout_seconds()
    max_tries = TAGGING_MAX_TRIES
    health_check_interval = 30
    allow_abort_jobs = True

    queue_name = "arq:tagging"
