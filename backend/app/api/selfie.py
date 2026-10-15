import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import DbSession
from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.schemas.item import ItemResponse
from app.services.ai_service import AIDisabledError, get_ai_service
from app.services.image_service import ImageService
from app.services.selfie_service import match_selfie
from app.utils.auth import get_current_user
from app.utils.uploads import UploadTooLargeError, read_upload_within_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/selfie", tags=["Selfie"])


class SelfieResponse(BaseModel):
    matches: list[ItemResponse]
    considered: int


@router.post("", response_model=SelfieResponse)
async def recognise_outfit(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    image: UploadFile = File(...),
) -> SelfieResponse:
    """Suggest which wardrobe items are in a photo; nothing is logged until the user confirms
    (the page then logs each confirmed item through POST /items/{id}/wear)."""
    try:
        content = await read_upload_within_limit(image, get_settings().max_upload_size_mb)
    except UploadTooLargeError as e:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(e)) from None
    if not ImageService().validate_image(content, image.content_type or "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: JPEG, PNG, WebP, HEIC",
        )
    try:
        ai = get_ai_service()
    except AIDisabledError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The AI is turned off"
        ) from None

    result = await db.execute(
        select(ClothingItem)
        .where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.status == ItemStatus.ready,
                ClothingItem.is_archived.is_(False),
            )
        )
        .options(selectinload(ClothingItem.additional_images))
        .order_by(ClothingItem.last_worn_at.desc().nulls_last(), ClothingItem.created_at.desc())
    )
    items = [i for i in result.scalars().all() if i.type and i.type != "unknown"]

    with tempfile.TemporaryDirectory() as folder:
        photo = Path(folder) / "selfie"
        photo.write_bytes(content)
        try:
            matches = await match_selfie(ai, photo, items)
        except Exception as e:
            logger.warning(f"Selfie recognition failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The AI could not read the photo. Try again in a moment.",
            ) from None

    return SelfieResponse(
        matches=[ItemResponse.model_validate(i) for i in matches], considered=len(items)
    )
