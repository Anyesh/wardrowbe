import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from arq import create_pool
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from app.config import get_settings
from app.database import DbSession
from app.models.try_on import OutfitTryOn, TryOnPhoto, TryOnStatus
from app.models.user import User
from app.services.image_service import IMAGE_MIME_TYPES, ImageService
from app.services.try_on_service import (
    ERROR_DAILY_LIMIT,
    ERROR_ITEM_IMAGE_MISSING,
    ERROR_NO_PHOTO,
    compute_cache_key,
    is_pending_fresh,
    load_outfit,
    load_photo,
    outfit_garments,
)
from app.utils.auth import get_current_user
from app.utils.rate_limit import check_rate_limit, rate_limit_by_user
from app.utils.signed_urls import sign_optional
from app.utils.uploads import UploadTooLargeError, read_upload_within_limit
from app.workers.queues import TAGGING_QUEUE
from app.workers.settings import get_redis_settings

logger = logging.getLogger(__name__)

DAILY_WINDOW_SECONDS = 24 * 60 * 60


def require_try_on_enabled() -> None:
    if not get_settings().try_on_enabled:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Outfit try-on is not enabled", "TRY_ON_DISABLED"
        )


router = APIRouter(tags=["Try-on"], dependencies=[Depends(require_try_on_enabled)])


def _error(status_code: int, message: str, error_code: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"message": message, "error_code": error_code}
    )


class TryOnPhotoResponse(BaseModel):
    image_url: str
    medium_url: str | None = None
    created_at: datetime
    updated_at: datetime


class TryOnResponse(BaseModel):
    status: TryOnStatus
    image_url: str | None = None
    medium_url: str | None = None
    error_code: str | None = None
    created_at: datetime
    stale: bool = False


def _photo_response(photo: TryOnPhoto) -> TryOnPhotoResponse:
    return TryOnPhotoResponse(
        image_url=sign_optional(photo.image_path),  # type: ignore[arg-type]
        medium_url=sign_optional(photo.medium_path, photo.image_path),
        created_at=photo.created_at,
        updated_at=photo.updated_at,
    )


def _try_on_response(try_on: OutfitTryOn, stale: bool) -> TryOnResponse:
    ready = try_on.status == TryOnStatus.ready
    return TryOnResponse(
        status=try_on.status,
        image_url=sign_optional(try_on.image_path) if ready else None,
        medium_url=sign_optional(try_on.medium_path, try_on.image_path) if ready else None,
        error_code=try_on.error_code,
        created_at=try_on.updated_at,
        stale=stale,
    )


async def _delete_all_try_ons(db: DbSession, user_id: UUID) -> None:
    """Delete the user's try-ons; their files go once the transaction commits (models/try_on)."""
    result = await db.execute(select(OutfitTryOn).where(OutfitTryOn.user_id == user_id))
    for try_on in result.scalars().all():
        await db.delete(try_on)


@router.get("/users/me/try-on-photo", response_model=TryOnPhotoResponse)
async def get_try_on_photo(
    db: DbSession, current_user: Annotated[User, Depends(get_current_user)]
) -> TryOnPhotoResponse:
    photo = await load_photo(db, current_user.id)
    if not photo:
        raise _error(status.HTTP_404_NOT_FOUND, "No try-on photo", ERROR_NO_PHOTO)
    return _photo_response(photo)


@router.put("/users/me/try-on-photo", response_model=TryOnPhotoResponse)
async def put_try_on_photo(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    image: UploadFile = File(..., description="Full-length photo of the user"),
) -> TryOnPhotoResponse:
    max_mb = get_settings().max_upload_size_mb
    try:
        content = await read_upload_within_limit(image, max_mb)
    except UploadTooLargeError as e:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(e)) from None

    image_service = ImageService()
    content_type = image.content_type or "application/octet-stream"
    if not image_service.validate_image(content, content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: JPEG, PNG, WebP, HEIC",
        )

    extension = next(
        (ext for ext, mime in IMAGE_MIME_TYPES.items() if mime == content_type), ".jpg"
    )
    try:
        paths = await asyncio.to_thread(
            image_service.store_try_on_image, current_user.id, content, extension
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    photo = await load_photo(db, current_user.id)
    old_paths = [photo.image_path, photo.medium_path] if photo else []
    try:
        if photo:
            photo.image_path = paths["image_path"]
            photo.medium_path = paths["medium_path"]
            photo.content_hash = paths["content_hash"]
        else:
            photo = TryOnPhoto(
                user_id=current_user.id,
                image_path=paths["image_path"],
                medium_path=paths["medium_path"],
                content_hash=paths["content_hash"],
            )
            db.add(photo)
        # Generated images were drawn from the old photo.
        await _delete_all_try_ons(db, current_user.id)
        await db.commit()
        await db.refresh(photo)
    except Exception:
        await db.rollback()
        image_service.delete_images({p: p for p in (paths["image_path"], paths["medium_path"])})
        raise

    image_service.delete_images({p: p for p in old_paths if p})
    return _photo_response(photo)


@router.delete("/users/me/try-on-photo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_try_on_photo(
    db: DbSession, current_user: Annotated[User, Depends(get_current_user)]
) -> None:
    photo = await load_photo(db, current_user.id)
    if not photo:
        return
    old_paths = {p: p for p in (photo.image_path, photo.medium_path) if p}
    await _delete_all_try_ons(db, current_user.id)
    await db.delete(photo)
    await db.commit()
    ImageService().delete_images(old_paths)


async def _get_outfit_or_404(db: DbSession, outfit_id: UUID, user: User):
    outfit = await load_outfit(db, outfit_id, user.id)
    if not outfit:
        raise _error(status.HTTP_404_NOT_FOUND, "Outfit not found", "OUTFIT_NOT_FOUND")
    return outfit


async def enqueue_try_on(outfit_id: UUID) -> None:
    redis = await create_pool(get_redis_settings())
    try:
        job = await redis.enqueue_job("generate_try_on", str(outfit_id), _queue_name=TAGGING_QUEUE)
        if job is None:
            raise RuntimeError("enqueue_job returned None")
    finally:
        await redis.aclose()


async def _check_daily_limit(user_id: UUID) -> None:
    # Counted in Redis (a fixed 24h window from the first generation), because a regenerate
    # overwrites its outfit's row and the database alone would not see repeat generations.
    try:
        await check_rate_limit(
            f"rate_limit:try_on_daily:user:{user_id}",
            get_settings().ai_image_daily_limit,
            DAILY_WINDOW_SECONDS,
        )
    except HTTPException:
        raise _error(
            status.HTTP_429_TOO_MANY_REQUESTS, "Daily try-on limit reached", ERROR_DAILY_LIMIT
        ) from None


@router.get("/outfits/{outfit_id}/try-on", response_model=TryOnResponse)
async def get_outfit_try_on(
    outfit_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> TryOnResponse:
    outfit = await _get_outfit_or_404(db, outfit_id, current_user)
    try_on = outfit.try_on
    if not try_on:
        raise _error(status.HTTP_404_NOT_FOUND, "No try-on for this outfit", "TRY_ON_NONE")
    photo = await load_photo(db, current_user.id)
    stale = True
    if photo:
        key = compute_cache_key(photo, outfit_garments(outfit), ImageService())
        stale = key != try_on.cache_key
    return _try_on_response(try_on, stale)


@router.post(
    "/outfits/{outfit_id}/try-on",
    response_model=TryOnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_outfit_try_on(
    outfit_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    regenerate: Annotated[bool, Query()] = False,
) -> TryOnResponse:
    outfit = await _get_outfit_or_404(db, outfit_id, current_user)
    photo = await load_photo(db, current_user.id)
    if not photo:
        raise _error(status.HTTP_409_CONFLICT, "Add a try-on photo first", ERROR_NO_PHOTO)

    garments = outfit_garments(outfit)
    image_service = ImageService()
    cache_key = compute_cache_key(photo, garments, image_service)
    try_on = outfit.try_on

    if (
        try_on
        and not regenerate
        and try_on.status == TryOnStatus.ready
        and try_on.cache_key == cache_key
    ):
        return _try_on_response(try_on, stale=False)

    if try_on and try_on.status == TryOnStatus.pending and is_pending_fresh(try_on.started_at):
        raise _error(
            status.HTTP_409_CONFLICT, "A try-on is already being drawn", "TRY_ON_IN_PROGRESS"
        )

    if not garments or any(not g.image_path for g in garments):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Every item needs a photo",
            ERROR_ITEM_IMAGE_MISSING,
        )

    await rate_limit_by_user(current_user.id, "try_on", max_requests=5, window_seconds=60)
    await _check_daily_limit(current_user.id)

    now = datetime.now(UTC)
    if not try_on:
        try_on = OutfitTryOn(outfit_id=outfit.id, user_id=current_user.id, cache_key=cache_key)
        db.add(try_on)
    try_on.status = TryOnStatus.pending
    try_on.error_code = None
    try_on.cache_key = cache_key
    try_on.started_at = now
    try_on.completed_at = None
    # Commit before enqueuing: the worker reads on its own connection.
    await db.commit()
    await db.refresh(try_on)

    try:
        await enqueue_try_on(outfit.id)
    except Exception as e:
        logger.error("Failed to queue try-on job: %s", type(e).__name__)
        try_on.status = TryOnStatus.failed
        try_on.error_code = "TRY_ON_FAILED"
        try_on.completed_at = datetime.now(UTC)
        await db.commit()
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Could not queue the try-on", "TRY_ON_FAILED"
        ) from None

    return _try_on_response(try_on, stale=False)


@router.delete("/outfits/{outfit_id}/try-on", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outfit_try_on(
    outfit_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    outfit = await _get_outfit_or_404(db, outfit_id, current_user)
    if outfit.try_on:
        await db.delete(outfit.try_on)
        await db.commit()
