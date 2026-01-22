"""Learning system models for continuous AI improvement."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.item import ClothingItem
    from app.models.user import User


class UserLearningProfile(Base):
    """
    Learned preferences for a user based on feedback patterns.

    This table stores computed insights that are periodically updated
    based on the user's feedback history. It represents what the system
    has "learned" about the user's tastes.
    """

    __tablename__ = "user_learning_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Learned color preferences (computed from feedback)
    # Format: {"blue": 0.85, "red": 0.6, "green": -0.3} where positive = liked, negative = disliked
    learned_color_scores: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Learned style preferences
    # Format: {"casual": 0.9, "formal": 0.4, "sporty": -0.2}
    learned_style_scores: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Learned occasion preferences
    # Format: {"work": {"formality": "business-casual", "colors": ["blue", "gray"]}}
    learned_occasion_patterns: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Weather-based preferences learned from feedback
    # Format: {"cold": {"preferred_layers": 2, "outerwear_important": true}}
    learned_weather_preferences: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Time-based patterns (e.g., prefers casual on Fridays)
    # Format: {"friday": {"occasion_override": "casual"}, "monday": {"formality": "formal"}}
    learned_temporal_patterns: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Overall recommendation acceptance rate (0-1)
    overall_acceptance_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    # Average ratings by category
    average_overall_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    average_comfort_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    average_style_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))

    # Number of data points used for learning
    feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    outfits_rated: Mapped[int] = mapped_column(Integer, default=0)

    # Learning metadata
    last_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str] = mapped_column(String(20), default="1.0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="learning_profile")


class ItemPairScore(Base):
    """
    Tracks how well pairs of items work together based on feedback.

    When a user accepts/rates an outfit positively, the items in that
    outfit are considered a "good pair". Over time, this builds up
    knowledge of which items complement each other.
    """

    __tablename__ = "item_pair_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # The two items in the pair (item1_id < item2_id to ensure uniqueness)
    item1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clothing_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    item2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clothing_items.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Compatibility score (-1 to 1, positive = good together, negative = avoid)
    compatibility_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)

    # Number of times this pair appeared together in outfits
    times_paired: Mapped[int] = mapped_column(Integer, default=0)

    # Number of times pair was accepted/rejected
    times_accepted: Mapped[int] = mapped_column(Integer, default=0)
    times_rejected: Mapped[int] = mapped_column(Integer, default=0)

    # Sum of ratings when this pair appeared (for averaging)
    total_rating_sum: Mapped[int] = mapped_column(Integer, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)

    # Context tracking (which occasions/weather this pair works well in)
    occasion_performance: Mapped[dict] = mapped_column(JSONB, default=dict)
    weather_performance: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Ensure unique pairs per user (item1 < item2)
    __table_args__ = (
        UniqueConstraint("user_id", "item1_id", "item2_id", name="uq_user_item_pair"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    item1: Mapped["ClothingItem"] = relationship("ClothingItem", foreign_keys=[item1_id])
    item2: Mapped["ClothingItem"] = relationship("ClothingItem", foreign_keys=[item2_id])


class OutfitPerformance(Base):
    """
    Tracks outfit performance metrics for learning.

    This is a denormalized table that stores computed metrics
    about each outfit's performance for faster querying during
    learning computations.
    """

    __tablename__ = "outfit_performances"

    outfit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outfits.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Computed performance score (0-1, higher = better)
    performance_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)

    # Component scores
    acceptance_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    rating_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    wear_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))

    # Context at time of recommendation (denormalized for analysis)
    occasion: Mapped[str] = mapped_column(String(50))
    weather_temp: Mapped[int | None] = mapped_column(Integer)
    weather_condition: Mapped[str | None] = mapped_column(String(50))

    # Item type composition (for pattern analysis)
    # Format: {"top": "shirt", "bottom": "jeans", "shoes": "sneakers"}
    item_composition: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Color composition
    # Format: {"primary_colors": ["blue", "gray"], "color_harmony": "complementary"}
    color_composition: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Was this outfit modified before wearing?
    was_modified: Mapped[bool] = mapped_column(default=False)
    modification_notes: Mapped[str | None] = mapped_column(Text)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User")


class StyleInsight(Base):
    """
    Generated insights about user's style patterns.

    These are human-readable insights generated periodically
    to help users understand their style and improve recommendations.
    """

    __tablename__ = "style_insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Insight category (color, style, occasion, weather, combination, etc.)
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    # Insight type (positive, negative, suggestion, pattern)
    insight_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Human-readable insight text
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Confidence in this insight (0-1)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0.5)

    # Data supporting this insight
    supporting_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Has user acknowledged/dismissed this insight?
    is_acknowledged: Mapped[bool] = mapped_column(default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # When should this insight expire?
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user: Mapped["User"] = relationship("User")
