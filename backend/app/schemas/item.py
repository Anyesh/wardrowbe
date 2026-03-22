from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.utils.signed_urls import sign_image_url

# Default wash intervals by clothing type (wears between washes)
DEFAULT_WASH_INTERVALS: dict[str, int] = {
    "t-shirt": 1,
    "shirt": 2,
    "blouse": 2,
    "pants": 4,
    "jeans": 6,
    "shorts": 3,
    "dress": 2,
    "skirt": 3,
    "sweater": 5,
    "hoodie": 4,
    "jacket": 8,
    "coat": 10,
    "blazer": 5,
    "suit": 5,
    "shoes": 15,
    "accessories": 20,
    "other": 3,
}


class ItemTags(BaseModel):
    colors: list[str] = Field(default_factory=list)
    primary_color: str | None = None
    pattern: str | None = None
    material: str | None = None
    style: list[str] = Field(default_factory=list)
    season: list[str] = Field(default_factory=list)
    formality: str | None = None
    fit: str | None = None


class ItemBase(BaseModel):
    type: str = Field(default="unknown", max_length=50)  # Default to unknown, AI will detect
    subtype: str | None = Field(None, max_length=50)
    name: str | None = Field(None, max_length=100)
    brand: str | None = Field(None, max_length=100)
    notes: str | None = None
    purchase_date: date | None = None
    purchase_price: Decimal | None = Field(None, ge=0)
    favorite: bool = False


class ItemCreate(ItemBase):
    tags: ItemTags | None = None
    colors: list[str] | None = None
    primary_color: str | None = None


class ItemUpdate(BaseModel):
    type: str | None = Field(None, min_length=1, max_length=50)
    subtype: str | None = Field(None, max_length=50)
    name: str | None = Field(None, max_length=100)
    brand: str | None = Field(None, max_length=100)
    notes: str | None = None
    purchase_date: date | None = None
    purchase_price: Decimal | None = Field(None, ge=0)
    favorite: bool | None = None
    tags: ItemTags | None = None
    colors: list[str] | None = None
    primary_color: str | None = None
    wash_interval: int | None = None


class ItemResponse(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    image_path: str
    thumbnail_path: str | None = None
    medium_path: str | None = None
    tags: dict = Field(default_factory=dict)
    colors: list[str] = Field(default_factory=list)
    primary_color: str | None = None
    pattern: str | None = None
    material: str | None = None
    style: list[str] = Field(default_factory=list)
    formality: str | None = None
    season: list[str] = Field(default_factory=list)
    status: str
    ai_processed: bool = False
    ai_confidence: Decimal | None = None
    ai_description: str | None = None
    wear_count: int = 0
    last_worn_at: date | None = None
    last_suggested_at: date | None = None
    suggestion_count: int = 0
    acceptance_count: int = 0
    wears_since_wash: int = 0
    last_washed_at: date | None = None
    wash_interval: int | None = None
    needs_wash: bool = False
    additional_images: list["ItemImageResponse"] = Field(default_factory=list)
    is_archived: bool = False
    archived_at: datetime | None = None
    archive_reason: str | None = None
    created_at: datetime
    updated_at: datetime

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

    @computed_field
    @property
    def medium_url(self) -> str | None:
        if self.medium_path:
            return sign_image_url(self.medium_path)
        return None

    @computed_field
    @property
    def effective_wash_interval(self) -> int:
        if self.wash_interval is not None:
            return self.wash_interval
        return DEFAULT_WASH_INTERVALS.get(self.type, 3)


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class ItemFilter(BaseModel):
    type: str | None = None
    subtype: str | None = None
    colors: list[str] | None = None
    status: str | None = None
    favorite: bool | None = None
    needs_wash: bool | None = None
    is_archived: bool = False
    search: str | None = None
    sort_by: str | None = None
    sort_order: str = "desc"


class LogWearRequest(BaseModel):
    worn_at: date | None = None  # If None, use user's timezone to determine today
    occasion: str | None = None
    notes: str | None = None


class ArchiveRequest(BaseModel):
    reason: str | None = Field(None, max_length=50)


class BulkUploadResult(BaseModel):
    filename: str
    success: bool
    item: ItemResponse | None = None
    error: str | None = None


class BulkUploadResponse(BaseModel):
    total: int
    successful: int
    failed: int
    results: list[BulkUploadResult]


class BulkFilters(BaseModel):
    type: str | None = None
    search: str | None = None
    is_archived: bool | None = None


class BulkDeleteRequest(BaseModel):
    # Explicit selection
    item_ids: list[UUID] | None = None

    # Select all with exceptions
    select_all: bool = False
    excluded_ids: list[UUID] | None = None
    filters: BulkFilters | None = None

    def model_post_init(self, __context):
        if not self.select_all and not self.item_ids:
            raise ValueError("Either item_ids or select_all=True must be provided")
        if self.select_all and self.item_ids:
            raise ValueError("Cannot use both item_ids and select_all")


class BulkDeleteResponse(BaseModel):
    deleted: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class BulkAnalyzeRequest(BaseModel):
    # Explicit selection
    item_ids: list[UUID] | None = None

    # Select all with exceptions
    select_all: bool = False
    excluded_ids: list[UUID] | None = None
    filters: BulkFilters | None = None

    def model_post_init(self, __context):
        if not self.select_all and not self.item_ids:
            raise ValueError("Either item_ids or select_all=True must be provided")
        if self.select_all and self.item_ids:
            raise ValueError("Cannot use both item_ids and select_all")


class BulkAnalyzeResponse(BaseModel):
    queued: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class ItemImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    image_path: str
    thumbnail_path: str | None = None
    medium_path: str | None = None
    position: int
    created_at: datetime

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

    @computed_field
    @property
    def medium_url(self) -> str | None:
        if self.medium_path:
            return sign_image_url(self.medium_path)
        return None


class ReorderImagesRequest(BaseModel):
    image_ids: list[UUID]


class RemoveBackgroundRequest(BaseModel):
    bg_color: str = Field(
        default="#FFFFFF",
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Hex color for the replacement background",
    )


class LogWashRequest(BaseModel):
    washed_at: date | None = None  # If None, use user's timezone to determine today
    method: str | None = Field(None, max_length=50)
    notes: str | None = None


class WashHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    washed_at: date
    method: str | None = None
    notes: str | None = None
    created_at: datetime
