import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# 1 = must have, 2 = would like, 3 = some day
DEFAULT_PRIORITY = 2


class WishlistItem(Base):
    """Something the user wants to buy: a photo (a link's preview image or an upload), notes,
    the shop link and a price, kept apart from the wardrobe until it is bought."""

    __tablename__ = "wishlist_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(1000))
    # A picture on the web (the shop's own), shown as is; an upload is stored like item photos.
    image_url: Mapped[str | None] = mapped_column(String(1000))
    image_path: Mapped[str | None] = mapped_column(String(500))
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    item_type: Mapped[str | None] = mapped_column(String(50))
    priority: Mapped[int] = mapped_column(Integer, default=DEFAULT_PRIORITY, nullable=False)
    bought: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Price watch: the shop's latest price, when it was read, and when it last went down
    # compared with `price` (the price the user noted).
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    price_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_dropped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
