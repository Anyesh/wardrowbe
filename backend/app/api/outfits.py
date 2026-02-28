import logging
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, computed_field
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.item import ClothingItem
from app.models.outfit import FamilyOutfitRating, Outfit, OutfitItem, OutfitStatus, UserFeedback
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
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/outfits", tags=["Outfits"])


# Request/Response schemas
class WeatherOverrideRequest(BaseModel):
    temperature: float = Field(description="Temperature in Celsius")
    feels_like: float | None = Field(None, description="Feels like temperature")
    condition: str = Field(default="unknown", description="Weather condition")
    precipitation_chance: int = Field(default=0, ge=0, le=100)
    humidity: int = Field(default=50, ge=0, le=100)


class SuggestRequest(BaseModel):
    occasion: str = Field(default="casual", description="Occasion type")
    weather_override: WeatherOverrideRequest | None = Field(
        None, description="Manual weather override"
    )
    exclude_items: list[UUID] = Field(default_factory=list, description="Items to exclude")
    include_items: list[UUID] = Field(default_factory=list, description="Items to include")


class OutfitItemResponse(BaseModel):
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
        return sign_image_url(self.image_path)

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class WoreInsteadItem(BaseModel):
    id: UUID
    type: str
    name: str | None = None
    thumbnail_path: str | None = None

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class FeedbackSummary(BaseModel):
    rating: int | None = None
    comment: str | None = None
    worn_at: date | None = None
    actually_worn: bool | None = None
    wore_instead_items: list[WoreInsteadItem] | None = None


class FamilyRatingRequest(BaseModel):
    rating: int = Field(ge=1, le=5, description="Rating 1-5")
    comment: str | None = Field(None, max_length=500)


class FamilyRatingResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_display_name: str
    user_avatar_url: str | None = None
    rating: int
    comment: str | None = None
    created_at: datetime


class OutfitResponse(BaseModel):
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
    family_ratings: list[FamilyRatingResponse] | None = None
    family_rating_average: float | None = None
    family_rating_count: int | None = None
    created_at: datetime


class OutfitListResponse(BaseModel):
    outfits: list[OutfitResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class FeedbackRequest(BaseModel):
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
    db: AsyncSession, outfits: list[Outfit], user_id: UUID | None = None
) -> dict[str, list[WoreInsteadItem]]:
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

    query = select(ClothingItem).where(ClothingItem.id.in_(all_item_ids))
    if user_id is not None:
        query = query.where(ClothingItem.user_id == user_id)
    result = await db.execute(query)
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

    # Build family ratings if loaded
    family_ratings_list = None
    family_rating_average = None
    family_rating_count = None
    if hasattr(outfit, "family_ratings") and outfit.family_ratings:
        family_ratings_list = [
            FamilyRatingResponse(
                id=r.id,
                user_id=r.user_id,
                user_display_name=r.user.display_name or r.user.email if r.user else "Unknown",
                user_avatar_url=r.user.avatar_url if r.user else None,
                rating=r.rating,
                comment=r.comment,
                created_at=r.created_at,
            )
            for r in outfit.family_ratings
        ]
        family_rating_count = len(outfit.family_ratings)
        if family_rating_count > 0:
            family_rating_average = (
                sum(r.rating for r in outfit.family_ratings) / family_rating_count
            )

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
        family_ratings=family_ratings_list,
        family_rating_average=family_rating_average,
        family_rating_count=family_rating_count,
        created_at=outfit.created_at,
    )


@router.post("/suggest", response_model=OutfitResponse)
async def suggest_outfit(
    request: SuggestRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
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
        ) from None
    except AIRecommendationError as e:
        logger.error(f"AI recommendation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None

    # Fetch wore_instead items for this single outfit
    wore_instead_map = await fetch_wore_instead_items_map(db, [outfit], user_id=current_user.id)
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
    family_member_id: UUID | None = Query(None, description="View a family member's outfits"),
) -> OutfitListResponse:
    # Determine whose outfits to fetch
    target_user_id = current_user.id
    if family_member_id:
        # Verify same family
        if not current_user.family_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be in a family to view family member outfits",
            )
        member_result = await db.execute(
            select(User).where(User.id == family_member_id, User.is_active.is_(True))
        )
        member = member_result.scalar_one_or_none()
        if not member or member.family_id != current_user.family_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not in your family",
            )
        target_user_id = family_member_id

    # Build query
    query = (
        select(Outfit)
        .where(Outfit.user_id == target_user_id)
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
            selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
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
    count_query = select(Outfit.id).where(Outfit.user_id == target_user_id)
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
    wore_instead_map = await fetch_wore_instead_items_map(db, outfits, user_id=current_user.id)

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
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
            selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
        )
    )

    result = await db.execute(query)
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Outfit not found",
        )

    return outfit_to_response(
        outfit, await fetch_wore_instead_items_map(db, [outfit], user_id=current_user.id)
    )


@router.post("/{outfit_id}/accept", response_model=OutfitResponse)
async def accept_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
            selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
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

    return outfit_to_response(
        outfit, await fetch_wore_instead_items_map(db, [outfit], user_id=current_user.id)
    )


@router.post("/{outfit_id}/reject", response_model=OutfitResponse)
async def reject_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OutfitResponse:
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == current_user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
            selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
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

    return outfit_to_response(
        outfit, await fetch_wore_instead_items_map(db, [outfit], user_id=current_user.id)
    )


@router.delete("/{outfit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outfit(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
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
        from app.schemas.item import DEFAULT_WASH_INTERVALS

        user_today = get_user_today(current_user)
        feedback.worn_at = user_today
        for outfit_item in outfit.items:
            item = outfit_item.item
            effective_interval = (
                item.wash_interval
                if item.wash_interval is not None
                else DEFAULT_WASH_INTERVALS.get(item.type, 3)
            )
            # Atomic SQL increment to avoid race on concurrent feedback submissions
            await db.execute(
                update(ClothingItem)
                .where(ClothingItem.id == item.id)
                .values(
                    wear_count=ClothingItem.wear_count + 1,
                    last_worn_at=user_today,
                    wears_since_wash=ClothingItem.wears_since_wash + 1,
                    needs_wash=ClothingItem.wears_since_wash + 1 >= effective_interval,
                )
            )
    if request.worn_with_modifications is not None:
        feedback.worn_with_modifications = request.worn_with_modifications
    if request.modification_notes is not None:
        feedback.modification_notes = request.modification_notes
    if request.actually_worn is not None:
        feedback.actually_worn = request.actually_worn
    if request.wore_instead_items is not None:
        feedback.wore_instead_items = [str(item_id) for item_id in request.wore_instead_items]

        # Track wash status for "wore instead" items
        # When user says they wore something else, those items need washing tracking
        if feedback.wore_instead_items and not feedback.worn_at:
            # Only process if not already marked worn (avoid double-counting)
            from app.schemas.item import DEFAULT_WASH_INTERVALS

            user_today = get_user_today(current_user)
            feedback.worn_at = user_today

            # Get the actual items they wore
            wore_instead_ids = [UUID(item_id) for item_id in feedback.wore_instead_items]
            result = await db.execute(
                select(ClothingItem).where(
                    and_(
                        ClothingItem.id.in_(wore_instead_ids),
                        ClothingItem.user_id == current_user.id,
                    )
                )
            )
            wore_instead_items = list(result.scalars().all())

            # Atomic SQL increment for wore-instead items
            for item in wore_instead_items:
                effective_interval = (
                    item.wash_interval
                    if item.wash_interval is not None
                    else DEFAULT_WASH_INTERVALS.get(item.type, 3)
                )
                await db.execute(
                    update(ClothingItem)
                    .where(ClothingItem.id == item.id)
                    .values(
                        wear_count=ClothingItem.wear_count + 1,
                        last_worn_at=user_today,
                        wears_since_wash=ClothingItem.wears_since_wash + 1,
                        needs_wash=ClothingItem.wears_since_wash + 1 >= effective_interval,
                    )
                )

            logger.info(
                f"Tracked {len(wore_instead_items)} 'wore instead' items for washing/wear stats"
            )

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


@router.post("/{outfit_id}/family-rating", response_model=FamilyRatingResponse)
async def submit_family_rating(
    outfit_id: UUID,
    request: FamilyRatingRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FamilyRatingResponse:
    # Get the outfit
    result = await db.execute(select(Outfit).where(Outfit.id == outfit_id))
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found")

    # Cannot rate your own outfit
    if outfit.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot rate your own outfit",
        )

    # Verify same family
    if not current_user.family_id or not outfit.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be in the same family to rate outfits",
        )

    # Check the outfit owner is in the same family
    owner_result = await db.execute(
        select(User).where(User.id == outfit.user_id, User.is_active.is_(True))
    )
    owner = owner_result.scalar_one_or_none()
    if not owner or owner.family_id != current_user.family_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be in the same family to rate outfits",
        )

    # Check for existing rating (upsert)
    existing = await db.execute(
        select(FamilyOutfitRating).where(
            and_(
                FamilyOutfitRating.outfit_id == outfit_id,
                FamilyOutfitRating.user_id == current_user.id,
            )
        )
    )
    rating = existing.scalar_one_or_none()

    if rating:
        rating.rating = request.rating
        rating.comment = request.comment
    else:
        rating = FamilyOutfitRating(
            outfit_id=outfit_id,
            user_id=current_user.id,
            rating=request.rating,
            comment=request.comment,
        )
        db.add(rating)

    await db.flush()
    await db.refresh(rating)

    return FamilyRatingResponse(
        id=rating.id,
        user_id=rating.user_id,
        user_display_name=current_user.display_name or current_user.email,
        user_avatar_url=current_user.avatar_url,
        rating=rating.rating,
        comment=rating.comment,
        created_at=rating.created_at,
    )


@router.get("/{outfit_id}/family-ratings", response_model=list[FamilyRatingResponse])
async def get_family_ratings(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[FamilyRatingResponse]:
    result = await db.execute(select(Outfit).where(Outfit.id == outfit_id))
    outfit = result.scalar_one_or_none()

    if not outfit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found")

    # Verify caller owns the outfit or is in the same family as the owner
    if outfit.user_id != current_user.id:
        if not current_user.family_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        owner_result = await db.execute(
            select(User).where(User.id == outfit.user_id, User.is_active.is_(True))
        )
        owner = owner_result.scalar_one_or_none()
        if not owner or owner.family_id != current_user.family_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Get ratings with user info
    ratings_result = await db.execute(
        select(FamilyOutfitRating)
        .where(FamilyOutfitRating.outfit_id == outfit_id)
        .options(selectinload(FamilyOutfitRating.user))
        .order_by(FamilyOutfitRating.created_at.desc())
    )
    ratings = list(ratings_result.scalars().all())

    return [
        FamilyRatingResponse(
            id=r.id,
            user_id=r.user_id,
            user_display_name=r.user.display_name or r.user.email,
            user_avatar_url=r.user.avatar_url,
            rating=r.rating,
            comment=r.comment,
            created_at=r.created_at,
        )
        for r in ratings
    ]


@router.delete("/{outfit_id}/family-rating", status_code=status.HTTP_204_NO_CONTENT)
async def delete_family_rating(
    outfit_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    result = await db.execute(
        select(FamilyOutfitRating).where(
            and_(
                FamilyOutfitRating.outfit_id == outfit_id,
                FamilyOutfitRating.user_id == current_user.id,
            )
        )
    )
    rating = result.scalar_one_or_none()

    if not rating:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rating not found",
        )

    await db.delete(rating)
    await db.flush()
