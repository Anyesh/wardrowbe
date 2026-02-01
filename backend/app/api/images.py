import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.services.family_service import FamilyService
from app.services.image_service import ImageService
from app.utils.auth import get_current_user_optional
from app.utils.signed_urls import verify_signature

router = APIRouter(prefix="/images", tags=["Images"])

FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+\.(jpg|jpeg|png|webp)$")


@router.get("/{user_id}/{filename}")
async def get_image(
    user_id: str,
    filename: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_current_user_optional)] = None,
    expires: str | None = Query(None),
    sig: str | None = Query(None),
) -> FileResponse:
    try:
        UUID(user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        ) from e

    if not FILENAME_PATTERN.match(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename format",
        )

    path = f"{user_id}/{filename}"
    can_access = False

    if expires and sig:
        if verify_signature(path, expires, sig):
            can_access = True

    if not can_access and current_user:
        if str(current_user.id) == user_id:
            can_access = True
        elif current_user.family_id:
            family_service = FamilyService(db)
            family = await family_service.get_by_id(current_user.family_id)
            if family:
                family_user_ids = [str(m.id) for m in family.members]
                can_access = user_id in family_user_ids

    if not can_access:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access denied",
        )

    image_service = ImageService()
    image_path = image_service.get_image_path(path)

    if not image_path.resolve().is_relative_to(image_service.storage_path.resolve()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path",
        )

    if not image_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )

    ext = filename.rsplit(".", 1)[-1].lower()
    content_types = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }
    content_type = content_types.get(ext, "image/jpeg")

    return FileResponse(
        path=str(image_path),
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600, must-revalidate",
        },
    )
