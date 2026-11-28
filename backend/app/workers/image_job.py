import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.item_service import status_unless_archived

logger = logging.getLogger(__name__)

ImageWork = Callable[[str], Awaitable[dict[str, Any]]]


def _owned_by_job(item_id: UUID, job_id: str):
    return (ClothingItem.id == item_id, ClothingItem.ai_job_id == job_id)


async def _start(db: AsyncSession, item_id: UUID, job_id: str) -> str | None:
    row = (
        await db.execute(
            select(ClothingItem.image_path, ClothingItem.ai_job_id)
            .where(ClothingItem.id == item_id)
            .with_for_update()
        )
    ).first()
    if row is None:
        raise LookupError(f"Item {item_id} not found")
    if row.ai_job_id != job_id:
        await db.commit()
        return None
    await db.execute(
        update(ClothingItem)
        .where(*_owned_by_job(item_id, job_id))
        .values(ai_started_at=datetime.now(UTC))
    )
    await db.commit()
    return row.image_path


async def _finish(db: AsyncSession, item_id: UUID, job_id: str, final_status: ItemStatus) -> None:
    await db.execute(
        update(ClothingItem)
        .where(*_owned_by_job(item_id, job_id))
        .values(
            status=status_unless_archived(final_status),
            processing_kind=None,
            ai_started_at=None,
            ai_job_id=None,
        )
    )
    await db.commit()


async def _fail(db: AsyncSession, item_id: UUID, job_id: str) -> None:
    # The kind stays on a failure so the grid labels and retries it as this image
    # job, and ai_raw_response/ai_failed_at stay untouched: writing ai_failed_at
    # would start a bogus AI retry cooldown.
    await db.execute(
        update(ClothingItem)
        .where(*_owned_by_job(item_id, job_id))
        .values(
            status=status_unless_archived(ItemStatus.error),
            processing_kind=case(
                (ClothingItem.is_archived.is_(True), None), else_=ClothingItem.processing_kind
            ),
            ai_started_at=None,
            ai_job_id=None,
        )
    )
    await db.commit()


async def run_image_job(
    db: AsyncSession,
    ctx: dict,
    item_id: str,
    final_status: str,
    label: str,
    work: ImageWork,
) -> dict:
    """Run one image job against the item its job id still owns.

    `work` gets the image path and returns columns to write even if the item was
    cancelled meanwhile, because the photo on disk has already changed. The
    status is set only while the item still carries this job's id, and an item
    archived during the job stays archived.
    """
    job_id = ctx["job_id"]
    item_uuid = UUID(item_id)
    try:
        try:
            image_path = await _start(db, item_uuid, job_id)
        except LookupError:
            logger.warning(f"Item {item_id} not found for {label} job")
            return {"status": "error", "error": "Item not found"}
        if image_path is None:
            logger.info(f"Skipping {label} for item {item_id}: its job was cancelled")
            return {"status": "cancelled", "item_id": item_id}

        try:
            written = await work(image_path)
        except Exception as e:
            logger.error(f"{label} failed for item {item_id}: {e}")
            await _fail(db, item_uuid, job_id)
            return {"status": "error", "error": str(e)}

        if written:
            await db.execute(
                update(ClothingItem).where(ClothingItem.id == item_uuid).values(**written)
            )
        await _finish(db, item_uuid, job_id, ItemStatus(final_status))
        return {"status": "success", "item_id": item_id}
    finally:
        await db.close()
