import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.models.item import ClothingItem, ItemStatus
from app.services.image_service import ImageService
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)


async def remove_item_background_job(ctx: dict, item_id: str, bg_color_hex: str) -> dict:
    """Remove the background for one item and composite it onto bg_color_hex.

    Deterministic local image op (no external AI call), so no retry/cooldown
    machinery is needed here - unlike tag_item_image. A failure is just marked
    as an error status; the user re-selects and retries via the bulk toolbar.
    """
    hex_color = bg_color_hex.lstrip("#")
    bg_color = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    db = get_db_session(ctx)
    try:
        result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
        item = result.scalar_one_or_none()
        if item is None:
            logger.warning(f"Item {item_id} not found for background removal job")
            return {"status": "error", "error": "Item not found"}

        item.ai_started_at = datetime.now(UTC)
        await db.commit()

        try:
            image_service = ImageService()
            out = await asyncio.to_thread(
                image_service.remove_background, item.image_path, bg_color
            )
            item.original_image_path = out["original_backup_path"]
            item.status = ItemStatus.ready
            item.ai_started_at = None
            item.processing_kind = None
            await db.commit()
            return {"status": "success", "item_id": item_id}
        except Exception as e:
            logger.error(f"Background removal failed for item {item_id}: {e}")
            # Kind stays "background_removal" so the grid labels and retries
            # this as a background-removal failure, not a generic AI failure -
            # and ai_raw_response/ai_failed_at are left untouched since this
            # job never touched AI tagging's own failure bookkeeping.
            item.status = ItemStatus.error
            item.ai_started_at = None
            await db.commit()
            return {"status": "error", "error": str(e)}
    finally:
        await db.close()
