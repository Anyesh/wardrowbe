"""Item pairing API endpoints."""

import logging
from datetime import date, datetime
from typing import Annotated, Optional
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
    """Request to generate pairings for an item."""

    num_pairings: int = Field(default=3, ge=1, le=5, description="Number of pairings to generate")


class SourceItemResponse(BaseModel):
    """Source item in a pairing."""

    id: UUID
    type: str
    subtype: Optional[str] = None
    name: Optional[str] = None
    primary_color: Optional[str] = None
    image_path: str
    thumbnail_path: Optional[str] = None

    @computed_field
    @property
    def image_url(self) -> str:
        """Signed URL for the full-size image."""
        return sign_image_url(self.image_path)

    @computed_field
    @property
    def thumbnail_url(self) -> Optional[str]:
        """Signed URL for the thumbnail image."""
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class PairingItemResponse(BaseModel):
    """Individual item in a pairing."""

    id: UUID
    type: str
    subtype: Optional[str] = None
    name: Optional[str] = None
    primary_color: Optional[str] = None
    colors: list[str] = []
    image_path: str
    thumbnail_path: Optional[str] = None
    layer_type: Optional[str] = None
    position: int

    @computed_field
    @property
    def image_url(self) -> str:
        """Signed URL for the full-size image."""
        return sign_image_url(self.image_path)

    @computed_field
    @property
    def thumbnail_url(self) -> Optional[str]:
        """Signed URL for the thumbnail image."""
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class FeedbackSummary(BaseModel):
    """Summary of outfit feedback."""

    rating: Optional[int] = None
    comment: Optional[str] = None
    worn_at: Optional[date] = None


class PairingResponse(BaseModel):
    """Pairing response with source item highlighted."""

    id: UUID
    occasion: str
    scheduled_for: date
    status: str
    source: str
    reasoning: Optional[str] = None
    style_notes: Optional[str] = None
    highlights: Optional[list[str]] = None
    source_item: Optional[SourceItemResponse] = None
    items: list[PairingItemResponse]
    feedback: Optional[FeedbackSummary] = None
    created_at: datetime


class PairingListResponse(BaseModel):
    """Paginated pairing list response."""

    pairings: list[PairingResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class GeneratePairingsResponse(BaseModel):
    """Response after generating pairings."""

    generated: int
    pairings: list[PairingResponse]


def pairing_to_response(outfit: Outfit) -> PairingResponse:
    """Convert Outfit model to PairingResponse."""
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
        created_at=outfit.created_at,
    )


@router.post("/generate/{item_id}", response_model=GeneratePairingsResponse)
async def generate_pairings(
    item_id: UUID,
    request: GeneratePairingsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GeneratePairingsResponse:
    """
    Generate outfit pairings for a specific item.

    Creates multiple complete outfits that all include the specified item,
    with AI-generated reasoning for why each combination works.
    """
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
        ) from e
    except AIGenerationError as e:
        logger.error(f"AI pairing generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

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
    source_type: Optional[str] = Query(None, description="Filter by source item type"),
) -> PairingListResponse:
    """List all user's pairings with optional filtering."""
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
    """List pairings for a specific source item."""
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
    """Delete a pairing."""
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
