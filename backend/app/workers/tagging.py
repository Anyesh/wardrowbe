import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.models.item import ClothingItem, ItemStatus
from app.services.ai_service import AIService, ClothingTags
from app.workers.db import close_db, get_db_session, init_db

logger = logging.getLogger(__name__)


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
    }
    if raw_response:
        fields["ai_raw_response"] = {"raw_text": raw_response}
    return fields


async def update_item_status_to_error(ctx: dict, item_id: str, error_msg: str) -> None:
    """Update item status to error in database."""
    try:
        db = get_db_session(ctx)
        try:
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()
            if item:
                item.status = ItemStatus.error
                item.ai_raw_response = {"error": error_msg}
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

    try:
        # Verify image exists
        path = Path(image_path)
        if not path.exists():
            error_msg = f"Image not found: {image_path}"
            logger.error(error_msg)
            await update_item_status_to_error(ctx, item_id, error_msg)
            return {"status": "error", "error": "Image not found"}

        # Get user's AI endpoints from preferences
        ai_endpoints = None
        db = get_db_session(ctx)
        try:
            # Get the item to find user_id
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()
            if item:
                # Get user's preferences for AI endpoints
                from app.models.preference import UserPreference

                pref_result = await db.execute(
                    select(UserPreference).where(UserPreference.user_id == item.user_id)
                )
                prefs = pref_result.scalar_one_or_none()
                if prefs and prefs.ai_endpoints:
                    ai_endpoints = prefs.ai_endpoints
                    logger.info(
                        f"Using {len(ai_endpoints)} custom AI endpoints for user {item.user_id}"
                    )
        finally:
            await db.close()

        # Analyze with AI (uses custom endpoints if available)
        ai_service = AIService(endpoints=ai_endpoints)
        tags = await ai_service.analyze_image(path)

        logger.info(
            f"AI analysis complete for item {item_id}: type={tags.type}, color={tags.primary_color}"
        )

        # Update item in database
        db = get_db_session(ctx)
        try:
            result = await db.execute(select(ClothingItem).where(ClothingItem.id == UUID(item_id)))
            item = result.scalar_one_or_none()

            if item is None:
                logger.error(f"Item not found: {item_id}")
                return {"status": "error", "error": "Item not found"}

            # Update item fields - only update if user hasn't already set a value
            # Always update: ai_processed, ai_confidence, status, ai_raw_response
            # Conditionally update: type, subtype, primary_color, colors, pattern, material, style, formality, season
            ai_fields = tags_to_item_fields(tags, tags.raw_response)

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

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"Error tagging item {item_id}: {error_msg}")
        await update_item_status_to_error(ctx, item_id, error_msg)
        return {"status": "error", "error": error_msg}


async def startup(ctx: dict) -> None:
    """Worker startup hook."""
    logger.info("Tagging worker starting up...")
    await init_db(ctx)
    ctx["ai_service"] = AIService()
    health = await ctx["ai_service"].check_health()
    logger.info(f"AI service health: {health}")


async def shutdown(ctx: dict) -> None:
    """Worker shutdown hook."""
    logger.info("Tagging worker shutting down...")
    await close_db(ctx)


class WorkerSettings:
    """arq worker settings for tagging and notifications."""

    # Import notification functions
    from arq import cron

    from app.workers.notifications import (
        check_scheduled_notifications,
        retry_failed_notifications,
        send_notification,
    )

    functions = [
        tag_item_image,
        send_notification,
        retry_failed_notifications,
        check_scheduled_notifications,
    ]

    cron_jobs = [
        # Retry failed notifications every 5 minutes
        cron(retry_failed_notifications, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        # Check scheduled notifications every minute
        cron(check_scheduled_notifications, minute=None),
    ]

    on_startup = startup
    on_shutdown = shutdown

    # Import redis settings
    from app.workers.settings import get_redis_settings

    redis_settings = get_redis_settings()

    # Worker configuration
    max_jobs = 5
    job_timeout = 600  # 10 minutes per job (Pi's tinyllama is slow)
    max_tries = 3
    health_check_interval = 30

    # Queue name - must match the queue used in items.py
    queue_name = "arq:tagging"
