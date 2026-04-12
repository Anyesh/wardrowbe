from datetime import UTC, date, datetime, timedelta
from itertools import combinations
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import (
    FamilyOutfitRating,
    Outfit,
    OutfitItem,
    OutfitSource,
    OutfitStatus,
)
from app.models.user import User
from app.schemas.item import DEFAULT_WASH_INTERVALS
from app.services.learning_service import LearningService
from app.utils.clothing import canonical_item_order


class ItemOwnershipError(Exception):
    pass


class OutfitWornImmutableError(Exception):
    pass


class OutfitNotTemplateError(Exception):
    pass


class StudioService:
    CLONE_SOFT_IDEMPOTENCY_SECONDS = 5

    def __init__(self, db: AsyncSession):
        self.db = db
        self.learning = LearningService(db)

    async def _validate_item_ownership(
        self, user_id: UUID, item_ids: list[UUID]
    ) -> list[ClothingItem]:
        if not item_ids:
            raise ValueError("items required")

        result = await self.db.execute(
            select(ClothingItem).where(
                and_(
                    ClothingItem.id.in_(item_ids),
                    ClothingItem.user_id == user_id,
                    ClothingItem.status == ItemStatus.ready,
                )
            )
        )
        items = list(result.scalars().all())
        unique_requested = set(item_ids)
        if len(items) != len(unique_requested):
            raise ItemOwnershipError("one or more items do not belong to the caller")
        return items

    def _order_items_canonically(self, items: list[ClothingItem]) -> list[ClothingItem]:
        type_map = {item.id: (item.type or "") for item in items}
        ordered_ids = canonical_item_order([i.id for i in items], type_map)
        by_id = {item.id: item for item in items}
        return [by_id[iid] for iid in ordered_ids]

    async def _apply_wear_tracking(
        self, user_id: UUID, item_ids: list[UUID], worn_at: date
    ) -> None:
        for iid in item_ids:
            existing = await self.db.get(ClothingItem, iid)
            if existing is not None:
                self.db.expire(existing)

        result = await self.db.execute(
            select(ClothingItem).where(
                and_(
                    ClothingItem.id.in_(item_ids),
                    ClothingItem.user_id == user_id,
                )
            )
        )
        items = list(result.scalars().all())

        for item in items:
            effective_interval = (
                item.wash_interval
                if item.wash_interval is not None
                else DEFAULT_WASH_INTERVALS.get(item.type, 3)
            )
            new_wears_since_wash = (item.wears_since_wash or 0) + 1

            await self.db.execute(
                update(ClothingItem)
                .where(ClothingItem.id == item.id)
                .values(
                    wear_count=(item.wear_count or 0) + 1,
                    last_worn_at=func.greatest(
                        func.coalesce(ClothingItem.last_worn_at, worn_at),
                        worn_at,
                    ),
                    wears_since_wash=new_wears_since_wash,
                    needs_wash=new_wears_since_wash >= effective_interval,
                )
            )
            self.db.expire(item)

    async def _reload_outfit(self, outfit_id: UUID) -> Outfit:
        result = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == outfit_id)
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
            )
        )
        return result.scalar_one()

    async def get_full_outfit(self, outfit_id: UUID) -> Outfit:
        result = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == outfit_id)
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
                selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
            )
        )
        return result.scalar_one()

    async def create_from_scratch(
        self,
        user: User,
        item_ids: list[UUID],
        occasion: str,
        name: str | None,
        scheduled_for: date | None,
        mark_worn: bool,
        source_item_id: UUID | None,
    ) -> Outfit:
        items = await self._validate_item_ownership(user.id, item_ids)
        ordered = self._order_items_canonically(items)

        effective_worn = scheduled_for if mark_worn else None

        outfit = Outfit(
            user_id=user.id,
            occasion=occasion,
            scheduled_for=scheduled_for,
            source=OutfitSource.manual,
            status=OutfitStatus.pending,
            name=name,
            source_item_id=source_item_id,
        )
        self.db.add(outfit)
        await self.db.flush()

        for pos, item in enumerate(ordered):
            self.db.add(OutfitItem(outfit_id=outfit.id, item_id=item.id, position=pos))

        feedback = self.learning.create_synthetic_feedback(
            outfit_id=outfit.id, accepted=True, worn_at=effective_worn
        )
        self.db.add(feedback)

        if mark_worn and effective_worn is not None:
            await self._apply_wear_tracking(user.id, [i.id for i in ordered], effective_worn)

        await self.db.flush()
        return await self._reload_outfit(outfit.id)

    async def create_wore_instead(
        self,
        user: User,
        original_outfit_id: UUID,
        item_ids: list[UUID],
        rating: int | None,
        comment: str | None,
        scheduled_for: date | None,
    ) -> Outfit:
        result = await self.db.execute(
            select(Outfit)
            .where(and_(Outfit.id == original_outfit_id, Outfit.user_id == user.id))
            .options(selectinload(Outfit.feedback))
            .with_for_update()
        )
        original = result.scalar_one_or_none()
        if original is None:
            raise LookupError("original outfit not found")

        existing_result = await self.db.execute(
            select(Outfit)
            .where(Outfit.replaces_outfit_id == original.id)
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
            )
        )
        existing_replacement = existing_result.scalar_one_or_none()
        if existing_replacement is not None:
            return existing_replacement

        items = await self._validate_item_ownership(user.id, item_ids)
        ordered = self._order_items_canonically(items)

        effective_date = scheduled_for or original.scheduled_for

        occasion_label = (original.occasion or "Outfit").title()
        replacement = Outfit(
            user_id=user.id,
            occasion=original.occasion,
            scheduled_for=effective_date,
            source=OutfitSource.manual,
            status=OutfitStatus.pending,
            replaces_outfit_id=original.id,
            name=f"{occasion_label} (wore instead)",
        )
        self.db.add(replacement)
        await self.db.flush()

        for pos, item in enumerate(ordered):
            self.db.add(OutfitItem(outfit_id=replacement.id, item_id=item.id, position=pos))

        feedback = self.learning.create_synthetic_feedback(
            outfit_id=replacement.id,
            accepted=True,
            worn_at=effective_date,
            rating=rating,
            comment=comment,
        )
        self.db.add(feedback)

        original.status = OutfitStatus.rejected
        original.responded_at = datetime.utcnow()

        if effective_date is not None:
            await self._apply_wear_tracking(user.id, [i.id for i in ordered], effective_date)

        await self.db.flush()
        return await self._reload_outfit(replacement.id)

    async def clone_to_lookbook(
        self,
        user: User,
        source_outfit_id: UUID,
        name: str,
    ) -> Outfit:
        result = await self.db.execute(
            select(Outfit)
            .where(and_(Outfit.id == source_outfit_id, Outfit.user_id == user.id))
            .options(selectinload(Outfit.items).selectinload(OutfitItem.item))
        )
        source = result.scalar_one_or_none()
        if source is None:
            raise LookupError("source outfit not found")

        recent_cutoff = datetime.now(UTC) - timedelta(seconds=self.CLONE_SOFT_IDEMPOTENCY_SECONDS)
        recent_result = await self.db.execute(
            select(Outfit)
            .where(
                and_(
                    Outfit.user_id == user.id,
                    Outfit.cloned_from_outfit_id == source.id,
                    Outfit.scheduled_for.is_(None),
                    Outfit.created_at >= recent_cutoff,
                )
            )
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
            )
        )
        existing = recent_result.scalar_one_or_none()
        if existing is not None:
            return existing

        clone = Outfit(
            user_id=user.id,
            occasion=source.occasion,
            scheduled_for=None,
            source=OutfitSource.manual,
            status=OutfitStatus.pending,
            cloned_from_outfit_id=source.id,
            source_item_id=source.source_item_id,
            name=name,
        )
        self.db.add(clone)
        await self.db.flush()

        for oi in sorted(source.items, key=lambda x: x.position):
            self.db.add(
                OutfitItem(
                    outfit_id=clone.id,
                    item_id=oi.item_id,
                    position=oi.position,
                    layer_type=oi.layer_type,
                )
            )

        feedback = self.learning.create_synthetic_feedback(
            outfit_id=clone.id, accepted=True, worn_at=None
        )
        self.db.add(feedback)

        await self.db.flush()
        return await self._reload_outfit(clone.id)

    async def wear_today(self, user: User, template_id: UUID, scheduled_for: date | None) -> Outfit:
        result = await self.db.execute(
            select(Outfit)
            .where(and_(Outfit.id == template_id, Outfit.user_id == user.id))
            .options(selectinload(Outfit.items).selectinload(OutfitItem.item))
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise LookupError("template not found")

        if template.scheduled_for is not None:
            raise OutfitNotTemplateError("wear_today requires a lookbook template")

        target_date = scheduled_for or date.today()

        wear = Outfit(
            user_id=user.id,
            occasion=template.occasion,
            scheduled_for=target_date,
            source=OutfitSource.manual,
            status=OutfitStatus.pending,
            cloned_from_outfit_id=template.id,
            source_item_id=template.source_item_id,
            name=template.name,
        )
        self.db.add(wear)
        await self.db.flush()

        for oi in sorted(template.items, key=lambda x: x.position):
            self.db.add(
                OutfitItem(
                    outfit_id=wear.id,
                    item_id=oi.item_id,
                    position=oi.position,
                    layer_type=oi.layer_type,
                )
            )

        feedback = self.learning.create_synthetic_feedback(
            outfit_id=wear.id, accepted=True, worn_at=target_date
        )
        self.db.add(feedback)

        await self._apply_wear_tracking(user.id, [oi.item_id for oi in template.items], target_date)

        await self.db.flush()
        return await self._reload_outfit(wear.id)

    async def patch_outfit(
        self,
        user: User,
        outfit_id: UUID,
        name: str | None,
        items: list[UUID] | None,
    ) -> Outfit:
        result = await self.db.execute(
            select(Outfit)
            .where(and_(Outfit.id == outfit_id, Outfit.user_id == user.id))
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
            )
        )
        outfit = result.scalar_one_or_none()
        if outfit is None:
            raise LookupError("outfit not found")

        if name is not None:
            outfit.name = name

        if items is not None:
            if outfit.feedback is not None and outfit.feedback.worn_at is not None:
                raise OutfitWornImmutableError("cannot modify items on a worn outfit")

            new_items = await self._validate_item_ownership(user.id, items)
            ordered = self._order_items_canonically(new_items)

            old_item_ids = [oi.item_id for oi in outfit.items]
            new_item_ids = [i.id for i in ordered]

            old_pairs = {tuple(sorted([a, b])) for a, b in combinations(old_item_ids, 2)}
            new_pairs = {tuple(sorted([a, b])) for a, b in combinations(new_item_ids, 2)}
            added = new_pairs - old_pairs
            removed = old_pairs - new_pairs

            self.db.expire(outfit, attribute_names=["items"])
            await self.db.execute(sa_delete(OutfitItem).where(OutfitItem.outfit_id == outfit.id))
            await self.db.flush()

            for pos, item in enumerate(ordered):
                self.db.add(OutfitItem(outfit_id=outfit.id, item_id=item.id, position=pos))
            await self.db.flush()

            refreshed = await self._reload_outfit(outfit.id)
            if added or removed:
                await self.learning.process_item_diff(
                    refreshed, added_pairs=added, removed_pairs=removed
                )
            outfit = refreshed

        await self.db.flush()
        return await self._reload_outfit(outfit.id)
