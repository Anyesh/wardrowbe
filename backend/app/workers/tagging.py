import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from arq import Retry
from sqlalchemy import select, update

from app.config import get_settings
from app.models.item import ClothingItem, ItemStatus, TaggedBy, TaggingStatus
from app.models.preference import UserPreference
from app.services.ai_service import AIService, ClothingTags
from app.workers.db import get_db_session

logger = logging.getLogger(__name__)

TAGGING_MAX_TRIES = 3

# Margin left below job_timeout so the in-job call budget always fires before
# arq's own kill (which does not retry - see _tagging_call_budget).
CALL_BUDGET_MARGIN_SECONDS = 30
MIN_CALL_BUDGET_SECONDS = 30


class ItemVanishedError(Exception):
    """The item row is not visible to this worker's connection.

    Almost always means the producing request has not committed yet, so the job
    must be retried rather than dropped: returning here would leave the item
    stuck in `processing` until the stale sweep condemns it.
    """


def _is_final_attempt(ctx: dict) -> bool:
    return int(ctx.get("job_try") or 1) >= TAGGING_MAX_TRIES


def retry_delay_seconds(ctx: dict) -> int:
    # Exponential, so a provider that is rate limiting or restarting gets room to
    # recover instead of being hit again immediately.
    return min(2 ** int(ctx.get("job_try") or 1) * 5, 120)


def worker_job_timeout_seconds() -> int:
    settings = get_settings()
    return max(settings.ai_timeout * settings.ai_max_retries + 60, 600)


def _tagging_call_budget(ai_service: AIService) -> float:
    # No fixed formula bounds the real worst case (per-user endpoint count is
    # unknowable at import time), so this is an upper bound clamped to
    # job_timeout, not an exact figure - it deliberately omits inter-retry
    # backoff sleeps. What matters is that it always fires before arq's own
    # job_timeout kill, since that kill does not retry the job at all.
    settings = get_settings()
    endpoint_count = len(getattr(ai_service, "_endpoints", None) or [None])
    raw = endpoint_count * settings.ai_max_retries * 2 * settings.ai_timeout
    return max(
        MIN_CALL_BUDGET_SECONDS,
        min(raw, worker_job_timeout_seconds() - CALL_BUDGET_MARGIN_SECONDS),
    )


async def _clear_ai_started_at(ctx: dict, item_id: str) -> None:
    db = get_db_session(ctx)
    try:
        # Guarded so this only touches a row still in `processing` - a row already
        # moved to a terminal state (cancelled -> ready, or a final-attempt error)
        # must not be re-touched. Not a race guard between this attempt and the
        # next: arq only starts attempt N+1 after this write's enclosing exception
        # has propagated and the retry defer has elapsed, so there is no window
        # where two attempts' writes could interleave.
        await db.execute(
            update(ClothingItem)
            .where(ClothingItem.id == UUID(item_id), ClothingItem.status == ItemStatus.processing)
            .values(ai_started_at=None)
        )
        await db.commit()
    finally:
        await db.close()


async def clear_ai_started_at(ctx: dict, item_id: str) -> None:
    # Best-effort: this runs from an exception handler, so a failure here must
    # never replace the exception already in flight. Bounded so a failing write
    # can't hang arq's run_job wait indefinitely.
    try:
        await asyncio.wait_for(_clear_ai_started_at(ctx, item_id), timeout=5)
    except Exception:
        pass


def tags_to_item_fields(tags: ClothingTags, raw_response: str | None = None) -> dict[str, Any]:
    """Convert ClothingTags to item database fields."""
    # Build the tags JSONB object for frontend display
    tags_jsonb = {
        "colors": tags.colors or [],
        "pattern": tags.pattern,
        "material": tags.material,
        "style": tags.style or [],
        "season": tags.season or [],
        "formality": tags.formality,
        "fit": tags.fit,
        "occasion": tags.occasion or [],
        "brand": tags.brand,
        "condition": tags.condition,
        "features": tags.features or [],
    }
    if tags.logprobs_confidence is not None:
        tags_jsonb["logprobs_confidence"] = tags.logprobs_confidence

    fields = {
        "type": tags.type,
        "subtype": tags.subtype,
        "primary_color": tags.primary_color,
        "colors": tags.colors,
        "pattern": tags.pattern,
        "material": tags.material,
        "style": tags.style,
        "formality": tags.formality,
        "season": tags.season,
        "tags": tags_jsonb,  # Populate the tags JSONB field for frontend
        "ai_processed": True,
        "ai_confidence": tags.confidence,
        "ai_description": tags.description,  # Human-readable description
        "status": ItemStatus.ready,
        "tagging_status": TaggingStatus.tagged,
        "tagged_by": TaggedBy.auto,
        "tagged_at": datetime.now(UTC),
    }
    if raw_response:
        fields["ai_raw_response"] = {"raw_text": raw_response}
    return fields


async def mark_item_tagging_skipped(ctx: dict, item_id: str) -> None:
    db = get_db_session(ctx)
    try:
        result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
        item = result.scalar_one_or_none()
        if item and item.status == ItemStatus.processing:
            item.status = ItemStatus.ready
            item.tagging_status = TaggingStatus.pending
            await db.commit()
    finally:
        await db.close()


async def update_item_status_to_error(ctx: dict, item_id: str, error_msg: str) -> None:
    try:
        db = get_db_session(ctx)
        try:
            # Guarded: only flip status if still processing, because an orphaned job
            # (worker crash, or a job the user already cancelled) must not un-ready or
            # re-error an item the user has already moved past.
            await db.execute(
                update(ClothingItem)
                .where(
                    ClothingItem.id == UUID(item_id), ClothingItem.status == ItemStatus.processing
                )
                .values(
                    status=ItemStatus.error,
                    ai_raw_response={"error": error_msg},
                    ai_failed_at=datetime.now(UTC),
                )
            )
            await db.commit()
        finally:
            await db.close()
    except Exception as e:
        logger.error(f"Failed to update item {item_id} status to error: {e}")


async def tag_item_image(ctx: dict, item_id: str, image_path: str) -> dict[str, Any]:
    """
    Analyze an item's image and update it with AI-generated tags.

    Args:
        ctx: arq context
        item_id: UUID of the item to tag
        image_path: Path to the image file

    Returns:
        Dict with status and tags
    """
    logger.info(f"Starting AI tagging for item {item_id}")

    if not get_settings().effective_ai_vision_enabled:
        logger.info(f"Internal vision disabled; skipping AI tagging for item {item_id}")
        await mark_item_tagging_skipped(ctx, item_id)
        return {"status": "skipped", "reason": "vision disabled", "item_id": item_id}

    try:
        # Verify image exists
        path = Path(image_path)
        if not path.exists():
            error_msg = f"Image not found: {image_path}"
            logger.error(error_msg)
            await update_item_status_to_error(ctx, item_id, error_msg)
            return {"status": "error", "error": "Image not found"}

        # Get user's AI endpoints from preferences, and mark this attempt as started
        ai_endpoints = None
        db = get_db_session(ctx)
        try:
            # Get the item to find user_id
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()
            if item is None:
                raise ItemVanishedError(f"Item {item_id} not visible to worker")

            # Overwritten on every attempt (not set-once), so a retry's backoff wait
            # reads as "queued for retry," not "still analyzing."
            item.ai_started_at = datetime.now(UTC)

            pref_result = await db.execute(
                select(UserPreference).where(UserPreference.user_id == item.user_id)
            )
            prefs = pref_result.scalar_one_or_none()
            if prefs and prefs.ai_endpoints:
                ai_endpoints = prefs.ai_endpoints
                logger.info(
                    f"Using {len(ai_endpoints)} custom AI endpoints for user {item.user_id}"
                )

            await db.commit()
        finally:
            await db.close()

        # Analyze with AI (uses custom endpoints if available)
        ai_service = AIService(endpoints=ai_endpoints)
        tags = await asyncio.wait_for(
            ai_service.analyze_image(path), timeout=_tagging_call_budget(ai_service)
        )

        logger.info(
            f"AI analysis complete for item {item_id}: type={tags.type}, color={tags.primary_color}"
        )

        # Update item in database
        db = get_db_session(ctx)
        try:
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()

            if item is None:
                raise ItemVanishedError(f"Item {item_id} not visible to worker")

            # Unguarded by design: worst case after a cancel this backfills tags onto an
            # item the user already moved past, which is harmless (unlike the error path).
            # Update item fields - only update if user hasn't already set a value
            # Always update: ai_processed, ai_confidence, status, ai_raw_response
            # Conditionally update: type, subtype, primary_color, colors, pattern, material, style, formality, season
            ai_fields = tags_to_item_fields(tags, tags.raw_response)
            # Snapshotted once: applying tagging_status before tagged_by/tagged_at in the
            # same loop would otherwise make the guard for the later two fields see the
            # already-updated status and skip them even outside of a race.
            was_pending = item.tagging_status == TaggingStatus.pending

            for field, value in ai_fields.items():
                # Always update AI metadata fields (including tags JSONB and description)
                if field in (
                    "ai_processed",
                    "ai_confidence",
                    "status",
                    "ai_raw_response",
                    "tags",
                    "ai_description",
                ):
                    setattr(item, field, value)
                elif field in ("tagging_status", "tagged_by", "tagged_at"):
                    if was_pending:
                        setattr(item, field, value)
                # Only update content fields if user hasn't set them (or they're default/unknown)
                elif field == "type":
                    if not item.type or item.type == "unknown":
                        setattr(item, field, value)
                elif field == "subtype":
                    if not item.subtype:
                        setattr(item, field, value)
                elif field == "primary_color":
                    if not item.primary_color or item.primary_color == "unknown":
                        setattr(item, field, value)
                else:
                    # For other fields (colors, pattern, material, style, etc.), only set if not already set
                    current_value = getattr(item, field, None)
                    if (
                        current_value is None
                        or current_value == []
                        or current_value == ""
                        or current_value == {}
                    ):
                        setattr(item, field, value)

            await db.commit()
            logger.info(f"Updated item {item_id} with AI tags (status=ready)")

            return {
                "status": "success",
                "item_id": item_id,
                "tags": tags.model_dump(exclude={"raw_response"}),
            }

        finally:
            await db.close()

    except asyncio.CancelledError:
        # A cancelled attempt (worker shutdown, or cancel_item_analysis's abort) must
        # not touch `status` - cancel_item_analysis owns the terminal state for an
        # aborted job via its own guarded update, and marking this `error` here would
        # race it. Only clear the in-flight marker, then let the cancellation and
        # arq's own handling proceed normally.
        await clear_ai_started_at(ctx, item_id)
        raise
    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Error tagging item {item_id}: {error_msg}")
        # Returning normally here made max_tries dead: arq books a returned value
        # as success. arq only reschedules on Retry, so a plain re-raise would
        # surface the failure but still never retry.
        if _is_final_attempt(ctx):
            await update_item_status_to_error(ctx, item_id, error_msg)
            raise
        await clear_ai_started_at(ctx, item_id)
        raise Retry(defer=retry_delay_seconds(ctx)) from e
