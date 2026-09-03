import logging

from app.config import get_settings
from app.workers.background_removal import remove_item_background_job
from app.workers.db import close_db, init_db
from app.workers.queues import IMAGE_QUEUE
from app.workers.rotation import rotate_item_image_job
from app.workers.settings import get_redis_settings

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    logger.info("Image worker starting up...")
    await init_db(ctx)


async def shutdown(ctx: dict) -> None:
    logger.info("Image worker shutting down...")
    await close_db(ctx)


class ImageWorkerSettings:
    """Local image work, kept off arq:tagging.

    Rotation and background removal are deterministic Pillow/rembg operations
    with no external AI call, and a bulk batch of them can run to hundreds of
    jobs. Sharing arq:tagging meant one such batch blocked every AI tagging job
    behind it, because that queue drains oldest-first at a concurrency of one.
    """

    functions = [
        rotate_item_image_job,
        remove_item_background_job,
    ]

    on_startup = startup
    on_shutdown = shutdown

    redis_settings = get_redis_settings()

    max_jobs = get_settings().image_worker_concurrency
    job_timeout = get_settings().image_job_timeout
    # Both jobs catch their own failures and record an error status, so arq
    # never sees a raised exception to retry. Re-running a failed deterministic
    # image op would just reproduce the same failure.
    max_tries = 1
    health_check_interval = 30
    allow_abort_jobs = True

    queue_name = IMAGE_QUEUE
