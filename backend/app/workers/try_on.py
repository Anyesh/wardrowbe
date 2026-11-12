import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.models.try_on import OutfitTryOn, TryOnStatus
from app.services.image_generation import (
    ERROR_FAILED,
    TryOnGenerationError,
    generate_try_on_image,
)
from app.services.image_service import ImageService
from app.services.try_on_service import (
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


async def _current_pending_row(db, outfit_id: UUID) -> OutfitTryOn | None:
    # populate_existing: the row may have been changed (or deleted) while the model worked.
    result = await db.execute(
        select(OutfitTryOn)
        .where(OutfitTryOn.outfit_id == outfit_id)
        .execution_options(populate_existing=True)
    )
    row = result.scalar_one_or_none()
    return row if row is not None and row.status == TryOnStatus.pending else None


async def _finish_failed(db, outfit_id: UUID, error_code: str) -> None:
    await db.rollback()
    row = await _current_pending_row(db, outfit_id)
    if row is None:
        return
    old_paths = [row.image_path, row.medium_path]
    row.status = TryOnStatus.failed
    row.error_code = error_code
    row.image_path = None
    row.medium_path = None
    row.completed_at = datetime.now(UTC)
    await db.commit()
    ImageService().delete_images({p: p for p in old_paths if p})


async def generate_try_on(ctx: dict, outfit_id: str) -> None:
    """Draw one outfit on the user's reference photo. Never leaves the row pending."""
    outfit_uuid = UUID(outfit_id)
    db = get_db_session(ctx)
    try:
        try:
            row = await _current_pending_row(db, outfit_uuid)
            if row is None:
                return
            await _generate(db, row)
        except TryOnGenerationError as e:
            await _finish_failed(db, outfit_uuid, e.error_code)
        except ItemImageMissingError:
            await _finish_failed(db, outfit_uuid, ERROR_ITEM_IMAGE_MISSING)
        except Exception as e:
            # Class name only: exception text can carry provider output or file contents.
            logger.error("Try-on job failed for outfit %s: %s", outfit_id, type(e).__name__)
            await _finish_failed(db, outfit_uuid, ERROR_FAILED)
    finally:
        await db.close()


async def _generate(db, row: OutfitTryOn) -> None:
    outfit_id, user_id = row.outfit_id, row.user_id
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

    generated = await generate_try_on_image(person, garment_jpegs, model_garments)
    paths = await asyncio.to_thread(
        image_service.store_try_on_image, user_id, generated.data, generated.extension
    )

    row = await _current_pending_row(db, outfit_id)
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
