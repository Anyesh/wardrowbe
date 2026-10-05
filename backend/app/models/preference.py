import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.preference_defaults import (
    DEFAULT_LAYERING_PREFERENCE,
    DEFAULT_OCCASION,
    DEFAULT_PREFER_UNDERUSED_ITEMS,
    DEFAULT_TEMPERATURE_SENSITIVITY,
    DEFAULT_TEMPERATURE_UNIT,
    DEFAULT_VARIETY_LEVEL,
)
from app.utils.scales import (
    DEFAULT_AVOID_REPEAT_DAYS,
    DEFAULT_COLD_THRESHOLD,
    DEFAULT_HOT_THRESHOLD,
)

if TYPE_CHECKING:
    from app.models.user import User


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Color preferences
    color_favorites: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    color_avoid: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Style preferences
    style_profile: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Occasion settings
    default_occasion: Mapped[str] = mapped_column(String(50), default=DEFAULT_OCCASION)
    occasion_preferences: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Temperature/comfort
    temperature_unit: Mapped[str] = mapped_column(String(20), default=DEFAULT_TEMPERATURE_UNIT)
    temperature_sensitivity: Mapped[str] = mapped_column(
        String(20), default=DEFAULT_TEMPERATURE_SENSITIVITY
    )
    cold_threshold: Mapped[int] = mapped_column(Integer, default=DEFAULT_COLD_THRESHOLD)
    hot_threshold: Mapped[int] = mapped_column(Integer, default=DEFAULT_HOT_THRESHOLD)
    layering_preference: Mapped[str] = mapped_column(
        String(20), default=DEFAULT_LAYERING_PREFERENCE
    )

    # Recommendation settings
    avoid_repeat_days: Mapped[int] = mapped_column(Integer, default=DEFAULT_AVOID_REPEAT_DAYS)
    prefer_underused_items: Mapped[bool] = mapped_column(
        Boolean, default=DEFAULT_PREFER_UNDERUSED_ITEMS
    )
    variety_level: Mapped[str] = mapped_column(String(20), default=DEFAULT_VARIETY_LEVEL)

    # Restrictions
    excluded_item_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    excluded_combinations: Mapped[list] = mapped_column(JSONB, default=list)

    # AI Settings - list of endpoint configs
    # Each endpoint: {url, vision_model, text_model, name, enabled}
    ai_endpoints: Mapped[list] = mapped_column(JSONB, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="preferences")
