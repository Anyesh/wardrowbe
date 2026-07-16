import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.outfit import Outfit
    from app.models.user import User


class ItemStatus(enum.StrEnum):
    processing = "processing"
    ready = "ready"
    error = "error"
    archived = "archived"


class ClothingItem(Base):
    __tablename__ = "clothing_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Image paths
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    medium_path: Mapped[str | None] = mapped_column(String(500))
    image_hash: Mapped[str | None] = mapped_column(String(16), index=True)  # pHash hex string

    # Classification
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(50))

    # Tags and attributes
    tags: Mapped[dict] = mapped_column(JSONB, default=dict)
    colors: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    primary_color: Mapped[str | None] = mapped_column(String(50))
    pattern: Mapped[str | None] = mapped_column(String(50))
    material: Mapped[str | None] = mapped_column(String(50))
    style: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    formality: Mapped[str | None] = mapped_column(String(50))
    season: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # AI metadata
    status: Mapped[ItemStatus] = mapped_column(
        Enum(ItemStatus, name="item_status"), default=ItemStatus.processing
    )
    ai_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    ai_raw_response: Mapped[dict | None] = mapped_column(JSONB)

    # Usage tracking
    wear_count: Mapped[int] = mapped_column(Integer, default=0)
    last_worn_at: Mapped[date | None] = mapped_column(Date)
    last_suggested_at: Mapped[date | None] = mapped_column(Date)
    suggestion_count: Mapped[int] = mapped_column(Integer, default=0)
    acceptance_count: Mapped[int] = mapped_column(Integer, default=0)

    # Wash tracking
    wears_since_wash: Mapped[int] = mapped_column(Integer, default=0)
    last_washed_at: Mapped[date | None] = mapped_column(Date)
    wash_interval: Mapped[int | None] = mapped_column(Integer)
    needs_wash: Mapped[bool] = mapped_column(Boolean, default=False)

    # AI description (human-readable caption)
    ai_description: Mapped[str | None] = mapped_column(Text)

    # User metadata
    name: Mapped[str | None] = mapped_column(String(100))
    brand: Mapped[str | None] = mapped_column(String(100))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)

    # Lifecycle
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_reason: Mapped[str | None] = mapped_column(String(50))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="clothing_items")
    wear_history: Mapped[list["ItemHistory"]] = relationship(
        "ItemHistory", back_populates="item", cascade="all, delete-orphan"
    )
    wash_history: Mapped[list["WashHistory"]] = relationship(
        "WashHistory", back_populates="item", cascade="all, delete-orphan"
    )
    additional_images: Mapped[list["ItemImage"]] = relationship(
        "ItemImage",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ItemImage.position",
    )


class ItemHistory(Base):
    __tablename__ = "item_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clothing_items.id", ondelete="CASCADE"), nullable=False
    )
    outfit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outfits.id", ondelete="SET NULL")
    )

    worn_at: Mapped[date] = mapped_column(Date, nullable=False)
    occasion: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    item: Mapped["ClothingItem"] = relationship("ClothingItem", back_populates="wear_history")
    outfit: Mapped[Optional["Outfit"]] = relationship("Outfit")


class WashHistory(Base):
    __tablename__ = "wash_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clothing_items.id", ondelete="CASCADE"), nullable=False
    )

    washed_at: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    item: Mapped["ClothingItem"] = relationship("ClothingItem", back_populates="wash_history")


class ItemImage(Base):
    __tablename__ = "item_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clothing_items.id", ondelete="CASCADE"), nullable=False
    )

    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    medium_path: Mapped[str | None] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    item: Mapped["ClothingItem"] = relationship("ClothingItem", back_populates="additional_images")
