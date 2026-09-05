import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.models.item import ClothingItem, ItemStatus
from app.services.image_service import ImageService
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)


async def rotate_item_image_job(ctx: dict, item_id: str, direction: str) -> dict:
    """Rotate one item's stored image and regenerate its size variants.

    Rotation overwrites in place, so the item's three paths are unchanged and
    only status bookkeeping is written back.
    """
    db = get_db_session(ctx)
    try:
        result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
        item = result.scalar_one_or_none()
        if item is None:
            logger.warning(f"Item {item_id} not found for rotation job")
            return {"status": "error", "error": "Item not found"}

        item.ai_started_at = datetime.now(UTC)
        await db.commit()

        try:
            image_service = ImageService()
            await asyncio.to_thread(image_service.rotate_image, item.image_path, direction)
            item.status = ItemStatus.ready
            item.ai_started_at = None
            item.processing_kind = None
            await db.commit()
            return {"status": "success", "item_id": item_id}
        except Exception as e:
            logger.error(f"Rotation failed for item {item_id}: {e}")
            # Kind stays "rotate" so the grid labels and retries this as a
            # rotation failure, and ai_raw_response/ai_failed_at are left alone
            # because this job never touched AI tagging's failure bookkeeping -
            # writing ai_failed_at would start a bogus AI retry cooldown.
            item.status = ItemStatus.error
            item.ai_started_at = None
            await db.commit()
            return {"status": "error", "error": str(e)}
    finally:
        await db.close()
