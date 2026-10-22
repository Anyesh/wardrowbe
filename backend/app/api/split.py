import asyncio
import logging
from typing import Annotated
from uuid import UUID

from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.config import get_settings
from app.database import DbSession
from app.models.item import ClothingItem
from app.models.user import User
from app.schemas.item import ItemCreate
from app.services.ai_service import AIDisabledError, get_ai_service
from app.services.image_service import ImageService
from app.services.item_service import ItemService
from app.utils.auth import get_current_user
from app.utils.rate_limit import rate_limit_by_user
from app.workers.queues import TAGGING_QUEUE
from app.workers.settings import get_redis_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/items", tags=["Items"])

MAX_SPLIT_BOXES = 8
MIN_BOX_SIDE = 0.02
SPLIT_ARCHIVE_REASON = "split"


class GarmentBox(BaseModel):
    """A box as fractions (0-1) of the photo's width and height."""

    left: float = Field(ge=0, lt=1)
    top: float = Field(ge=0, lt=1)
    width: float = Field(ge=MIN_BOX_SIDE, le=1)
    height: float = Field(ge=MIN_BOX_SIDE, le=1)

    @model_validator(mode="after")
    def _inside_the_photo(self) -> "GarmentBox":
        # A hair over 1 is rounding from a drag handle at the photo's edge, not a real overflow.
        if self.left + self.width > 1.001 or self.top + self.height > 1.001:
            raise ValueError("The box extends outside the photo")
        return self


class DetectedGarmentResponse(GarmentBox):
    type: str
    colors: list[str] = []


class DetectGarmentsResponse(BaseModel):
    garments: list[DetectedGarmentResponse]


class SplitRequest(BaseModel):
    boxes: list[GarmentBox] = Field(min_length=1, max_length=MAX_SPLIT_BOXES)


class SplitResponse(BaseModel):
    source_id: UUID
    item_ids: list[UUID]


async def _owned_item(item_service: ItemService, item_id: UUID, user: User) -> ClothingItem:
    item = await item_service.get_by_id(item_id, user.id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@router.post("/{item_id}/detect-garments", response_model=DetectGarmentsResponse)
async def detect_garments(
    item_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> DetectGarmentsResponse:
    """Find the garments in an item's photo and where they are. Writes nothing."""
    item = await _owned_item(ItemService(db), item_id, current_user)
    await rate_limit_by_user(current_user.id, "detect-garments", max_requests=10, window_seconds=60)

    image_path = ImageService().get_image_path(item.image_path)
    if not image_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")

    try:
        garments = await get_ai_service().detect_garments(image_path)
    except AIDisabledError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI vision is disabled"
        ) from e
    except Exception as e:
        logger.error(f"Garment detection failed for item {item_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="The AI service could not be reached"
        ) from e

    return DetectGarmentsResponse(
        garments=[
            DetectedGarmentResponse(
                type=g.type,
                colors=g.colors,
                left=g.left,
                top=g.top,
                width=g.width,
                height=g.height,
            )
            for g in garments
        ]
    )


@router.post("/{item_id}/split", response_model=SplitResponse, status_code=status.HTTP_201_CREATED)
async def split_item(
    item_id: UUID,
    body: SplitRequest,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> SplitResponse:
    """Make one new item from each box on an item's photo, then archive the original.

    All or nothing: if any crop fails, the crops already stored are removed and nothing changes.
    The original is archived (restorable), never deleted. Crops skip the duplicate check, since
    garments that look alike (a white tee and a cream one) are the point.
    """
    item_service = ItemService(db)
    source = await _owned_item(item_service, item_id, current_user)
    if source.is_archived:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item is archived")

    image_service = ImageService()
    stored: list[dict[str, str]] = []
    created: list[ClothingItem] = []
    try:
        for box in body.boxes:
            try:
                crop = await asyncio.to_thread(
                    image_service.crop_to_jpeg,
                    source.image_path,
                    box.left,
                    box.top,
                    box.width,
                    box.height,
                )
                paths = await image_service.process_and_store(
                    user_id=current_user.id, image_data=crop, original_filename="split.jpg"
                )
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
            stored.append(paths)
            created.append(
                await item_service.create(
                    user_id=current_user.id,
                    item_data=ItemCreate(type="unknown"),
                    image_paths=paths,
                )
            )
        await item_service.archive(source, SPLIT_ARCHIVE_REASON)
        await db.commit()
    except Exception:
        await db.rollback()
        for paths in stored:
            image_service.delete_images(paths)
        raise

    await _start_tagging(db, item_service, image_service, created)
    return SplitResponse(source_id=source.id, item_ids=[i.id for i in created])


async def _start_tagging(
    db: DbSession,
    item_service: ItemService,
    image_service: ImageService,
    items: list[ClothingItem],
) -> None:
    """Queue normal AI tagging for each new item (or mark them ready when AI vision is off)."""
    if not settings.effective_ai_vision_enabled:
        for item in items:
            await item_service.mark_pending(item, set_ready=True)
        await db.commit()
        return

    try:
        redis = await create_pool(get_redis_settings())
    except Exception as e:
        logger.error(f"Failed to connect to Redis to tag split items: {e}")
        return
    try:
        for item in items:
            job = await redis.enqueue_job(
                "tag_item_image",
                str(item.id),
                str(image_service.get_image_path(item.image_path)),
                _queue_name=TAGGING_QUEUE,
            )
            item.ai_job_id = job.job_id
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to queue tagging for split items: {e}")
    finally:
        await redis.aclose()
