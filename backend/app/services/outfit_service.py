from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem
from app.models.outfit import (
    FamilyOutfitRating,
    Outfit,
    OutfitItem,
    OutfitSource,
    OutfitStatus,
    UserFeedback,
)
from app.models.user import User
from app.schemas.outfit import FeedbackRequest
from app.services.item_service import ItemService
from app.services.studio_service import StudioService
from app.utils.timezone import get_user_today


@dataclass
class OutfitListFilters:
    user_id: UUID
    status_filter: str | None = None
    occasion: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    source: str | None = None
    is_lookbook: bool | None = None
    is_replacement: bool | None = None
    has_source_item: bool | None = None
    item_type: str | None = None
    family_member_view: bool = False
    search: str | None = None
    occasions: list[str] | None = None
    cloned_from_outfit_id: UUID | None = None


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class OutfitService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def set_status(self, outfit_id: UUID, user_id: UUID, new_status: OutfitStatus) -> Outfit:
        result = await self.db.execute(
            select(Outfit).where(and_(Outfit.id == outfit_id, Outfit.user_id == user_id))
        )
        outfit = result.scalar_one_or_none()

        if not outfit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"message": "Outfit not found", "error_code": "OUTFIT_NOT_FOUND"},
            )

        outfit.status = new_status
        outfit.responded_at = datetime.utcnow()
        await self.db.commit()

        refreshed = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == outfit_id)
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
                selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
            )
        )
        return refreshed.scalar_one()

    def _build_filter_clauses(self, filters: OutfitListFilters) -> list:
        clauses = [Outfit.user_id == filters.user_id]

        if filters.family_member_view:
            clauses.append(Outfit.scheduled_for.is_not(None))

        if filters.status_filter:
            parsed_statuses: list[OutfitStatus] = []
            for s in filters.status_filter.split(","):
                try:
                    parsed_statuses.append(OutfitStatus(s.strip()))
                except ValueError:
                    continue
            if len(parsed_statuses) == 1:
                clauses.append(Outfit.status == parsed_statuses[0])
            elif parsed_statuses:
                clauses.append(Outfit.status.in_(parsed_statuses))

        if filters.occasion:
            clauses.append(Outfit.occasion == filters.occasion)

        if filters.date_from:
            clauses.append(Outfit.scheduled_for >= filters.date_from)

        if filters.date_to:
            clauses.append(Outfit.scheduled_for <= filters.date_to)

        if filters.source:
            source_values: list[OutfitSource] = []
            for s in filters.source.split(","):
                try:
                    source_values.append(OutfitSource(s.strip()))
                except ValueError:
                    continue
            if len(source_values) == 1:
                clauses.append(Outfit.source == source_values[0])
            elif source_values:
                clauses.append(Outfit.source.in_(source_values))

        if filters.is_lookbook is True:
            clauses.append(Outfit.scheduled_for.is_(None))
        elif filters.is_lookbook is False:
            clauses.append(Outfit.scheduled_for.is_not(None))

        if filters.is_replacement is True:
            clauses.append(Outfit.replaces_outfit_id.is_not(None))
        elif filters.is_replacement is False:
            clauses.append(Outfit.replaces_outfit_id.is_(None))

        if filters.has_source_item is True:
            clauses.append(Outfit.source_item_id.is_not(None))
        elif filters.has_source_item is False:
            clauses.append(Outfit.source_item_id.is_(None))

        if filters.item_type:
            clauses.append(Outfit.source_item.has(ClothingItem.type == filters.item_type))

        # Occasions match too because unnamed outfits are titled by their translated occasion;
        # the client sends the occasion keys whose label contains the search term.
        search_matches = []
        if filters.search:
            search_matches.append(
                Outfit.name.ilike(f"%{_escape_like(filters.search)}%", escape="\\")
            )
        if filters.occasions:
            search_matches.append(Outfit.occasion.in_(filters.occasions))
        if search_matches:
            clauses.append(or_(*search_matches))

        if filters.cloned_from_outfit_id is not None:
            clauses.append(Outfit.cloned_from_outfit_id == filters.cloned_from_outfit_id)

        return clauses

    async def get_ids_by_filter(
        self,
        filters: OutfitListFilters,
        excluded_ids: list[UUID] | None = None,
        after_id: UUID | None = None,
        limit: int | None = None,
    ) -> list[UUID]:
        clauses = self._build_filter_clauses(filters)
        if excluded_ids:
            clauses.append(Outfit.id.notin_(excluded_ids))
        if after_id is not None:
            clauses.append(Outfit.id > after_id)

        # invariant: a capped bulk delete resumes with after_id, so the order
        # has to be total and stable across requests.
        query = select(Outfit.id).where(and_(*clauses)).order_by(Outfit.id.asc())
        if limit is not None:
            query = query.limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_with_filters(
        self, filters: OutfitListFilters, page: int, page_size: int
    ) -> tuple[list[Outfit], int]:
        clauses = self._build_filter_clauses(filters)

        count_query: Select = select(func.count()).select_from(Outfit).where(and_(*clauses))
        total = (await self.db.execute(count_query)).scalar_one()

        query = (
            select(Outfit)
            .where(and_(*clauses))
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
                selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
            )
            .order_by(Outfit.created_at.desc(), Outfit.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.db.execute(query)
        outfits = list(result.scalars().all())
        return outfits, total

    async def verify_family_access(self, current_user: User, family_member_id: UUID) -> UUID:
        if not current_user.family_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "You must be in a family to view family member outfits",
                    "error_code": "NOT_IN_FAMILY",
                },
            )
        member_result = await self.db.execute(
            select(User).where(User.id == family_member_id, User.is_active == True)  # noqa: E712
        )
        member = member_result.scalar_one_or_none()
        if not member or member.family_id != current_user.family_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not in your family",
            )
        return family_member_id

    async def apply_feedback(
        self, user: User, outfit: Outfit, request: FeedbackRequest
    ) -> tuple[UserFeedback, Outfit | None]:
        if outfit.feedback:
            feedback = outfit.feedback
        else:
            feedback = UserFeedback(outfit_id=outfit.id)
            outfit.feedback = feedback
            self.db.add(feedback)

        if request.accepted is not None:
            feedback.accepted = request.accepted
            outfit.status = OutfitStatus.accepted if request.accepted else OutfitStatus.rejected
            outfit.responded_at = datetime.utcnow()

        if request.rating is not None:
            feedback.rating = request.rating
        if request.comfort_rating is not None:
            feedback.comfort_rating = request.comfort_rating
        if request.style_rating is not None:
            feedback.style_rating = request.style_rating
        if request.comment is not None:
            feedback.comment = request.comment
        if request.worn and not feedback.worn_at:
            user_today = get_user_today(user)
            feedback.worn_at = user_today
            await ItemService(self.db).record_wears(
                user.id,
                [outfit_item.item_id for outfit_item in outfit.items],
                user_today,
                occasion=outfit.occasion,
                outfit_id=outfit.id,
            )
        if request.worn_with_modifications is not None:
            feedback.worn_with_modifications = request.worn_with_modifications
        if request.modification_notes is not None:
            feedback.modification_notes = request.modification_notes
        if request.actually_worn is not None:
            feedback.actually_worn = request.actually_worn
        replacement: Outfit | None = None
        if request.wore_instead_items is not None:
            feedback.wore_instead_items = [str(item_id) for item_id in request.wore_instead_items]
            if request.wore_instead_items:
                studio_service = StudioService(self.db)
                replacement = await studio_service.create_wore_instead(
                    user=user,
                    original_outfit_id=outfit.id,
                    item_ids=list(request.wore_instead_items),
                    rating=request.rating,
                    comment=request.comment,
                    scheduled_for=None,
                )

        return feedback, replacement
