import logging
from collections import Counter
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from sqlalchemy import and_, select

from app.config import get_settings
from app.database import DbSession
from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.models.wishlist import DEFAULT_PRIORITY, WishlistItem
from app.services.image_service import ImageService
from app.services.link_preview import PreviewError, fetch_preview, validate_url
from app.services.price_watch import check_prices
from app.utils.auth import get_current_user
from app.utils.garment_vocabulary import ITEM_ROLE, TYPES
from app.utils.signed_urls import sign_optional
from app.utils.uploads import UploadTooLargeError, read_upload_within_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wishlist", tags=["Wishlist"])

# A wardrobe that covers a week without laundry: how many of each role it usually holds.
ROLE_TARGETS: dict[str, int] = {
    "base_top": 7,
    "bottom": 3,
    "footwear": 2,
    "outer_layer": 2,
    "mid_layer": 1,
}


def _http_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        return validate_url(value)
    except PreviewError as e:
        raise ValueError(str(e)) from None


def _known_type(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if value not in TYPES:
        raise ValueError(f"Unknown clothing type: {value}")
    return value


class WishlistFields(BaseModel):
    notes: str | None = Field(None, max_length=2000)
    link: str | None = Field(None, max_length=1000)
    image_url: str | None = Field(None, max_length=1000)
    price: Decimal | None = Field(None, ge=0, le=1_000_000)
    item_type: str | None = None
    priority: int = Field(DEFAULT_PRIORITY, ge=1, le=3)

    @field_validator("link", "image_url")
    @classmethod
    def web_address(cls, value: str | None) -> str | None:
        return _http_url(value)

    @field_validator("item_type")
    @classmethod
    def known_type(cls, value: str | None) -> str | None:
        return _known_type(value)


class WishlistCreate(WishlistFields):
    name: str = Field(min_length=1, max_length=200)


class WishlistUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    notes: str | None = Field(None, max_length=2000)
    link: str | None = Field(None, max_length=1000)
    image_url: str | None = Field(None, max_length=1000)
    price: Decimal | None = Field(None, ge=0, le=1_000_000)
    item_type: str | None = None
    priority: int | None = Field(None, ge=1, le=3)
    bought: bool | None = None

    @field_validator("link", "image_url")
    @classmethod
    def web_address(cls, value: str | None) -> str | None:
        return _http_url(value)

    @field_validator("item_type")
    @classmethod
    def known_type(cls, value: str | None) -> str | None:
        return _known_type(value)


class WishlistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    notes: str | None
    link: str | None
    image_url: str | None
    image_path: str | None = Field(None, exclude=True)
    thumbnail_path: str | None = Field(None, exclude=True)
    price: Decimal | None
    item_type: str | None
    priority: int
    bought: bool
    current_price: Decimal | None = None
    price_checked_at: datetime | None = None
    price_dropped_at: datetime | None = None
    created_at: datetime

    @computed_field
    @property
    def photo_url(self) -> str | None:
        """The uploaded photo when there is one, otherwise the picture from the web."""
        return sign_optional(self.thumbnail_path, self.image_path) or self.image_url


class PreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=1000)


class PreviewResponse(BaseModel):
    url: str
    title: str | None
    image_url: str | None
    price: Decimal | None
    currency: str | None
    site: str | None


class Suggestion(BaseModel):
    role: str
    have: int
    target: int


async def _owned(db, user: User, item_id: UUID) -> WishlistItem:
    entry = await db.scalar(
        select(WishlistItem).where(WishlistItem.id == item_id, WishlistItem.user_id == user.id)
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return entry


@router.get("", response_model=list[WishlistResponse])
async def list_wishlist(
    db: DbSession, current_user: Annotated[User, Depends(get_current_user)]
) -> list[WishlistResponse]:
    rows = await db.scalars(
        select(WishlistItem)
        .where(WishlistItem.user_id == current_user.id)
        .order_by(WishlistItem.bought, WishlistItem.priority, WishlistItem.created_at.desc())
    )
    return [WishlistResponse.model_validate(row) for row in rows]


@router.post("", response_model=WishlistResponse, status_code=status.HTTP_201_CREATED)
async def add_wishlist_item(
    data: WishlistCreate, db: DbSession, current_user: Annotated[User, Depends(get_current_user)]
) -> WishlistResponse:
    entry = WishlistItem(user_id=current_user.id, **data.model_dump())
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return WishlistResponse.model_validate(entry)


@router.patch("/{item_id}", response_model=WishlistResponse)
async def update_wishlist_item(
    item_id: UUID,
    data: WishlistUpdate,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> WishlistResponse:
    entry = await _owned(db, current_user, item_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if key in ("name", "priority", "bought") and value is None:
            continue
        setattr(entry, key, value)
    await db.flush()
    await db.refresh(entry)
    return WishlistResponse.model_validate(entry)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wishlist_item(
    item_id: UUID, db: DbSession, current_user: Annotated[User, Depends(get_current_user)]
) -> Response:
    entry = await _owned(db, current_user, item_id)
    paths = {"image": entry.image_path, "thumbnail": entry.thumbnail_path}
    await db.delete(entry)
    await db.flush()
    ImageService().delete_images(paths)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{item_id}/image", response_model=WishlistResponse)
async def upload_wishlist_photo(
    item_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    image: UploadFile = File(...),
) -> WishlistResponse:
    entry = await _owned(db, current_user, item_id)
    image_service = ImageService()
    try:
        content = await read_upload_within_limit(image, get_settings().max_upload_size_mb)
    except UploadTooLargeError as e:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(e)) from None
    if not image_service.validate_image(content, image.content_type or "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image file. Supported formats: JPEG, PNG, WebP, HEIC",
        )
    try:
        paths = await image_service.process_and_store(
            user_id=current_user.id,
            image_data=content,
            original_filename=image.filename or "wishlist.jpg",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    old = {"image": entry.image_path, "thumbnail": entry.thumbnail_path}
    entry.image_path = paths["image_path"]
    entry.thumbnail_path = paths.get("thumbnail_path")
    await db.flush()
    await db.refresh(entry)
    image_service.delete_images(old)
    return WishlistResponse.model_validate(entry)


@router.post("/preview", response_model=PreviewResponse)
async def preview_link(
    data: PreviewRequest, _: Annotated[User, Depends(get_current_user)]
) -> PreviewResponse:
    try:
        preview = await fetch_preview(data.url)
    except PreviewError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    return PreviewResponse(**preview.__dict__)


# A button press reads the shops while the page waits, so it covers a handful at a time.
MANUAL_CHECK_LIMIT = 15


@router.post("/check-prices", response_model=list[WishlistResponse])
async def check_prices_now(
    db: DbSession, current_user: Annotated[User, Depends(get_current_user)]
) -> list[WishlistResponse]:
    entries = list(
        (
            await db.scalars(
                select(WishlistItem)
                .where(
                    WishlistItem.user_id == current_user.id,
                    WishlistItem.link.is_not(None),
                    WishlistItem.bought.is_(False),
                )
                .order_by(WishlistItem.price_checked_at.nulls_first())
                .limit(MANUAL_CHECK_LIMIT)
            )
        ).all()
    )
    await check_prices(db, entries, pause=0.3)
    for entry in entries:
        await db.refresh(entry)
    return [WishlistResponse.model_validate(e) for e in entries]


@router.get("/suggestions", response_model=list[Suggestion])
async def wardrobe_gaps(
    db: DbSession, current_user: Annotated[User, Depends(get_current_user)]
) -> list[Suggestion]:
    types = await db.scalars(
        select(ClothingItem.type).where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.status == ItemStatus.ready,
                ClothingItem.is_archived.is_(False),
            )
        )
    )
    have = Counter(ITEM_ROLE.get((t or "").lower()) for t in types)
    gaps = [
        Suggestion(role=role, have=have.get(role, 0), target=target)
        for role, target in ROLE_TARGETS.items()
        if have.get(role, 0) < target
    ]
    gaps.sort(key=lambda g: g.have / g.target)
    return gaps
