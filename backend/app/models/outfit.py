"""Outfit and recommendation models."""

import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.item import ClothingItem
    from app.models.user import User


class OutfitStatus(str, enum.Enum):
    """Outfit recommendation status."""

    pending = "pending"
    sent = "sent"
    viewed = "viewed"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"


class OutfitSource(str, enum.Enum):
    """How the outfit was created."""

    scheduled = "scheduled"
    on_demand = "on_demand"
    manual = "manual"
    pairing = "pairing"


class Outfit(Base):
    """Generated outfit recommendation."""

    __tablename__ = "outfits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Context
    weather_data: Mapped[dict | None] = mapped_column(JSONB)
    occasion: Mapped[str] = mapped_column(String(50), nullable=False)
    scheduled_for: Mapped[date] = mapped_column(Date, nullable=False)

    # AI output
    reasoning: Mapped[str | None] = mapped_column(Text)
    style_notes: Mapped[str | None] = mapped_column(Text)
    ai_raw_response: Mapped[dict | None] = mapped_column(JSONB)

    # Status
    status: Mapped[OutfitStatus] = mapped_column(
        Enum(OutfitStatus, name="outfit_status", create_type=False),
        default=OutfitStatus.pending,
    )
    source: Mapped[OutfitSource] = mapped_column(
        Enum(OutfitSource, name="outfit_source", create_type=False),
        default=OutfitSource.scheduled,
    )

    # Source item for pairings
    source_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clothing_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="outfits")
    items: Mapped[list["OutfitItem"]] = relationship(
        "OutfitItem", back_populates="outfit", cascade="all, delete-orphan"
    )
    feedback: Mapped[Optional["UserFeedback"]] = relationship(
        "UserFeedback", back_populates="outfit", uselist=False, cascade="all, delete-orphan"
    )
    source_item: Mapped[Optional["ClothingItem"]] = relationship(
        "ClothingItem", foreign_keys=[source_item_id]
    )


class OutfitItem(Base):
    """Junction table linking outfits to clothing items."""

    __tablename__ = "outfit_items"

    outfit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outfits.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clothing_items.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    layer_type: Mapped[str | None] = mapped_column(String(20))

    # Relationships
    outfit: Mapped["Outfit"] = relationship("Outfit", back_populates="items")
    item: Mapped["ClothingItem"] = relationship("ClothingItem")


class UserFeedback(Base):
    """User feedback on outfit recommendations."""

    __tablename__ = "user_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    outfit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outfits.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    accepted: Mapped[bool | None] = mapped_column(Boolean)
    rating: Mapped[int | None] = mapped_column(Integer)
    comfort_rating: Mapped[int | None] = mapped_column(Integer)
    style_rating: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)

    worn_at: Mapped[date | None] = mapped_column(Date)
    worn_with_modifications: Mapped[bool] = mapped_column(Boolean, default=False)
    modification_notes: Mapped[str | None] = mapped_column(Text)

    # Tracking what user actually wore
    actually_worn: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wore_instead_items: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )  # List of item UUIDs worn instead

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    outfit: Mapped["Outfit"] = relationship("Outfit", back_populates="feedback")
