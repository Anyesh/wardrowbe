import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from arq import create_pool
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.item import (
    ArchiveRequest,
    BulkAnalyzeRequest,
    BulkAnalyzeResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkUploadResponse,
    BulkUploadResult,
    ItemCreate,
    ItemFilter,
    ItemImageResponse,
    ItemListResponse,
    ItemResponse,
    ItemUpdate,
    LogWashRequest,
    LogWearRequest,
    RemoveBackgroundRequest,
    ReorderImagesRequest,
    WashHistoryResponse,
)
from app.services.image_service import ImageService
from app.services.item_service import ItemService
from app.utils.auth import get_current_user
from app.workers.settings import get_redis_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/items", tags=["Items"])


@router.get("", response_model=ItemListResponse)
async def list_items(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: str | None = None,
    subtype: str | None = None,
    colors: str | None = None,
    status: str | None = None,
    favorite: bool | None = None,
    needs_wash: bool | None = None,
    is_archived: bool = False,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
) -> ItemListResponse:
    color_list = colors.split(",") if colors else None

    filters = ItemFilter(
        type=type,
        subtype=subtype,
        colors=color_list,
        status=status,
        favorite=favorite,
        needs_wash=needs_wash,
        is_archived=is_archived,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    item_service = ItemService(db)
    items, total = await item_service.get_list(
        user_id=current_user.id,
        filters=filters,
        page=page,
        page_size=page_size,
    )

    return ItemListResponse(
        items=[ItemResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    image: UploadFile = File(...),
    type: str | None = Form(None),  # Optional - AI will detect if not provided
    subtype: str | None = Form(None),
    name: str | None = Form(None),
    brand: str | None = Form(None),
    notes: str | None = Form(None),
    colors: str | None = Form(None),
    primary_color: str | None = Form(None),
    favorite: bool = Form(False),
) -> ItemResponse:
    # Validate and process image
    image_service = ImageService()
    item_service = ItemService(db)

    content = await image.read()
    content_type = image.content_type or "application/octet-stream"

    if not image_service.validate_image(content, content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: JPEG, PNG, WebP, HEIC",
        )

    # Compute hash and check for duplicates BEFORE storing
    try:
        image_hash = image_service.compute_phash(content, image.filename or "upload.jpg")
        existing = await item_service.find_duplicate_by_hash(current_user.id, image_hash)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Duplicate image detected. This item already exists in your wardrobe (ID: {existing.id})",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to compute image hash: {e}")
        # Continue without duplicate check if hash computation fails

    # Process and store image
    try:
        image_paths = await image_service.process_and_store(
            user_id=current_user.id,
            image_data=content,
            original_filename=image.filename or "upload.jpg",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None

    # Parse colors from comma-separated string
    color_list = colors.split(",") if colors else None

    # Create item - use "unknown" if type not provided (AI will detect)
    item_data = ItemCreate(
        type=type or "unknown",
        subtype=subtype,
        name=name,
        brand=brand,
        notes=notes,
        colors=color_list,
        primary_color=primary_color,
        favorite=favorite,
    )

    item = await item_service.create(
        user_id=current_user.id,
        item_data=item_data,
        image_paths=image_paths,
    )

    # Queue AI tagging job
    try:
        redis = await create_pool(get_redis_settings())
        try:
            full_image_path = f"{settings.storage_path}/{image_paths['image_path']}"
            await redis.enqueue_job(
                "tag_item_image",
                str(item.id),
                full_image_path,
                _queue_name="arq:tagging",
            )
            logger.info(f"Queued AI tagging job for item {item.id}")
        finally:
            await redis.aclose()
    except Exception as e:
        # Don't fail the upload if queueing fails
        logger.error(f"Failed to queue AI tagging job: {e}")

    return ItemResponse.model_validate(item)


@router.post("/bulk", response_model=BulkUploadResponse, status_code=status.HTTP_201_CREATED)
async def bulk_create_items(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    images: list[UploadFile] = File(..., description="Multiple image files to upload"),
) -> BulkUploadResponse:
    if len(images) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 20 images per bulk upload",
        )

    if len(images) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one image is required",
        )

    image_service = ImageService()
    item_service = ItemService(db)
    results: list[BulkUploadResult] = []
    successful = 0
    failed = 0

    # Create Redis pool once for all jobs
    redis = None
    try:
        redis = await create_pool(get_redis_settings())
    except Exception as e:
        logger.error(f"Failed to connect to Redis for bulk upload: {e}")

    try:
        for upload_file in images:
            filename = upload_file.filename or "unknown.jpg"

            try:
                # Read and validate image
                content = await upload_file.read()
                content_type = upload_file.content_type or "application/octet-stream"

                if not image_service.validate_image(content, content_type):
                    results.append(
                        BulkUploadResult(
                            filename=filename,
                            success=False,
                            error="Invalid image format. Supported: JPEG, PNG, WebP, HEIC",
                        )
                    )
                    failed += 1
                    continue

                # Check for duplicates BEFORE storing
                try:
                    image_hash = image_service.compute_phash(content, filename)
                    existing = await item_service.find_duplicate_by_hash(
                        current_user.id, image_hash
                    )
                    if existing:
                        results.append(
                            BulkUploadResult(
                                filename=filename,
                                success=False,
                                error="Duplicate image - already exists in wardrobe",
                            )
                        )
                        failed += 1
                        continue
                except Exception as e:
                    logger.warning(f"Failed to check duplicate for {filename}: {e}")
                    # Continue without duplicate check

                # Process and store image
                image_paths = await image_service.process_and_store(
                    user_id=current_user.id,
                    image_data=content,
                    original_filename=filename,
                )

                # Create item with unknown type (AI will detect)
                item_data = ItemCreate(type="unknown")
                item = await item_service.create(
                    user_id=current_user.id,
                    item_data=item_data,
                    image_paths=image_paths,
                )

                # Queue AI tagging job
                if redis:
                    try:
                        full_image_path = f"{settings.storage_path}/{image_paths['image_path']}"
                        await redis.enqueue_job(
                            "tag_item_image",
                            str(item.id),
                            full_image_path,
                            _queue_name="arq:tagging",
                        )
                        logger.info(f"Queued AI tagging for bulk item {item.id}")
                    except Exception as e:
                        logger.error(f"Failed to queue AI tagging for {item.id}: {e}")

                results.append(
                    BulkUploadResult(
                        filename=filename,
                        success=True,
                        item=ItemResponse.model_validate(item),
                    )
                )
                successful += 1

            except ValueError as e:
                results.append(
                    BulkUploadResult(
                        filename=filename,
                        success=False,
                        error=str(e),
                    )
                )
                failed += 1
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")
                results.append(
                    BulkUploadResult(
                        filename=filename,
                        success=False,
                        error="Failed to process image",
                    )
                )
                failed += 1
    finally:
        if redis:
            await redis.aclose()

    return BulkUploadResponse(
        total=len(images),
        successful=successful,
        failed=failed,
        results=results,
    )


@router.post("/bulk/delete", response_model=BulkDeleteResponse)
async def bulk_delete_items(
    request: BulkDeleteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BulkDeleteResponse:
    item_service = ItemService(db)
    image_service = ImageService()
    deleted = 0
    failed = 0
    errors: list[str] = []

    # Get item IDs to delete
    if request.select_all:
        # Get all items matching filters, excluding specified ones
        item_ids = await item_service.get_ids_by_filter(
            user_id=current_user.id,
            type_filter=request.filters.type if request.filters else None,
            search=request.filters.search if request.filters else None,
            is_archived=request.filters.is_archived
            if request.filters and request.filters.is_archived is not None
            else False,
            excluded_ids=list(request.excluded_ids) if request.excluded_ids else None,
        )
        logger.info(f"Bulk delete select_all: {len(item_ids)} items to delete")
    else:
        item_ids = request.item_ids or []

    for item_id in item_ids:
        try:
            item = await item_service.get_by_id(item_id, current_user.id)
            if not item:
                errors.append(f"Item {item_id} not found or not owned by user")
                failed += 1
                continue

            # Delete images
            image_service.delete_images(
                {
                    "image_path": item.image_path,
                    "medium_path": item.medium_path,
                    "thumbnail_path": item.thumbnail_path,
                }
            )

            await item_service.delete(item)
            deleted += 1
        except Exception as e:
            logger.error(f"Failed to delete item {item_id}: {e}")
            errors.append(f"Failed to delete item {item_id}")
            failed += 1

    return BulkDeleteResponse(deleted=deleted, failed=failed, errors=errors)


@router.post("/bulk/analyze", response_model=BulkAnalyzeResponse)
async def bulk_analyze_items(
    request: BulkAnalyzeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BulkAnalyzeResponse:
    from app.models.item import ItemStatus

    item_service = ItemService(db)
    queued = 0
    failed = 0
    errors: list[str] = []

    # Get item IDs to analyze
    if request.select_all:
        item_ids = await item_service.get_ids_by_filter(
            user_id=current_user.id,
            type_filter=request.filters.type if request.filters else None,
            search=request.filters.search if request.filters else None,
            is_archived=request.filters.is_archived
            if request.filters and request.filters.is_archived is not None
            else False,
            excluded_ids=list(request.excluded_ids) if request.excluded_ids else None,
        )
        logger.info(f"Bulk analyze select_all: {len(item_ids)} items to analyze")
    else:
        item_ids = request.item_ids or []

    # Collect valid items first
    items_to_process = []
    for item_id in item_ids:
        item = await item_service.get_by_id(item_id, current_user.id)
        if not item:
            errors.append(f"Item {item_id} not found or not owned by user")
            failed += 1
            continue
        items_to_process.append(item)

    # Set all items to processing status
    for item in items_to_process:
        item.status = ItemStatus.processing
    await db.commit()

    # Queue AI jobs
    redis = None
    try:
        redis = await create_pool(get_redis_settings())
    except Exception as e:
        logger.error(f"Failed to connect to Redis for bulk analyze: {e}")
        # Roll back status changes
        for item in items_to_process:
            item.status = ItemStatus.error
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect to job queue",
        ) from None

    try:
        for item in items_to_process:
            try:
                full_image_path = f"{settings.storage_path}/{item.image_path}"
                await redis.enqueue_job(
                    "tag_item_image",
                    str(item.id),
                    full_image_path,
                    _queue_name="arq:tagging",
                )
                logger.info(f"Queued AI re-analysis for item {item.id}")
                queued += 1
            except Exception as e:
                logger.error(f"Failed to queue AI analysis for {item.id}: {e}")
                errors.append(f"Failed to queue analysis for item {item.id}")
                item.status = ItemStatus.error
                failed += 1

        await db.commit()
    finally:
        if redis:
            await redis.aclose()

    return BulkAnalyzeResponse(queued=queued, failed=failed, errors=errors)


@router.get("/types")
async def get_item_types(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    item_service = ItemService(db)
    return await item_service.get_item_types(current_user.id)


@router.get("/colors")
async def get_color_distribution(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    item_service = ItemService(db)
    return await item_service.get_color_distribution(current_user.id)


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    return ItemResponse.model_validate(item)


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: UUID,
    item_data: ItemUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    item = await item_service.update(item, item_data)
    return ItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    # Delete images
    image_service = ImageService()
    image_service.delete_images(
        {
            "image_path": item.image_path,
            "medium_path": item.medium_path,
            "thumbnail_path": item.thumbnail_path,
        }
    )

    await item_service.delete(item)


@router.post("/{item_id}/archive", response_model=ItemResponse)
async def archive_item(
    item_id: UUID,
    request: ArchiveRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    item = await item_service.archive(item, request.reason)
    return ItemResponse.model_validate(item)


@router.post("/{item_id}/restore", response_model=ItemResponse)
async def restore_item(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    item = await item_service.restore(item)
    return ItemResponse.model_validate(item)


@router.post("/{item_id}/wear", response_model=ItemResponse)
async def log_item_wear(
    item_id: UUID,
    request: LogWearRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    # Use user's timezone to determine today if worn_at not provided
    if request.worn_at is None:
        try:
            user_tz = ZoneInfo(current_user.timezone or "UTC")
        except Exception:
            user_tz = ZoneInfo("UTC")
        worn_at = datetime.now(UTC).astimezone(user_tz).date()
    else:
        worn_at = request.worn_at

    await item_service.log_wear(
        item=item,
        worn_at=worn_at,
        occasion=request.occasion,
        notes=request.notes,
    )

    # Refresh to get updated wear_count
    await db.refresh(item)
    return ItemResponse.model_validate(item)


@router.get("/{item_id}/history")
async def get_item_history(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(10, ge=1, le=100),
) -> list[dict]:
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    from app.models.item import ItemHistory
    from app.models.outfit import Outfit, OutfitItem

    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    # Eagerly load outfit and its items for context
    result = await db.execute(
        sa_select(ItemHistory)
        .where(ItemHistory.item_id == item_id)
        .options(
            selectinload(ItemHistory.outfit)
            .selectinload(Outfit.items)
            .selectinload(OutfitItem.item)
        )
        .order_by(ItemHistory.worn_at.desc())
        .limit(limit)
    )
    history = list(result.scalars().all())

    entries = []
    for h in history:
        entry = {
            "id": str(h.id),
            "worn_at": h.worn_at.isoformat(),
            "occasion": h.occasion,
            "notes": h.notes,
        }
        if h.outfit:
            from app.utils.signed_urls import sign_image_url

            entry["outfit"] = {
                "id": str(h.outfit.id),
                "occasion": h.outfit.occasion,
                "items": [
                    {
                        "id": str(oi.item.id),
                        "type": oi.item.type,
                        "name": oi.item.name,
                        "thumbnail_url": sign_image_url(oi.item.thumbnail_path)
                        if oi.item.thumbnail_path
                        else None,
                    }
                    for oi in sorted(h.outfit.items, key=lambda x: x.position)
                ],
            }
        entries.append(entry)

    return entries


@router.get("/{item_id}/wear-stats")
async def get_item_wear_stats(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    return await item_service.get_wear_stats(item, current_user.timezone or "UTC")


@router.post("/{item_id}/wash", response_model=ItemResponse)
async def log_item_wash(
    item_id: UUID,
    request: LogWashRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    if item.wears_since_wash == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item is already clean (0 wears since last wash)",
        )

    # Use user's timezone to determine today if washed_at not provided
    if request.washed_at is None:
        try:
            user_tz = ZoneInfo(current_user.timezone or "UTC")
        except Exception:
            user_tz = ZoneInfo("UTC")
        washed_at = datetime.now(UTC).astimezone(user_tz).date()
    else:
        washed_at = request.washed_at

    await item_service.log_wash(
        item=item,
        washed_at=washed_at,
        method=request.method,
        notes=request.notes,
    )

    await db.refresh(item)
    return ItemResponse.model_validate(item)


@router.get("/{item_id}/wash-history", response_model=list[WashHistoryResponse])
async def get_item_wash_history(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(10, ge=1, le=100),
) -> list[WashHistoryResponse]:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    history = await item_service.get_wash_history(item_id, limit)
    return [WashHistoryResponse.model_validate(h) for h in history]


@router.post("/{item_id}/analyze", response_model=dict)
async def trigger_ai_analysis(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    try:
        # Set item status to processing so UI shows feedback
        from app.models.item import ItemStatus

        item.status = ItemStatus.processing
        await db.commit()

        redis = await create_pool(get_redis_settings())
        try:
            full_image_path = f"{settings.storage_path}/{item.image_path}"
            job = await redis.enqueue_job(
                "tag_item_image",
                str(item.id),
                full_image_path,
                _queue_name="arq:tagging",
            )
            logger.info(f"Queued AI re-analysis job for item {item.id}")
            return {"status": "queued", "job_id": job.job_id}
        finally:
            await redis.aclose()
    except Exception as e:
        logger.error(f"Failed to queue AI analysis job: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue AI analysis",
        ) from None


@router.post("/{item_id}/rotate", response_model=ItemResponse)
async def rotate_item_image(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    direction: str = Query(
        "cw",
        regex="^(cw|ccw)$",
        description="Rotation direction: cw (clockwise) or ccw (counter-clockwise)",
    ),
) -> ItemResponse:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    if not item.image_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item has no image",
        )

    try:
        image_service = ImageService()
        image_service.rotate_image(item.image_path, direction)
        await db.commit()
        await db.refresh(item)
        return ItemResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    except Exception as e:
        logger.error(f"Failed to rotate image: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to rotate image",
        ) from None


@router.post("/{item_id}/remove-background", response_model=ItemResponse)
async def remove_item_background(
    item_id: UUID,
    request: RemoveBackgroundRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    if not item.image_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item has no image",
        )

    hex_color = request.bg_color.lstrip("#")
    bg_color = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    try:
        image_service = ImageService()
        await asyncio.to_thread(image_service.remove_background, item.image_path, bg_color)
        await db.commit()
        await db.refresh(item)
        return ItemResponse.model_validate(item)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Background removal provider not available. "
            "For rembg: pip install rembg[cpu]. "
            "For HTTP provider: set BG_REMOVAL_PROVIDER=http and BG_REMOVAL_URL.",
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    except Exception as e:
        logger.error(f"Failed to remove background: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove background",
        ) from None


@router.post(
    "/{item_id}/images", response_model=ItemImageResponse, status_code=status.HTTP_201_CREATED
)
async def add_item_image(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    image: UploadFile = File(...),
) -> ItemImageResponse:
    from app.models.item import ItemImage

    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    # Check max images limit
    from sqlalchemy import func, select

    count_result = await db.execute(select(func.count()).where(ItemImage.item_id == item_id))
    current_count = count_result.scalar() or 0
    if current_count >= 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum of 4 additional images per item",
        )

    # Process image
    image_service_inst = ImageService()
    content = await image.read()
    content_type = image.content_type or "application/octet-stream"

    if not image_service_inst.validate_image(content, content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: JPEG, PNG, WebP, HEIC",
        )

    try:
        image_paths = await image_service_inst.process_and_store(
            user_id=current_user.id,
            image_data=content,
            original_filename=image.filename or "upload.jpg",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None

    item_image = ItemImage(
        item_id=item_id,
        image_path=image_paths["image_path"],
        thumbnail_path=image_paths.get("thumbnail_path"),
        medium_path=image_paths.get("medium_path"),
        position=current_count,
    )
    db.add(item_image)
    await db.flush()
    await db.refresh(item_image)

    return ItemImageResponse.model_validate(item_image)


@router.delete("/{item_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item_image(
    item_id: UUID,
    image_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    from sqlalchemy import select

    from app.models.item import ItemImage

    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    result = await db.execute(
        select(ItemImage).where(ItemImage.id == image_id, ItemImage.item_id == item_id)
    )
    item_image = result.scalar_one_or_none()

    if not item_image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )

    # Delete image files
    image_service_inst = ImageService()
    image_service_inst.delete_images(
        {
            "image_path": item_image.image_path,
            "medium_path": item_image.medium_path,
            "thumbnail_path": item_image.thumbnail_path,
        }
    )

    await db.delete(item_image)
    await db.flush()


@router.patch("/{item_id}/images/reorder", response_model=list[ItemImageResponse])
async def reorder_item_images(
    item_id: UUID,
    request: ReorderImagesRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ItemImageResponse]:
    from sqlalchemy import select

    from app.models.item import ItemImage

    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    result = await db.execute(select(ItemImage).where(ItemImage.item_id == item_id))
    images = {img.id: img for img in result.scalars().all()}

    for position, img_id in enumerate(request.image_ids):
        if img_id in images:
            images[img_id].position = position

    await db.flush()

    # Return in new order
    ordered = sorted(images.values(), key=lambda x: x.position)
    return [ItemImageResponse.model_validate(img) for img in ordered]


@router.post("/{item_id}/images/{image_id}/set-primary", response_model=ItemResponse)
async def set_primary_image(
    item_id: UUID,
    image_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ItemResponse:
    from sqlalchemy import select

    from app.models.item import ItemImage

    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    result = await db.execute(
        select(ItemImage).where(ItemImage.id == image_id, ItemImage.item_id == item_id)
    )
    item_image = result.scalar_one_or_none()

    if not item_image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found",
        )

    # Swap paths: current primary -> additional, additional -> primary
    old_primary = {
        "image_path": item.image_path,
        "thumbnail_path": item.thumbnail_path,
        "medium_path": item.medium_path,
    }

    item.image_path = item_image.image_path
    item.thumbnail_path = item_image.thumbnail_path
    item.medium_path = item_image.medium_path

    item_image.image_path = old_primary["image_path"]
    item_image.thumbnail_path = old_primary["thumbnail_path"]
    item_image.medium_path = old_primary["medium_path"]

    await db.flush()
    await db.refresh(item)
    return ItemResponse.model_validate(item)
