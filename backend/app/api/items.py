import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from arq import create_pool
from arq.jobs import Job
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.item import ClothingItem, ItemStatus, TaggedBy, TaggingStatus
from app.models.user import User
from app.schemas.item import (
    ArchiveRequest,
    BulkAnalyzeRequest,
    BulkAnalyzeResponse,
    BulkCancelAnalysisRequest,
    BulkCancelAnalysisResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkRemoveBackgroundRequest,
    BulkRemoveBackgroundResponse,
    BulkRotateRequest,
    BulkRotateResponse,
    BulkSelectionRequest,
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
    TaggingProgressResponse,
    WashHistoryResponse,
)
from app.services.image_service import ImageService
from app.services.item_service import ItemService
from app.utils.auth import get_current_user
from app.workers.queues import IMAGE_QUEUE, TAGGING_QUEUE, queue_for_kind
from app.workers.settings import get_redis_settings

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/items", tags=["Items"])

TAG_WRITEBACK_FIELDS = {"type", "subtype", "colors", "primary_color", "tags"}
_EMPTY_TAG_VALUES = (None, "", [], {})


def _has_tag_content(field: str, value: Any) -> bool:
    if field == "tags" and isinstance(value, dict):
        return any(v not in _EMPTY_TAG_VALUES for v in value.values())
    return value not in _EMPTY_TAG_VALUES


async def _resolve_bulk_item_ids(
    item_service: ItemService,
    user_id: UUID,
    request: BulkSelectionRequest,
    action: str,
) -> tuple[list[UUID], UUID | None, bool]:
    """Resolve one bulk request into at most max_bulk_action_count item ids.

    An explicit id list is the caller's to chunk, so an oversized one is
    rejected with the limit in the message. A select_all cannot be chunked by
    the client, which holds filters rather than ids, so it is walked here: one
    row beyond the cap is fetched to decide has_more without a second query.
    """
    limit = settings.max_bulk_action_count

    if not request.select_all:
        item_ids = request.item_ids or []
        if len(item_ids) > limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {limit} items per bulk action",
            )
        return item_ids, None, False

    filters = request.filters
    item_ids = await item_service.get_ids_by_filter(
        user_id=user_id,
        type_filter=filters.type if filters else None,
        search=filters.search if filters else None,
        is_archived=filters.is_archived if filters and filters.is_archived is not None else False,
        excluded_ids=list(request.excluded_ids) if request.excluded_ids else None,
        after_id=request.after_id,
        limit=limit + 1,
    )

    has_more = len(item_ids) > limit
    item_ids = item_ids[:limit]
    next_cursor = item_ids[-1] if has_more and item_ids else None
    logger.info(f"Bulk {action} select_all: {len(item_ids)} items, has_more={has_more}")
    return item_ids, next_cursor, has_more


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
    tagging_status: str | None = None,
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
        tagging_status=tagging_status,
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
    skip_ai: bool = Form(False),
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

    do_auto_tag = settings.effective_ai_vision_enabled and not skip_ai

    if do_auto_tag:
        # Commit before enqueuing: the worker runs in another process on its own
        # connection, so a job handed over while this transaction is still open
        # dequeues against a row it cannot see.
        await db.commit()
        try:
            redis = await create_pool(get_redis_settings())
            try:
                full_image_path = f"{settings.storage_path}/{image_paths['image_path']}"
                job = await redis.enqueue_job(
                    "tag_item_image",
                    str(item.id),
                    full_image_path,
                    _queue_name=TAGGING_QUEUE,
                )
                item.ai_job_id = job.job_id
                await db.commit()
                await db.refresh(item, attribute_names=["updated_at"])
                logger.info(f"Queued AI tagging job for item {item.id}")
            finally:
                await redis.aclose()
        except Exception as e:
            logger.error(f"Failed to queue AI tagging job: {e}")
    else:
        item = await item_service.mark_pending(item, set_ready=True)

    return ItemResponse.model_validate(item)


@router.post("/bulk", response_model=BulkUploadResponse, status_code=status.HTTP_201_CREATED)
async def bulk_create_items(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    images: list[UploadFile] = File(..., description="Multiple image files to upload"),
    skip_ai: bool = Form(False),
    upload_keys: list[str] | None = Form(
        None,
        description="Optional per-file idempotency keys, same order/length as images. "
        "Used by the durable upload queue so a retried chunk cannot create a "
        "duplicate item for a file already accepted.",
    ),
) -> BulkUploadResponse:
    if len(images) > settings.max_bulk_upload_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.max_bulk_upload_count} images per bulk upload",
        )

    if len(images) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one image is required",
        )

    if upload_keys is not None and len(upload_keys) != len(images):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="upload_keys must have the same length as images",
        )

    image_service = ImageService()
    item_service = ItemService(db)
    results: list[BulkUploadResult] = []
    successful = 0
    failed = 0
    # Captured once: a rollback later in this request (the upload_key conflict
    # branch) expires every ORM object the session has touched, including
    # current_user. Accessing current_user.id after that point would trigger a
    # synchronous lazy-reload outside the async context and crash with
    # MissingGreenlet - use this plain value everywhere instead.
    user_id = current_user.id

    do_auto_tag = settings.effective_ai_vision_enabled and not skip_ai

    redis = None
    if do_auto_tag:
        try:
            redis = await create_pool(get_redis_settings())
        except Exception as e:
            logger.error(f"Failed to connect to Redis for bulk upload: {e}")

    try:
        for idx, upload_file in enumerate(images):
            filename = upload_file.filename or "unknown.jpg"
            upload_key = upload_keys[idx] if upload_keys is not None else None

            try:
                # Fast path: this exact queued upload already succeeded (a retried
                # chunk from the durable upload queue). Skip re-reading/re-storing
                # the file entirely - the DB unique constraint below is the
                # correctness backstop for the race this can't close on its own.
                if upload_key is not None:
                    existing_by_key = await item_service.find_by_upload_key(user_id, upload_key)
                    if existing_by_key:
                        results.append(
                            BulkUploadResult(
                                filename=filename,
                                success=True,
                                item=ItemResponse.model_validate(existing_by_key),
                                duplicate=True,
                                existing_item_id=existing_by_key.id,
                            )
                        )
                        successful += 1
                        continue

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
                    existing = await item_service.find_duplicate_by_hash(user_id, image_hash)
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
                    user_id=user_id,
                    image_data=content,
                    original_filename=filename,
                )

                # Create item with unknown type (AI will detect)
                item_data = ItemCreate(type="unknown")
                item = await item_service.create(
                    user_id=user_id,
                    item_data=item_data,
                    image_paths=image_paths,
                    upload_key=upload_key,
                )

                if not do_auto_tag:
                    item = await item_service.mark_pending(item, set_ready=True)
                elif redis:
                    # Commit per item before handing the job over. Batching the
                    # commit to the end of the loop leaves every row invisible to
                    # the worker for the whole upload, which strands the batch in
                    # `processing` whenever the AI is fast enough to win the race.
                    await db.commit()
                    try:
                        full_image_path = f"{settings.storage_path}/{image_paths['image_path']}"
                        job = await redis.enqueue_job(
                            "tag_item_image",
                            str(item.id),
                            full_image_path,
                            _queue_name=TAGGING_QUEUE,
                        )
                        item.ai_job_id = job.job_id
                        await db.commit()
                        await db.refresh(item, attribute_names=["updated_at"])
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
            except IntegrityError:
                # Only raised by the upload_key unique constraint on this table -
                # a concurrent request (a re-entrant/multi-tab drain retry) won the
                # race and already created the item for this exact queued upload.
                # A flush-level integrity error poisons the session for the rest of
                # this request, so it must be rolled back before the loop continues,
                # and the files this iteration already wrote need cleanup or every
                # retry of the same race leaks orphaned images on disk.
                await db.rollback()
                image_service.delete_images(image_paths)
                existing_by_key = (
                    await item_service.find_by_upload_key(user_id, upload_key)
                    if upload_key is not None
                    else None
                )
                results.append(
                    BulkUploadResult(
                        filename=filename,
                        success=True,
                        item=ItemResponse.model_validate(existing_by_key)
                        if existing_by_key
                        else None,
                        duplicate=True,
                        existing_item_id=existing_by_key.id if existing_by_key else None,
                    )
                )
                successful += 1
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
    item_ids, next_cursor, has_more = await _resolve_bulk_item_ids(
        item_service, current_user.id, request, "delete"
    )

    for item_id in item_ids:
        try:
            item = await item_service.get_by_id(item_id, current_user.id)
            if not item:
                errors.append(f"Item {item_id} not found or not owned by user")
                failed += 1
                continue

            image_service.delete_images(
                {
                    "image_path": item.image_path,
                    "medium_path": item.medium_path,
                    "thumbnail_path": item.thumbnail_path,
                    "original_backup_path": item.original_image_path,
                }
            )

            await item_service.delete(item)
            deleted += 1
        except Exception as e:
            logger.error(f"Failed to delete item {item_id}: {e}")
            errors.append(f"Failed to delete item {item_id}")
            failed += 1

    return BulkDeleteResponse(
        deleted=deleted,
        failed=failed,
        errors=errors,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/bulk/analyze", response_model=BulkAnalyzeResponse)
async def bulk_analyze_items(
    request: BulkAnalyzeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BulkAnalyzeResponse:
    item_service = ItemService(db)
    queued = 0
    failed = 0
    errors: list[str] = []

    # Get item IDs to analyze
    item_ids, next_cursor, has_more = await _resolve_bulk_item_ids(
        item_service, current_user.id, request, "analyze"
    )

    # Collect valid items first
    items_to_process = []
    for item_id in item_ids:
        item = await item_service.get_by_id(item_id, current_user.id)
        if not item:
            errors.append(f"Item {item_id} not found or not owned by user")
            failed += 1
            continue
        items_to_process.append(item)

    if not settings.effective_ai_vision_enabled:
        for item in items_to_process:
            item.status = ItemStatus.ready
            item.tagging_status = TaggingStatus.pending
            item.tagged_by = None
            item.tagged_at = None
        await db.commit()
        return BulkAnalyzeResponse(
            queued=0,
            failed=failed,
            errors=errors,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    # Items already processing with a live job are skipped, not re-queued - a
    # double-submit must not orphan the first job or race its ai_started_at
    # write. An item stuck `processing` with no job (a previously-failed
    # enqueue) is not considered "already processing" and gets a fresh job.
    already_processing_ids = {
        item.id
        for item in items_to_process
        if item.status == ItemStatus.processing and item.ai_job_id
    }
    # Error-status items go through the same cooldown gate as the single-item
    # retry endpoint - deliberately NOT folded into `already_processing_ids`,
    # since the reasons differ (a live job vs. a cooldown) and the response
    # must report them separately (see `cooldown` below).
    error_candidates = [
        item
        for item in items_to_process
        if item.id not in already_processing_ids and item.status == ItemStatus.error
    ]
    to_queue = [
        item
        for item in items_to_process
        if item.id not in already_processing_ids and item.status != ItemStatus.error
    ]
    skipped = len(already_processing_ids)

    # Batched atomic claim - one round trip, not one UPDATE per item - for every
    # error-status candidate at once. Unclaimed candidates still genuinely in
    # `error` and within cooldown are reported honestly instead of silently
    # dropped or mislabeled as "already processing".
    claimed_job_ids: dict[UUID, str] = {}
    cooldown_count = 0
    cooldown_retry_after: int | None = None
    if error_candidates:
        claimed_job_ids, cooling_down = await item_service.claim_error_items_for_retry(
            [item.id for item in error_candidates], settings.ai_retry_cooldown_seconds
        )
        cooldown_count = len(cooling_down)
        if cooling_down:
            cooldown_retry_after = max(cooling_down.values())
        await db.commit()

    for item in to_queue:
        item.status = ItemStatus.processing
        item.ai_started_at = None
        item.processing_kind = None
    await db.commit()

    # Unified enqueue worklist: regular to_queue items get an arq-assigned job
    # id (read back after enqueue); claimed error items already have their job
    # id atomically assigned by the claim above and must reuse it via `_job_id`
    # (see the single-item retry endpoint for why - it closes the same
    # ai_job_id-ambiguity window this claim mechanism exists to prevent).
    to_enqueue: list[tuple[ClothingItem, str | None]] = [(item, None) for item in to_queue]
    to_enqueue += [
        (item, claimed_job_ids[item.id]) for item in error_candidates if item.id in claimed_job_ids
    ]

    # Queue AI jobs
    redis = None
    try:
        redis = await create_pool(get_redis_settings())
    except Exception as e:
        logger.error(f"Failed to connect to Redis for bulk analyze: {e}")
        # Roll back status changes for items this call actually touched - not the
        # full item list, or a transient outage would error out items that were
        # already processing with a live job untouched by this request.
        for item in to_queue:
            item.status = ItemStatus.error
        await db.commit()
        for item, job_id in to_enqueue:
            if job_id is not None:
                # Infra failure, not an AI failure - release without starting a
                # fresh cooldown (mirrors the single-item retry endpoint).
                await item_service.release_failed_claim(item.id, job_id)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect to job queue",
        ) from None

    try:
        for item, job_id in to_enqueue:
            try:
                full_image_path = f"{settings.storage_path}/{item.image_path}"
                job = await redis.enqueue_job(
                    "tag_item_image",
                    str(item.id),
                    full_image_path,
                    _job_id=job_id,
                    _queue_name=TAGGING_QUEUE,
                )
                if job is None:
                    raise RuntimeError("enqueue_job returned None")
                if job_id is None:
                    item.ai_job_id = job.job_id
                logger.info(f"Queued AI re-analysis for item {item.id}")
                queued += 1
            except Exception as e:
                logger.error(f"Failed to queue AI analysis for {item.id}: {e}")
                errors.append(f"Failed to queue analysis for item {item.id}")
                if job_id is not None:
                    await item_service.release_failed_claim(item.id, job_id)
                else:
                    item.status = ItemStatus.error
                failed += 1

        await db.commit()
    finally:
        if redis:
            await redis.aclose()

    return BulkAnalyzeResponse(
        queued=queued,
        failed=failed,
        skipped=skipped,
        cooldown=cooldown_count,
        retry_after_seconds=cooldown_retry_after,
        errors=errors,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/bulk/cancel-analysis", response_model=BulkCancelAnalysisResponse)
async def bulk_cancel_analysis(
    request: BulkCancelAnalysisRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BulkCancelAnalysisResponse:
    item_service = ItemService(db)
    errors: list[str] = []

    item_ids, next_cursor, has_more = await _resolve_bulk_item_ids(
        item_service, current_user.id, request, "cancel-analysis"
    )

    items_to_process = []
    for item_id in item_ids:
        item = await item_service.get_by_id(item_id, current_user.id)
        if not item:
            errors.append(f"Item {item_id} not found or not owned by user")
            continue
        items_to_process.append(item)

    # Only items still `processing` have anything in flight to abort; anything
    # else (ready, error) is reported as skipped rather than an error.
    processing_items = [item for item in items_to_process if item.status == ItemStatus.processing]
    skipped = len(items_to_process) - len(processing_items)

    if not processing_items:
        return BulkCancelAnalysisResponse(
            cancelled=0,
            skipped=skipped,
            errors=errors,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    redis = None
    try:
        redis = await create_pool(get_redis_settings())

        async def abort_job(item: ClothingItem) -> None:
            if not item.ai_job_id:
                return
            try:
                job = Job(item.ai_job_id, redis, _queue_name=queue_for_kind(item.processing_kind))
                await job.abort(timeout=5)
            except Exception as e:
                # The guarded UPDATE below protects against a stray worker
                # finishing after we've flipped status, so a failed/slow abort
                # here must not block the bulk status flip.
                logger.warning(f"Failed to abort AI job for item {item.id}: {e}")

        await asyncio.gather(*(abort_job(item) for item in processing_items))
    except Exception as e:
        logger.error(f"Failed to connect to job queue for bulk cancel-analysis: {e}")
        errors.append("Failed to connect to job queue; item statuses were not changed")
        return BulkCancelAnalysisResponse(
            cancelled=0,
            skipped=skipped,
            errors=errors,
            next_cursor=next_cursor,
            has_more=has_more,
        )
    finally:
        if redis:
            await redis.aclose()

    processing_ids = [item.id for item in processing_items]
    result = await db.execute(
        update(ClothingItem)
        .where(ClothingItem.id.in_(processing_ids), ClothingItem.status == ItemStatus.processing)
        .values(
            status=ItemStatus.ready,
            ai_job_id=None,
            ai_started_at=None,
            processing_kind=None,
        )
    )
    await db.commit()

    return BulkCancelAnalysisResponse(
        cancelled=result.rowcount,
        skipped=skipped,
        errors=errors,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/bulk/rotate", response_model=BulkRotateResponse)
async def bulk_rotate_items(
    request: BulkRotateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BulkRotateResponse:
    item_service = ItemService(db)
    queued = 0
    failed = 0
    errors: list[str] = []

    item_ids, next_cursor, has_more = await _resolve_bulk_item_ids(
        item_service, current_user.id, request, "rotate"
    )

    items_to_process: list[ClothingItem] = []
    for item_id in item_ids:
        item = await item_service.get_by_id(item_id, current_user.id)
        if not item:
            errors.append(f"Item {item_id} not found or not owned by user")
            failed += 1
            continue
        if not item.image_path:
            errors.append(f"Item {item_id} has no image")
            failed += 1
            continue
        items_to_process.append(item)

    # A concurrent job (tagging, background removal, an earlier rotate) may
    # still be writing image_path/medium_path/thumbnail_path for this item -
    # rotating it now would interleave two _save_all_sizes passes over the same
    # three files, so skip rather than queue.
    already_processing = [item for item in items_to_process if item.status == ItemStatus.processing]
    skipped = len(already_processing)
    to_queue = [item for item in items_to_process if item not in already_processing]

    for item in to_queue:
        item.status = ItemStatus.processing
        item.processing_kind = "rotate"
        # Clear any stale ai_started_at from a prior tagging run, otherwise the
        # frontend reads it as this job's elapsed time and shows a wildly wrong
        # duration for what is a sub-second rotation.
        item.ai_started_at = None
    await db.commit()

    redis = None
    try:
        redis = await create_pool(get_redis_settings())
    except Exception as e:
        logger.error(f"Failed to connect to Redis for bulk rotate: {e}")
        for item in to_queue:
            item.status = ItemStatus.error
            item.processing_kind = None
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect to job queue",
        ) from None

    try:
        for item in to_queue:
            try:
                job = await redis.enqueue_job(
                    "rotate_item_image_job",
                    str(item.id),
                    request.direction,
                    _queue_name=IMAGE_QUEUE,
                )
                if job is None:
                    raise RuntimeError("enqueue_job returned None")
                item.ai_job_id = job.job_id
                queued += 1
            except Exception as e:
                logger.error(f"Failed to queue rotation for {item.id}: {e}")
                errors.append(f"Failed to queue rotation for item {item.id}")
                item.status = ItemStatus.error
                item.processing_kind = None
                failed += 1
        await db.commit()
    finally:
        await redis.aclose()

    return BulkRotateResponse(
        queued=queued,
        failed=failed,
        skipped=skipped,
        errors=errors,
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.post("/bulk/remove-background", response_model=BulkRemoveBackgroundResponse)
async def bulk_remove_background_items(
    request: BulkRemoveBackgroundRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BulkRemoveBackgroundResponse:
    item_service = ItemService(db)
    queued = 0
    failed = 0
    errors: list[str] = []

    item_ids, next_cursor, has_more = await _resolve_bulk_item_ids(
        item_service, current_user.id, request, "remove-background"
    )

    items_to_process: list[ClothingItem] = []
    for item_id in item_ids:
        item = await item_service.get_by_id(item_id, current_user.id)
        if not item:
            errors.append(f"Item {item_id} not found or not owned by user")
            failed += 1
            continue
        if not item.image_path:
            errors.append(f"Item {item_id} has no image")
            failed += 1
            continue
        items_to_process.append(item)

    # Items already processing with a live job are skipped, not re-queued - a
    # second job racing the first would stomp each other's original-backup
    # write. An item stuck `processing` with no job (a previously-failed
    # enqueue) is not considered "already processing" and gets a fresh job,
    # mirroring bulk_analyze_items's skip check.
    already_processing = [
        item for item in items_to_process if item.status == ItemStatus.processing and item.ai_job_id
    ]
    skipped = len(already_processing)
    # original_image_path set means a previous run already flattened this
    # item's background - re-running the provider would stomp the existing
    # backup with a background-removed image of a background-removed image.
    already_done = [
        item
        for item in items_to_process
        if item not in already_processing and item.original_image_path
    ]
    already_done_count = len(already_done)
    to_queue = [
        item
        for item in items_to_process
        if item not in already_processing and item not in already_done
    ]

    for item in to_queue:
        item.status = ItemStatus.processing
        item.processing_kind = "background_removal"
        # Clear any stale ai_started_at left over from a prior tagging run -
        # otherwise the frontend reads it as this job's elapsed "analyzing"
        # time, showing a wildly wrong duration for what is actually a
        # few-second background-removal job.
        item.ai_started_at = None
    await db.commit()

    redis = None
    try:
        redis = await create_pool(get_redis_settings())
    except Exception as e:
        logger.error(f"Failed to connect to Redis for bulk remove-background: {e}")
        for item in to_queue:
            item.status = ItemStatus.error
            item.processing_kind = None
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect to job queue",
        ) from None

    try:
        for item in to_queue:
            try:
                job = await redis.enqueue_job(
                    "remove_item_background_job",
                    str(item.id),
                    request.bg_color,
                    _queue_name=IMAGE_QUEUE,
                )
                if job is None:
                    raise RuntimeError("enqueue_job returned None")
                item.ai_job_id = job.job_id
                queued += 1
            except Exception as e:
                logger.error(f"Failed to queue background removal for {item.id}: {e}")
                errors.append(f"Failed to queue background removal for item {item.id}")
                item.status = ItemStatus.error
                item.processing_kind = None
                failed += 1
        await db.commit()
    finally:
        if redis:
            await redis.aclose()

    return BulkRemoveBackgroundResponse(
        queued=queued,
        failed=failed,
        skipped=skipped,
        already_done=already_done_count,
        errors=errors,
        next_cursor=next_cursor,
        has_more=has_more,
    )


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


@router.get("/tagging-progress", response_model=TaggingProgressResponse)
async def get_tagging_progress(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TaggingProgressResponse:
    # Wardrobe-wide, not page-scoped: the client can only see the page it asked
    # for, so a 100-image upload showed at most "20 analyzing". Grouped in one
    # query on both status and whether the job has actually started, so the
    # queued/analyzing split can never drift against `processing` the way two
    # separate queries could under concurrent worker commits.
    result = await db.execute(
        select(ClothingItem.status, ClothingItem.ai_started_at.is_(None), func.count())
        .where(
            ClothingItem.user_id == current_user.id,
            ClothingItem.is_archived.is_(False),
            # Background-removal jobs reuse status=processing but aren't AI
            # tagging - exclude them so they don't pollute this banner's counts.
            ClothingItem.processing_kind.is_distinct_from("background_removal"),
        )
        .group_by(ClothingItem.status, ClothingItem.ai_started_at.is_(None))
    )
    queued = 0
    analyzing = 0
    failed = 0
    total = 0
    for status_value, is_null, n in result:
        status_str = str(getattr(status_value, "value", status_value))
        total += n
        if status_str == ItemStatus.processing.value:
            if is_null:
                queued += n
            else:
                analyzing += n
        elif status_str == ItemStatus.error.value:
            failed += n
    processing = queued + analyzing
    return TaggingProgressResponse(
        processing=processing,
        queued=queued,
        analyzing=analyzing,
        failed=failed,
        completed=total - processing - failed,
        total=total,
    )


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

    update_data = item_data.model_dump(exclude_unset=True)
    if any(_has_tag_content(f, update_data.get(f)) for f in TAG_WRITEBACK_FIELDS):
        item.tagging_status = TaggingStatus.tagged
        item.tagged_by = TaggedBy.manual
        item.tagged_at = datetime.now(UTC)

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

    image_service = ImageService()
    image_service.delete_images(
        {
            "image_path": item.image_path,
            "medium_path": item.medium_path,
            "thumbnail_path": item.thumbnail_path,
            "original_backup_path": item.original_image_path,
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

    if not settings.effective_ai_vision_enabled:
        await item_service.mark_pending(item, set_ready=True)
        await db.commit()
        return {"status": "deferred", "reason": "vision disabled"}

    if item.status == ItemStatus.processing and item.ai_job_id:
        # Dedup: a live job already owns this item. If ai_job_id is None instead,
        # a prior enqueue silently failed and there's nothing to dedup against -
        # fall through to a fresh enqueue below.
        return {"status": "already_queued", "job_id": item.ai_job_id}

    if item.status == ItemStatus.error:
        # Cooldown gate: internal retry (ai_service.py's fallback loop, arq's own
        # backoff) already exhausted itself before this item reached `error`, so
        # an instant manual retry only "works" by luck. Gated separately from the
        # branch above - every other status keeps the unconditional enqueue below
        # untouched.
        image_path = item.image_path
        job_id, retry_after_seconds = await item_service.claim_error_item_for_retry(
            item.id, settings.ai_retry_cooldown_seconds
        )
        if job_id is None:
            if retry_after_seconds is not None:
                return {"status": "cooldown", "retry_after_seconds": retry_after_seconds}
            # Lost a concurrent claim on this same item - report its real
            # current state instead of a stale in-memory guess.
            current = await item_service.get_by_id(item_id, current_user.id)
            return {
                "status": "already_queued",
                "job_id": current.ai_job_id if current else None,
            }

        await db.commit()
        try:
            redis = await create_pool(get_redis_settings())
            try:
                full_image_path = f"{settings.storage_path}/{image_path}"
                enqueued = await redis.enqueue_job(
                    "tag_item_image",
                    str(item_id),
                    full_image_path,
                    _job_id=job_id,
                    _queue_name=TAGGING_QUEUE,
                )
                if enqueued is None:
                    raise RuntimeError("enqueue_job returned None")
                logger.info(f"Queued AI re-analysis job for item {item_id}")
                return {"status": "queued", "job_id": job_id}
            finally:
                await redis.aclose()
        except Exception as e:
            logger.error(f"Failed to queue AI analysis job: {e}")
            await item_service.release_failed_claim(item_id, job_id)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to queue AI analysis",
            ) from None

    try:
        item.status = ItemStatus.processing
        item.ai_started_at = None
        item.processing_kind = None
        await db.commit()

        redis = await create_pool(get_redis_settings())
        try:
            full_image_path = f"{settings.storage_path}/{item.image_path}"
            job = await redis.enqueue_job(
                "tag_item_image",
                str(item.id),
                full_image_path,
                _queue_name=TAGGING_QUEUE,
            )
            item.ai_job_id = job.job_id
            await db.commit()
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


@router.post("/{item_id}/retag", response_model=ItemResponse)
async def retag_item(
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

    item = await item_service.mark_pending(item)
    return ItemResponse.model_validate(item)


@router.post("/{item_id}/cancel-analysis", response_model=ItemResponse)
async def cancel_item_analysis(
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

    if item.status != ItemStatus.processing:
        return ItemResponse.model_validate(item)

    if item.ai_job_id:
        redis = None
        try:
            redis = await create_pool(get_redis_settings())
            job = Job(item.ai_job_id, redis, _queue_name=queue_for_kind(item.processing_kind))
            await job.abort(timeout=5)
        except Exception as e:
            # abort failing or timing out must not block the status flip below;
            # the guarded UPDATE in update_item_status_to_error protects against
            # a stray worker finishing this job after we've already flipped it.
            logger.warning(f"Failed to abort AI job for item {item_id}: {e}")
        finally:
            if redis:
                await redis.aclose()

    await db.execute(
        update(ClothingItem)
        .where(ClothingItem.id == item.id, ClothingItem.status == ItemStatus.processing)
        .values(status=ItemStatus.ready, ai_job_id=None, ai_started_at=None, processing_kind=None)
    )
    await db.commit()
    # updated_at is recomputed by a DB-side trigger on UPDATE, so the Core update()
    # above leaves the in-memory value stale; refresh it explicitly alongside the
    # columns we changed instead of a bare refresh(), which would also expire the
    # already eager-loaded additional_images relationship and blow up serialization.
    await db.refresh(
        item,
        attribute_names=["status", "ai_job_id", "ai_started_at", "processing_kind", "updated_at"],
    )
    return ItemResponse.model_validate(item)


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
        # to_thread because rotate_image is a blocking decode/resize/encode
        # cycle; calling it directly stalls the whole event loop for its
        # duration, which on a large image is seconds of dead API.
        await asyncio.to_thread(image_service.rotate_image, item.image_path, direction)
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

    if item.status == ItemStatus.processing and item.ai_job_id:
        # A queued or running job (tagging or another background-removal run)
        # owns image_path/medium_path/thumbnail_path - racing it here would
        # stomp whichever write lands last.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Item has a background job in progress",
        )

    recovering_from_error = (
        item.status == ItemStatus.error and item.processing_kind == "background_removal"
    )

    hex_color = request.bg_color.lstrip("#")
    bg_color = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    try:
        image_service = ImageService()
        result = await asyncio.to_thread(image_service.remove_background, item.image_path, bg_color)
        item.original_image_path = result["original_backup_path"]
        if recovering_from_error:
            item.status = ItemStatus.ready
            item.processing_kind = None
            item.ai_started_at = None
        await db.commit()
        await db.refresh(
            item,
            attribute_names=[
                "original_image_path",
                "status",
                "processing_kind",
                "ai_started_at",
                "updated_at",
            ],
        )
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


@router.post("/{item_id}/restore-original", response_model=ItemResponse)
async def restore_item_original(
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

    if not item.original_image_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No original image to restore",
        )

    try:
        image_service = ImageService()
        await asyncio.to_thread(
            image_service.restore_original, item.image_path, item.original_image_path
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    except Exception as e:
        logger.error(f"Failed to restore original image: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to restore original image",
        ) from None

    item.original_image_path = None
    await db.commit()
    await db.refresh(item, attribute_names=["original_image_path", "updated_at"])
    return ItemResponse.model_validate(item)


@router.put("/{item_id}/image", response_model=ItemResponse)
async def replace_item_image(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    image: UploadFile = File(...),
) -> ItemResponse:
    item_service = ItemService(db)
    item = await item_service.get_by_id(item_id, current_user.id)

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )

    image_service = ImageService()
    content = await image.read()
    content_type = image.content_type or "application/octet-stream"

    if not image_service.validate_image(content, content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: JPEG, PNG, WebP, HEIC",
        )

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

    old_paths = {
        "image_path": item.image_path,
        "medium_path": item.medium_path,
        "thumbnail_path": item.thumbnail_path,
        "original_backup_path": item.original_image_path,
    }

    item.image_path = image_paths["image_path"]
    item.medium_path = image_paths["medium_path"]
    item.thumbnail_path = image_paths["thumbnail_path"]
    item.image_hash = image_paths["image_hash"]
    item.original_image_path = None
    await db.commit()
    await db.refresh(
        item,
        attribute_names=[
            "image_path",
            "medium_path",
            "thumbnail_path",
            "image_hash",
            "original_image_path",
            "updated_at",
        ],
    )

    # Old files are removed only after the new paths are committed, so a failed
    # commit cannot leave the item pointing at deleted files
    image_service.delete_images(old_paths)

    return ItemResponse.model_validate(item)


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
