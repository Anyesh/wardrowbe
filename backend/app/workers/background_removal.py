import asyncio

from app.models.item import ItemStatus
from app.services.image_service import ImageService
from app.workers.db import get_db_session
from app.workers.image_job import run_image_job


async def remove_item_background_job(
    ctx: dict, item_id: str, bg_color_hex: str, *, final_status: str = ItemStatus.ready
) -> dict:
    hex_color = bg_color_hex.lstrip("#")
    bg_color = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    async def remove(image_path: str) -> dict:
        out = await asyncio.to_thread(ImageService().remove_background, image_path, bg_color)
        return {"original_image_path": out["original_backup_path"]}

    return await run_image_job(
        get_db_session(ctx), ctx, item_id, final_status, "Background removal", remove
    )
