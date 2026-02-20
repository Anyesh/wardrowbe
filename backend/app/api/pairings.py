import logging
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, computed_field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.outfit import Outfit, OutfitSource
from app.models.user import User
from app.services.pairing_service import (
    AIGenerationError,
    InsufficientItemsError,
    PairingService,
)
from app.utils.auth import get_current_user
from app.utils.signed_urls import sign_image_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pairings", tags=["Pairings"])


# Request/Response schemas
class GeneratePairingsRequest(BaseModel):
    num_pairings: int = Field(default=3, ge=1, le=5, description="Number of pairings to generate")


class SourceItemResponse(BaseModel):
    id: UUID
    type: str
    subtype: str | None = None
    name: str | None = None
    primary_color: str | None = None
    image_path: str
    thumbnail_path: str | None = None

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


class PairingItemResponse(BaseModel):
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


class FeedbackSummary(BaseModel):
    rating: int | None = None
    comment: str | None = None
    worn_at: date | None = None


class FamilyRatingResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_display_name: str
    user_avatar_url: str | None = None
    rating: int
    comment: str | None = None
    created_at: datetime


class PairingResponse(BaseModel):
    id: UUID
    occasion: str
    scheduled_for: date
    status: str
    source: str
    reasoning: str | None = None
    style_notes: str | None = None
    highlights: list[str] | None = None
    source_item: SourceItemResponse | None = None
    items: list[PairingItemResponse]
    feedback: FeedbackSummary | None = None
    family_ratings: list[FamilyRatingResponse] | None = None
    family_rating_average: float | None = None
    family_rating_count: int | None = None
    created_at: datetime


class PairingListResponse(BaseModel):
    pairings: list[PairingResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class GeneratePairingsResponse(BaseModel):
    generated: int
    pairings: list[PairingResponse]


def pairing_to_response(outfit: Outfit) -> PairingResponse:
    items = []
    for outfit_item in sorted(outfit.items, key=lambda x: x.position):
        item = outfit_item.item
        items.append(
            PairingItemResponse(
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

    # Build source item response
    source_item_response = None
    if outfit.source_item:
        source_item_response = SourceItemResponse(
            id=outfit.source_item.id,
            type=outfit.source_item.type,
            subtype=outfit.source_item.subtype,
            name=outfit.source_item.name,
            primary_color=outfit.source_item.primary_color,
            image_path=outfit.source_item.image_path,
            thumbnail_path=outfit.source_item.thumbnail_path,
        )

    # Build feedback summary
    feedback_summary = None
    if outfit.feedback:
        feedback_summary = FeedbackSummary(
            rating=outfit.feedback.rating,
            comment=outfit.feedback.comment,
            worn_at=outfit.feedback.worn_at,
        )

    # Extract highlights from ai_raw_response
    highlights = None
    if outfit.ai_raw_response and isinstance(outfit.ai_raw_response, dict):
        raw_highlights = outfit.ai_raw_response.get("highlights")
        if raw_highlights and isinstance(raw_highlights, list):
            highlights = raw_highlights

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

    return PairingResponse(
        id=outfit.id,
        occasion=outfit.occasion,
        scheduled_for=outfit.scheduled_for,
        status=outfit.status.value,
        source=outfit.source.value,
        reasoning=outfit.reasoning,
        style_notes=outfit.style_notes,
        highlights=highlights,
        source_item=source_item_response,
        items=items,
        feedback=feedback_summary,
        family_ratings=family_ratings_list,
        family_rating_average=family_rating_average,
        family_rating_count=family_rating_count,
        created_at=outfit.created_at,
    )


@router.post("/generate/{item_id}", response_model=GeneratePairingsResponse)
async def generate_pairings(
    item_id: UUID,
    request: GeneratePairingsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GeneratePairingsResponse:
    service = PairingService(db)

    try:
        pairings = await service.generate_pairings(
            user=current_user,
            source_item_id=item_id,
            num_pairings=request.num_pairings,
        )
    except InsufficientItemsError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None
    except AIGenerationError as e:
        logger.error(f"AI pairing generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from None

    return GeneratePairingsResponse(
        generated=len(pairings),
        pairings=[pairing_to_response(p) for p in pairings],
    )


@router.get("", response_model=PairingListResponse)
async def list_pairings(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: str | None = Query(None, description="Filter by source item type"),
) -> PairingListResponse:
    service = PairingService(db)
    pairings, total = await service.get_all_pairings(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        source_type=source_type,
    )

    return PairingListResponse(
        pairings=[pairing_to_response(p) for p in pairings],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.get("/item/{item_id}", response_model=PairingListResponse)
async def list_item_pairings(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PairingListResponse:
    service = PairingService(db)
    pairings, total = await service.get_pairings_for_item(
        user_id=current_user.id,
        source_item_id=item_id,
        page=page,
        page_size=page_size,
    )

    return PairingListResponse(
        pairings=[pairing_to_response(p) for p in pairings],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.delete("/{pairing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pairing(
    pairing_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    query = select(Outfit).where(
        and_(
            Outfit.id == pairing_id,
            Outfit.user_id == current_user.id,
            Outfit.source == OutfitSource.pairing,
        )
    )

    result = await db.execute(query)
    pairing = result.scalar_one_or_none()

    if not pairing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pairing not found",
        )

    await db.delete(pairing)
    await db.commit()
