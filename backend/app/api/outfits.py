"""Outfit recommendation API endpoints."""

import logging
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, computed_field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.outfit import Outfit, OutfitItem, OutfitStatus, UserFeedback
from app.models.user import User
from app.services.learning_service import LearningService
from app.services.recommendation_service import (
    AIRecommendationError,
    InsufficientWardrobeError,
    RecommendationService,
)
from app.services.weather_service import WeatherData
from app.utils.auth import get_current_user
from app.utils.signed_urls import sign_image_url

logger = logging.getLogger(__name__)


def get_user_today(user: User) -> date:
    """Get today's date in the user's timezone."""
    try:
        user_tz = ZoneInfo(user.timezone or "UTC")
    except Exception:
        user_tz = ZoneInfo("UTC")
    return datetime.now(UTC).astimezone(user_tz).date()


router = APIRouter(prefix="/outfits", tags=["Outfits"])


# Request/Response schemas
class WeatherOverrideRequest(BaseModel):
    """Manual weather override."""

    temperature: float = Field(description="Temperature in Celsius")
    feels_like: float | None = Field(None, description="Feels like temperature")
    condition: str = Field(default="unknown", description="Weather condition")
    precipitation_chance: int = Field(default=0, ge=0, le=100)
    humidity: int = Field(default=50, ge=0, le=100)


class SuggestRequest(BaseModel):
    """Request for outfit suggestion."""

    occasion: str = Field(default="casual", description="Occasion type")
    weather_override: WeatherOverrideRequest | None = Field(
        None, description="Manual weather override"
    )
    exclude_items: list[UUID] = Field(default_factory=list, description="Items to exclude")
    include_items: list[UUID] = Field(default_factory=list, description="Items to include")


class OutfitItemResponse(BaseModel):
    """Individual item in an outfit."""

    id: UUID
    type: str
    subtype: str | None = None
    name: str | None = None
    primary_color: str | None = None
    colors: list[str] = []
    image_path: str
    thumbnail_path: str | None = None
    layer_type: str | None = None
    position: int

    @computed_field
    @property
    def image_url(self) -> str:
        """Signed URL for the full-size image."""
        return sign_image_url(self.image_path)

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        """Signed URL for the thumbnail image."""
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class WoreInsteadItem(BaseModel):
    """Item info for wore_instead display."""

    id: UUID
    type: str
    name: str | None = None
    thumbnail_path: str | None = None

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        """Signed URL for the thumbnail image."""
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class FeedbackSummary(BaseModel):
    """Summary of outfit feedback for list views."""

    rating: int | None = None
    comment: str | None = None
    worn_at: date | None = None
    actually_worn: bool | None = None
    wore_instead_items: list[WoreInsteadItem] | None = None


class OutfitResponse(BaseModel):
    """Outfit recommendation response."""

    id: UUID
    occasion: str
    scheduled_for: date
    status: str
    source: str
    reasoning: str | None = None
    style_notes: str | None = None
    highlights: list[str] | None = None
    weather: dict | None = None
    items: list[OutfitItemResponse]
    feedback: FeedbackSummary | None = None
    created_at: datetime


class OutfitListResponse(BaseModel):
    """Paginated outfit list response."""

    outfits: list[OutfitResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class FeedbackRequest(BaseModel):
    """Request to submit feedback on an outfit."""

    accepted: bool | None = Field(None, description="Whether outfit was accepted")
    rating: int | None = Field(None, ge=1, le=5, description="Overall rating 1-5")
    comfort_rating: int | None = Field(None, ge=1, le=5, description="Comfort rating 1-5")
    style_rating: int | None = Field(None, ge=1, le=5, description="Style rating 1-5")
    comment: str | None = Field(None, max_length=1000, description="Optional comment")
    worn: bool | None = Field(None, description="Whether the outfit was worn")
    worn_with_modifications: bool | None = Field(
        None, description="If worn, whether modifications were made"
    )
    modification_notes: str | None = Field(None, max_length=500)
    actually_worn: bool | None = Field(
        None, description="Did user actually wear this recommendation?"
    )
    wore_instead_items: list[UUID] | None = Field(
        None, description="Item IDs user wore instead of recommendation"
    )


class FeedbackResponse(BaseModel):
    """Response with feedback details."""

    id: UUID
    outfit_id: UUID
    accepted: bool | None = None
    rating: int | None = None
    comfort_rating: int | None = None
    style_rating: int | None = None
    comment: str | None = None
    worn_at: date | None = None
    worn_with_modifications: bool = False
    modification_notes: str | None = None
    actually_worn: bool | None = None
    wore_instead_items: list[UUID] | None = None
    created_at: datetime


async def fetch_wore_instead_items_map(
    db: AsyncSession, outfits: list[Outfit]
) -> dict[str, list[WoreInsteadItem]]:
    """
    Batch fetch wore_instead items for multiple outfits.
    Returns a map of outfit_id -> list of WoreInsteadItem.
    """
    from app.models.item import ClothingItem

    # Collect all wore_instead item IDs across all outfits
    all_item_ids: set[UUID] = set()
    outfit_to_item_ids: dict[str, list[str]] = {}

    for outfit in outfits:
        if outfit.feedback and outfit.feedback.wore_instead_items:
            # Extract item IDs - handle both dict format [{"item_id": "..."}] and string format ["..."]
            item_ids: list[str] = []
            for item_data in outfit.feedback.wore_instead_items:
                try:
                    if isinstance(item_data, dict):
                        item_id = item_data.get("item_id", "")
                    else:
                        item_id = str(item_data)
                    if item_id:
                        item_ids.append(item_id)
                        all_item_ids.add(UUID(item_id))
                except (ValueError, TypeError, KeyError):
                    continue
            outfit_to_item_ids[str(outfit.id)] = item_ids

    if not all_item_ids:
        return {}

    # Batch fetch all items in one query
    result = await db.execute(select(ClothingItem).where(ClothingItem.id.in_(all_item_ids)))
    items_by_id = {str(item.id): item for item in result.scalars().all()}

    # Build the map
    wore_instead_map: dict[str, list[WoreInsteadItem]] = {}
    for outfit_id, item_ids in outfit_to_item_ids.items():
        wore_items = []
        for item_id in item_ids:
            if item_id in items_by_id:
                item = items_by_id[item_id]
                wore_items.append(
                    WoreInsteadItem(
                        id=item.id,
                        type=item.type,
                        name=item.name,
                        thumbnail_path=item.thumbnail_path,
                    )
                )
        if wore_items:
            wore_instead_map[outfit_id] = wore_items

    return wore_instead_map


def outfit_to_response(
    outfit: Outfit, wore_instead_items_map: dict[str, list["WoreInsteadItem"]] | None = None
) -> OutfitResponse:
    """
    Convert Outfit model to response schema.

    Args:
        outfit: The outfit to convert
        wore_instead_items_map: Pre-fetched map of outfit_id -> list of WoreInsteadItem.
                               If None, wore_instead_items will not be included.
    """
    items = []
    for outfit_item in sorted(outfit.items, key=lambda x: x.position):
        item = outfit_item.item
        items.append(
            OutfitItemResponse(
                id=item.id,
                type=item.type,
                subtype=item.subtype,
                name=item.name,
                primary_color=item.primary_color,
                colors=item.colors or [],
                image_path=item.image_path,
                thumbnail_path=item.thumbnail_path,
                layer_type=outfit_item.layer_type,
                position=outfit_item.position,
            )
        )

    # Build feedback summary if feedback exists
    feedback_summary = None
    if outfit.feedback:
        wore_instead = None
        if wore_instead_items_map and str(outfit.id) in wore_instead_items_map:
            wore_instead = wore_instead_items_map[str(outfit.id)]
        feedback_summary = FeedbackSummary(
            rating=outfit.feedback.rating,
            comment=outfit.feedback.comment,
            worn_at=outfit.feedback.worn_at,
            actually_worn=outfit.feedback.actually_worn,
            wore_instead_items=wore_instead,
        )

    # Extract highlights from ai_raw_response if available
    highlights = None
    if outfit.ai_raw_response and isinstance(outfit.ai_raw_response, dict):
        raw_highlights = outfit.ai_raw_response.get("highlights")
        if raw_highlights and isinstance(raw_highlights, list):
            highlights = raw_highlights

    return OutfitResponse(
        id=outfit.id,
        occasion=outfit.occasion,
        scheduled_for=outfit.scheduled_for,
        status=outfit.status.value,
        source=outfit.source.value,
        reasoning=outfit.reasoning,
        style_notes=outfit.style_notes,
        highlights=highlights,
        weather=outfit.weather_data,
        items=items,
        feedback=feedback_summary,
        created_at=outfit.created_at,
    )


@router.post("/suggest", response_model=OutfitResponse)
async def suggest_outfit(
    request: SuggestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    """
    Generate an outfit recommendation.

    Uses AI to suggest a cohesive outfit based on:
    - Current weather (or override)
    - User's wardrobe
    - User's preferences
    - Occasion type
    """
    # Convert weather override to WeatherData if provided
    weather_override = None
    if request.weather_override:
        w = request.weather_override
        weather_override = WeatherData(
            temperature=w.temperature,
            feels_like=w.feels_like or w.temperature,
            humidity=w.humidity,
            precipitation_chance=w.precipitation_chance,
            precipitation_mm=0,
            wind_speed=0,
            condition=w.condition,
            condition_code=0,
            is_day=True,
            uv_index=0,
            timestamp=datetime.utcnow(),
        )

    service = RecommendationService(db)

    try:
        outfit = await service.generate_recommendation(
            user=current_user,
            occasion=request.occasion,
            weather_override=weather_override,
            exclude_items=request.exclude_items,
            include_items=request.include_items,
        )
    except InsufficientWardrobeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except AIRecommendationError as e:
        logger.error(f"AI recommendation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Fetch wore_instead items for this single outfit
    wore_instead_map = await fetch_wore_instead_items_map(db, [outfit])
    return outfit_to_response(outfit, wore_instead_map)


@router.get("", response_model=OutfitListResponse)
async def list_outfits(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    occasion: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> OutfitListResponse:
    """List user's outfit recommendations with filtering."""
    # Build query
    query = (
        select(Outfit)
        .where(Outfit.user_id == current_user.id)
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
        )
    )

    # Apply filters
    if status_filter:
        try:
            outfit_status = OutfitStatus(status_filter)
            query = query.where(Outfit.status == outfit_status)
        except ValueError:
            pass  # Ignore invalid status

    if occasion:
        query = query.where(Outfit.occasion == occasion)

    if date_from:
        query = query.where(Outfit.scheduled_for >= date_from)

    if date_to:
        query = query.where(Outfit.scheduled_for <= date_to)

    # Get total count (apply all filters)
    count_query = select(Outfit.id).where(Outfit.user_id == current_user.id)
    if status_filter:
        try:
            outfit_status = OutfitStatus(status_filter)
            count_query = count_query.where(Outfit.status == outfit_status)
        except ValueError:
            pass
    if occasion:
        count_query = count_query.where(Outfit.occasion == occasion)
    if date_from:
        count_query = count_query.where(Outfit.scheduled_for >= date_from)
    if date_to:
        count_query = count_query.where(Outfit.scheduled_for <= date_to)

    count_result = await db.execute(count_query)
    total = len(count_result.all())

    # Apply pagination and ordering
    query = query.order_by(Outfit.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    outfits = list(result.scalars().all())

    # Batch fetch wore_instead items for all outfits (single query)
    wore_instead_map = await fetch_wore_instead_items_map(db, outfits)

    # Convert outfits to responses
    outfit_responses = [outfit_to_response(o, wore_instead_map) for o in outfits]

    return OutfitListResponse(
        outfits=outfit_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.get("/{outfit_id}", response_model=OutfitResponse)
async def get_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    """Get a specific outfit by ID."""
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
        )
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outfit not found",
        )

    return outfit_to_response(outfit, await fetch_wore_instead_items_map(db, [outfit]))


@router.post("/{outfit_id}/accept", response_model=OutfitResponse)
async def accept_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    """Mark an outfit as accepted."""
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
        )
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outfit not found",
        )

    outfit.status = OutfitStatus.accepted
    outfit.responded_at = datetime.utcnow()
    await db.commit()
    await db.refresh(outfit)

    return outfit_to_response(outfit, await fetch_wore_instead_items_map(db, [outfit]))


@router.post("/{outfit_id}/reject", response_model=OutfitResponse)
async def reject_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    """Mark an outfit as rejected."""
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
        )
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outfit not found",
        )

    outfit.status = OutfitStatus.rejected
    outfit.responded_at = datetime.utcnow()
    await db.commit()
    await db.refresh(outfit)

    return outfit_to_response(outfit, await fetch_wore_instead_items_map(db, [outfit]))


@router.delete("/{outfit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Delete an outfit."""
    query = select(Outfit).where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outfit not found",
        )

    await db.delete(outfit)
    await db.commit()


@router.post("/{outfit_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    outfit_id: UUID,
    request: FeedbackRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FeedbackResponse:
    """Submit feedback for an outfit (rating, comments, wear status)."""
    # Get outfit with feedback
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.feedback), selectinload(Outfit.items).selectinload(OutfitItem.item)
        )
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outfit not found",
        )

    # Create or update feedback
    if outfit.feedback:
        feedback = outfit.feedback
    else:
        feedback = UserFeedback(outfit_id=outfit.id)
        db.add(feedback)

    # Update fields if provided
    if request.accepted is not None:
        feedback.accepted = request.accepted
        outfit.status = OutfitStatus.accepted if request.accepted else OutfitStatus.rejected
        outfit.responded_at = datetime.utcnow()

    if request.rating is not None:
        feedback.rating = request.rating
    if request.comfort_rating is not None:
        feedback.comfort_rating = request.comfort_rating
    if request.style_rating is not None:
        feedback.style_rating = request.style_rating
    if request.comment is not None:
        feedback.comment = request.comment
    if request.worn and not feedback.worn_at:
        # Only increment wear counts if not already marked as worn (idempotency)
        user_today = get_user_today(current_user)
        feedback.worn_at = user_today
        for outfit_item in outfit.items:
            outfit_item.item.wear_count += 1
            outfit_item.item.last_worn_at = user_today
    if request.worn_with_modifications is not None:
        feedback.worn_with_modifications = request.worn_with_modifications
    if request.modification_notes is not None:
        feedback.modification_notes = request.modification_notes
    if request.actually_worn is not None:
        feedback.actually_worn = request.actually_worn
    if request.wore_instead_items is not None:
        feedback.wore_instead_items = [str(item_id) for item_id in request.wore_instead_items]

    await db.commit()
    await db.refresh(feedback)

    # Trigger learning system to process this feedback
    try:
        learning_service = LearningService(db)
        await learning_service.process_feedback(outfit_id, current_user.id)
        logger.info(f"Learning processed for outfit {outfit_id}")
    except Exception as e:
        # Don't fail the request if learning fails - log full traceback
        logger.exception(f"Learning processing failed for outfit {outfit_id}: {e}")

    return FeedbackResponse(
        id=feedback.id,
        outfit_id=feedback.outfit_id,
        accepted=feedback.accepted,
        rating=feedback.rating,
        comfort_rating=feedback.comfort_rating,
        style_rating=feedback.style_rating,
        comment=feedback.comment,
        worn_at=feedback.worn_at,
        worn_with_modifications=feedback.worn_with_modifications,
        modification_notes=feedback.modification_notes,
        actually_worn=feedback.actually_worn,
        wore_instead_items=[UUID(item_id) for item_id in (feedback.wore_instead_items or [])],
        created_at=feedback.created_at,
    )


@router.get("/{outfit_id}/feedback", response_model=FeedbackResponse)
async def get_feedback(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FeedbackResponse:
    """Get feedback for an outfit."""
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(selectinload(Outfit.feedback))
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outfit not found",
        )

    if not outfit.feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No feedback found for this outfit",
        )

    feedback = outfit.feedback
    return FeedbackResponse(
        id=feedback.id,
        outfit_id=feedback.outfit_id,
        accepted=feedback.accepted,
        rating=feedback.rating,
        comfort_rating=feedback.comfort_rating,
        style_rating=feedback.style_rating,
        comment=feedback.comment,
        worn_at=feedback.worn_at,
        worn_with_modifications=feedback.worn_with_modifications,
        modification_notes=feedback.modification_notes,
        actually_worn=feedback.actually_worn,
        wore_instead_items=[UUID(item_id) for item_id in (feedback.wore_instead_items or [])],
        created_at=feedback.created_at,
    )
