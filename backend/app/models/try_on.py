"""Outfit try-on models: the user's reference photo and one generated image per outfit."""

import enum
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, event, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.outfit import Outfit

logger = logging.getLogger(__name__)


class TryOnStatus(enum.StrEnum):
    pending = "pending"
    ready = "ready"
    failed = "failed"


class TryOnPhoto(Base):
    __tablename__ = "try_on_photos"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    medium_path: Mapped[str | None] = mapped_column(String(500))
    # sha256 of the stored image bytes; part of every try-on's cache key.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def file_paths(self) -> list[str | None]:
        return [self.image_path, self.medium_path]


class OutfitTryOn(Base):
    __tablename__ = "outfit_try_ons"

    outfit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outfits.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[TryOnStatus] = mapped_column(
        Enum(TryOnStatus, name="try_on_status"), nullable=False, default=TryOnStatus.pending
    )
    error_code: Mapped[str | None] = mapped_column(String(50))
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(500))
    medium_path: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    outfit: Mapped["Outfit"] = relationship("Outfit", back_populates="try_on")

    @property
    def file_paths(self) -> list[str | None]:
        return [self.image_path, self.medium_path]


# Files go only after the transaction that deleted their rows has committed, so a rolled-back
# delete never leaves a row pointing at a missing file. Rows removed by a database-level cascade
# (a user deleted directly in SQL) are not seen here and leave their files behind.
_PENDING_FILES = "try_on_files_to_delete"


@event.listens_for(Session, "before_flush")
def _collect_deleted_files(session: Session, flush_context, instances) -> None:
    for obj in session.deleted:
        if isinstance(obj, TryOnPhoto | OutfitTryOn):
            session.info.setdefault(_PENDING_FILES, []).extend(p for p in obj.file_paths if p)


@event.listens_for(Session, "after_commit")
def _delete_collected_files(session: Session) -> None:
    paths = session.info.pop(_PENDING_FILES, None)
    if not paths:
        return
    # Imported here: image_service pulls in the heavy image stack and this module loads with
    # every model.
    from app.services.image_service import ImageService

    try:
        ImageService().delete_images({p: p for p in paths})
    except OSError:
        logger.warning("Could not delete %d try-on file(s)", len(paths))


@event.listens_for(Session, "after_rollback")
def _forget_collected_files(session: Session) -> None:
    session.info.pop(_PENDING_FILES, None)
