"""Write surface for externally-authored outfits (suggestions and pairings).

Authored rows are regular outfits with source='external'; no separate table.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.outfit import (
    FamilyOutfitRating,
    Outfit,
    OutfitItem,
    OutfitSource,
    OutfitStatus,
)
from app.models.user import User
from app.services.pairing_service import PAIRING_OCCASION
from app.services.studio_service import validate_item_ownership
from app.utils.timezone import get_user_today


class ExternalOutfitService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_full_outfit(self, outfit_id: UUID) -> Outfit:
        result = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == outfit_id)
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
                selectinload(Outfit.source_item),
                selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
            )
        )
        return result.scalar_one()

    async def _persist_outfit(
        self,
        user: User,
        *,
        ordered_item_ids: list[UUID],
        occasion: str,
        name: str | None = None,
        scheduled_for: date | None,
        source_item_id: UUID | None = None,
        reasoning: str | None,
        style_notes: str | None,
        season: str | None,
        formality: str | None,
        palette: list[str] | None,
        notes: str | None,
    ) -> Outfit:
        await validate_item_ownership(self.db, user.id, ordered_item_ids)

        outfit = Outfit(
            user_id=user.id,
            occasion=occasion,
            scheduled_for=scheduled_for or get_user_today(user),
            source=OutfitSource.external,
            status=OutfitStatus.pending,
            name=name,
            source_item_id=source_item_id,
            reasoning=reasoning,
            style_notes=style_notes,
            season=season,
            formality=formality,
            palette=palette,
            notes=notes,
        )
        self.db.add(outfit)
        await self.db.flush()

        for position, item_id in enumerate(ordered_item_ids):
            self.db.add(OutfitItem(outfit_id=outfit.id, item_id=item_id, position=position))

        await self.db.flush()
        return outfit

    async def create_suggestion(
        self,
        user: User,
        *,
        item_ids: list[UUID],
        occasion: str,
        name: str | None = None,
        scheduled_for: date | None = None,
        reasoning: str | None = None,
        style_notes: str | None = None,
        season: str | None = None,
        formality: str | None = None,
        palette: list[str] | None = None,
        notes: str | None = None,
    ) -> Outfit:
        """Persist an authored suggestion; item positions follow the request order."""
        return await self._persist_outfit(
            user,
            ordered_item_ids=list(dict.fromkeys(item_ids)),
            occasion=occasion,
            name=name,
            scheduled_for=scheduled_for,
            reasoning=reasoning,
            style_notes=style_notes,
            season=season,
            formality=formality,
            palette=palette,
            notes=notes,
        )

    async def create_pairing(
        self,
        user: User,
        *,
        source_item_id: UUID,
        item_ids: list[UUID],
        scheduled_for: date | None = None,
        reasoning: str | None = None,
        style_notes: str | None = None,
        season: str | None = None,
        formality: str | None = None,
        palette: list[str] | None = None,
        notes: str | None = None,
    ) -> Outfit:
        """Persist an authored pairing; the source item leads when absent from item_ids."""
        ordered = (
            list(dict.fromkeys(item_ids))
            if source_item_id in item_ids
            else list(dict.fromkeys([source_item_id, *item_ids]))
        )
        if len(ordered) < 2:
            raise ValueError("A pairing needs at least one partner item")

        return await self._persist_outfit(
            user,
            ordered_item_ids=ordered,
            occasion=PAIRING_OCCASION,
            scheduled_for=scheduled_for,
            source_item_id=source_item_id,
            reasoning=reasoning,
            style_notes=style_notes,
            season=season,
            formality=formality,
            palette=palette,
            notes=notes,
        )
