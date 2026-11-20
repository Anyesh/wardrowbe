import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.config import get_settings
from app.models.try_on import OutfitTryOn, TryOnStatus
from app.services.image_generation import (
    ERROR_FAILED,
    TryOnGenerationError,
    generate_try_on_image,
)
from app.services.image_service import ImageService
from app.services.try_on_service import (
    ERROR_DISABLED,
    ERROR_ITEM_IMAGE_MISSING,
    ERROR_NO_PHOTO,
    ItemImageMissingError,
    compute_cache_key,
    load_outfit,
    load_photo,
    outfit_garments,
    read_model_inputs,
)
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)


async def _current_pending_row(db, outfit_id: UUID, job_token: str) -> OutfitTryOn | None:
    """The outfit's row, only while it is still pending for this very generation.

    A newer request gives the row a new token, so a job that was overtaken (stale retry,
    regenerate) finds nothing here and writes nothing.
    """
    # populate_existing: the row may have been changed (or deleted) while the model worked.
    result = await db.execute(
        select(OutfitTryOn)
        .where(OutfitTryOn.outfit_id == outfit_id)
        .execution_options(populate_existing=True)
    )
    row = result.scalar_one_or_none()
    if row is None or row.status != TryOnStatus.pending:
        return None
    if row.job_token is None or str(row.job_token) != job_token:
        return None
    return row


async def _finish_failed(db, outfit_id: UUID, job_token: str, error_code: str) -> None:
    await db.rollback()
    row = await _current_pending_row(db, outfit_id, job_token)
    if row is None:
        return
    # A previous successful image (and its files) stays, so a failed regeneration does not
    # cost the user the last usable result; the error is shown next to it.
    row.status = TryOnStatus.failed
    row.error_code = error_code
    row.completed_at = datetime.now(UTC)
    await db.commit()


async def generate_try_on(ctx: dict, outfit_id: str, job_token: str) -> None:
    """Draw one outfit on the user's reference photo. Never leaves the row pending.

    Registered with max_tries=1 and a timeout above the provider timeout (see
    try_on_job_timeout_seconds): the call is paid, so arq must not run it twice.
    """
    outfit_uuid = UUID(outfit_id)
    db = get_db_session(ctx)
    try:
        try:
            row = await _current_pending_row(db, outfit_uuid, job_token)
            if row is None:
                return
            await _generate(db, row, job_token)
        except TryOnGenerationError as e:
            await _finish_failed(db, outfit_uuid, job_token, e.error_code)
        except ItemImageMissingError:
            await _finish_failed(db, outfit_uuid, job_token, ERROR_ITEM_IMAGE_MISSING)
        except asyncio.CancelledError:
            # arq's job timeout (or a shutdown) cancels the task: record it before leaving.
            logger.error("Try-on job cancelled for outfit %s", outfit_id)
            try:
                await _finish_failed(db, outfit_uuid, job_token, ERROR_FAILED)
            except Exception:
                logger.error("Could not record the cancelled try-on for outfit %s", outfit_id)
            raise
        except Exception as e:
            # Class name only: exception text can carry provider output or file contents.
            logger.error("Try-on job failed for outfit %s: %s", outfit_id, type(e).__name__)
            await _finish_failed(db, outfit_uuid, job_token, ERROR_FAILED)
    finally:
        await db.close()


async def _generate(db, row: OutfitTryOn, job_token: str) -> None:
    outfit_id, user_id = row.outfit_id, row.user_id
    # Queued jobs outlive a settings change: an operator who turns try-on off must not have
    # photos sent to the provider afterwards.
    if not get_settings().try_on_enabled:
        raise TryOnGenerationError(ERROR_DISABLED)
    outfit = await load_outfit(db, outfit_id, user_id)
    photo = await load_photo(db, user_id)
    if outfit is None:
        return
    if photo is None:
        raise TryOnGenerationError(ERROR_NO_PHOTO)

    image_service = ImageService()
    garments = outfit_garments(outfit)
    if not garments:
        raise ItemImageMissingError
    # The key describes the inputs actually sent, so a change made while the model works
    # shows up as stale instead of being hidden behind a fresh-looking result.
    cache_key = compute_cache_key(photo, garments, image_service)
    person, garment_jpegs = await asyncio.to_thread(
        read_model_inputs, photo, garments, image_service
    )
    model_garments = [g.garment for g in garments]
    # Release the connection while the model works; it can take minutes. This expires every
    # loaded object, so nothing read from them may be used below.
    await db.rollback()

    # Last look before the paid call: still wanted, still enabled, photo still there.
    if not get_settings().try_on_enabled:
        raise TryOnGenerationError(ERROR_DISABLED)
    if await _current_pending_row(db, outfit_id, job_token) is None:
        return
    if await load_photo(db, user_id) is None:
        raise TryOnGenerationError(ERROR_NO_PHOTO)
    await db.rollback()

    generated = await generate_try_on_image(person, garment_jpegs, model_garments)
    paths = await asyncio.to_thread(
        image_service.store_try_on_image, user_id, generated.data, generated.extension
    )

    row = await _current_pending_row(db, outfit_id, job_token)
    if row is None:
        # Deleted (or replaced by a newer request) while the model worked.
        image_service.delete_images({p: p for p in (paths["image_path"], paths["medium_path"])})
        return
    old_paths = [row.image_path, row.medium_path]
    row.status = TryOnStatus.ready
    row.error_code = None
    row.cache_key = cache_key
    row.image_path = paths["image_path"]
    row.medium_path = paths["medium_path"]
    row.completed_at = datetime.now(UTC)
    await db.commit()
    image_service.delete_images({p: p for p in old_paths if p})


def try_on_job_timeout_seconds() -> int:
    """arq's kill deadline: past the provider timeout, so the job can record its own failure."""
    return get_settings().ai_image_timeout + 60
