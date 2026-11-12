"""Shared logic for outfit try-on: cache key, model inputs and error codes."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.item import ClothingItem
from app.models.outfit import Outfit, OutfitItem
from app.models.try_on import TryOnPhoto
from app.services.image_generation import PROMPT_VERSION, Garment, garment_record
from app.services.image_service import ImageService

# A pending row older than this is treated as lost (worker killed mid-job) and may be redone.
PENDING_TIMEOUT = timedelta(minutes=15)

REFERENCE_MAX_PX = 1600
GARMENT_MAX_PX = 800

ERROR_NO_PHOTO = "TRY_ON_NO_PHOTO"
ERROR_ITEM_IMAGE_MISSING = "TRY_ON_ITEM_IMAGE_MISSING"
ERROR_DAILY_LIMIT = "TRY_ON_DAILY_LIMIT"


class ItemImageMissingError(Exception):
    pass


@dataclass(frozen=True)
class OutfitGarment:
    item: ClothingItem
    layer: str | None

    @property
    def garment(self) -> Garment:
        return Garment(
            type=self.item.type,
            subtype=self.item.subtype,
            colors=list(self.item.colors or []),
            primary_color=self.item.primary_color,
            layer=self.layer,
        )

    @property
    def image_path(self) -> str | None:
        return self.item.medium_path or self.item.image_path or None


def is_pending_fresh(started_at: datetime) -> bool:
    return datetime.now(UTC) - started_at < PENDING_TIMEOUT


async def load_outfit(db: AsyncSession, outfit_id, user_id) -> Outfit | None:
    result = await db.execute(
        select(Outfit)
        .where(Outfit.id == outfit_id, Outfit.user_id == user_id)
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item), selectinload(Outfit.try_on)
        )
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def load_photo(db: AsyncSession, user_id) -> TryOnPhoto | None:
    result = await db.execute(select(TryOnPhoto).where(TryOnPhoto.user_id == user_id))
    return result.scalar_one_or_none()


def outfit_garments(outfit: Outfit) -> list[OutfitGarment]:
    """The outfit's items in the fixed order they are sent to the model."""
    garments = [OutfitGarment(oi.item, oi.layer_type) for oi in outfit.items if oi.item]
    return sorted(garments, key=lambda g: (g.item.type, str(g.item.id)))


def _image_identity(image_service: ImageService, garment: OutfitGarment) -> list:
    """Something that changes whenever the picture sent for this item changes.

    Rotating or removing the background rewrites the file at the same path, so the path alone is
    not enough; the file's mtime catches those without reacting to unrelated item edits.
    """
    path = garment.image_path
    mtime = 0
    if path:
        try:
            mtime = image_service.get_image_path(path).stat().st_mtime_ns
        except OSError:
            mtime = 0
    return [path, mtime, garment.item.image_hash]


def compute_cache_key(
    photo: TryOnPhoto, garments: list[OutfitGarment], image_service: ImageService
) -> str:
    payload = [
        PROMPT_VERSION,
        get_settings().ai_image_model,
        photo.content_hash,
        [
            [
                str(g.item.id),
                _image_identity(image_service, g),
                garment_record(g.garment),
            ]
            for g in garments
        ],
    ]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def read_model_inputs(
    photo: TryOnPhoto, garments: list[OutfitGarment], image_service: ImageService
) -> tuple[bytes, list[bytes]]:
    """Blocking: re-encode the reference photo and each garment image for the model."""
    person = image_service.load_for_model(photo.image_path, REFERENCE_MAX_PX)
    images = []
    for g in garments:
        if not g.image_path:
            raise ItemImageMissingError
        try:
            images.append(image_service.load_for_model(g.image_path, GARMENT_MAX_PX, quality=85))
        except (OSError, ValueError):
            raise ItemImageMissingError from None
    return person, images
