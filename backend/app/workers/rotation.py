import asyncio

from app.models.item import ItemStatus
from app.services.image_service import ImageService
from app.workers.db import get_db_session
from app.workers.image_job import run_image_job


async def rotate_item_image_job(
    ctx: dict, item_id: str, direction: str, *, final_status: str = ItemStatus.ready
) -> dict:
    async def rotate(image_path: str) -> dict:
        await asyncio.to_thread(ImageService().rotate_image, image_path, direction)
        return {}

    return await run_image_job(get_db_session(ctx), ctx, item_id, final_status, "Rotation", rotate)
