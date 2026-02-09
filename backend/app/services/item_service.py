from collections import Counter
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem, ItemHistory, ItemStatus, WashHistory
from app.schemas.item import DEFAULT_WASH_INTERVALS, ItemCreate, ItemFilter, ItemUpdate


class ItemService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, item_id: UUID, user_id: UUID) -> ClothingItem | None:
        result = await self.db.execute(
            select(ClothingItem)
            .where(and_(ClothingItem.id == item_id, ClothingItem.user_id == user_id))
            .options(selectinload(ClothingItem.additional_images))
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        user_id: UUID,
        filters: ItemFilter,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ClothingItem], int]:
        # Base query
        query = (
            select(ClothingItem)
            .where(ClothingItem.user_id == user_id)
            .options(selectinload(ClothingItem.additional_images))
        )

        # Apply filters
        if filters.type:
            query = query.where(ClothingItem.type == filters.type)
        if filters.subtype:
            query = query.where(ClothingItem.subtype == filters.subtype)
        if filters.status:
            query = query.where(ClothingItem.status == filters.status)
        if filters.favorite is not None:
            query = query.where(ClothingItem.favorite == filters.favorite)
        if filters.colors:
            query = query.where(ClothingItem.colors.overlap(filters.colors))

        # Archive filter
        query = query.where(ClothingItem.is_archived == filters.is_archived)

        # Needs wash filter
        if filters.needs_wash is not None:
            query = query.where(ClothingItem.needs_wash == filters.needs_wash)

        # Search filter
        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    ClothingItem.name.ilike(search_term),
                    ClothingItem.brand.ilike(search_term),
                    ClothingItem.type.ilike(search_term),
                    ClothingItem.notes.ilike(search_term),
                )
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Sorting
        sort_columns = {
            "created_at": ClothingItem.created_at,
            "last_worn": ClothingItem.last_worn_at,
            "wear_count": ClothingItem.wear_count,
            "name": ClothingItem.name,
            "type": ClothingItem.type,
        }
        sort_col = sort_columns.get(filters.sort_by or "", ClothingItem.created_at)
        if filters.sort_order == "asc":
            query = query.order_by(sort_col.asc().nulls_last())
        else:
            query = query.order_by(sort_col.desc().nulls_last())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_ids_by_filter(
        self,
        user_id: UUID,
        type_filter: str | None = None,
        search: str | None = None,
        is_archived: bool = False,
        excluded_ids: list[UUID] | None = None,
    ) -> list[UUID]:
        query = select(ClothingItem.id).where(ClothingItem.user_id == user_id)

        if type_filter:
            query = query.where(ClothingItem.type == type_filter)

        query = query.where(ClothingItem.is_archived == is_archived)

        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    ClothingItem.name.ilike(search_term),
                    ClothingItem.brand.ilike(search_term),
                    ClothingItem.type.ilike(search_term),
                    ClothingItem.notes.ilike(search_term),
                )
            )

        if excluded_ids:
            query = query.where(ClothingItem.id.notin_(excluded_ids))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def find_duplicate_by_hash(
        self,
        user_id: UUID,
        image_hash: str,
        threshold: int = 8,
    ) -> ClothingItem | None:
        # For exact duplicate detection (same hash)
        result = await self.db.execute(
            select(ClothingItem).where(
                and_(
                    ClothingItem.user_id == user_id,
                    ClothingItem.image_hash == image_hash,
                    not ClothingItem.is_archived,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: UUID,
        item_data: ItemCreate,
        image_paths: dict[str, str],
    ) -> ClothingItem:
        # Build tags dict
        tags = {}
        if item_data.tags:
            tags = item_data.tags.model_dump(exclude_none=True)

        # Create item
        item = ClothingItem(
            user_id=user_id,
            image_path=image_paths["image_path"],
            thumbnail_path=image_paths.get("thumbnail_path"),
            medium_path=image_paths.get("medium_path"),
            image_hash=image_paths.get("image_hash"),
            type=item_data.type,
            subtype=item_data.subtype,
            tags=tags,
            colors=item_data.colors or [],
            primary_color=item_data.primary_color,
            status=ItemStatus.processing,  # AI analysis will update to ready
            name=item_data.name,
            brand=item_data.brand,
            notes=item_data.notes,
            purchase_date=item_data.purchase_date,
            purchase_price=item_data.purchase_price,
            favorite=item_data.favorite,
        )

        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item, ["additional_images"])
        return item

    async def update(self, item: ClothingItem, item_data: ItemUpdate) -> ClothingItem:
        update_data = item_data.model_dump(exclude_unset=True)

        # Handle tags specially
        if "tags" in update_data and update_data["tags"]:
            update_data["tags"] = update_data["tags"].model_dump(exclude_none=True)

        for field, value in update_data.items():
            setattr(item, field, value)

        await self.db.flush()
        # Re-fetch with eager loading to ensure relationships are properly loaded
        result = await self.get_by_id(item.id, item.user_id)
        return result  # type: ignore[return-value]

    async def delete(self, item: ClothingItem) -> None:
        await self.db.delete(item)
        await self.db.flush()

    async def archive(
        self,
        item: ClothingItem,
        reason: str | None = None,
    ) -> ClothingItem:
        item.is_archived = True
        item.archived_at = datetime.now(UTC)
        item.archive_reason = reason
        item.status = ItemStatus.archived
        await self.db.flush()
        # Re-fetch with eager loading to ensure relationships are properly loaded
        result = await self.get_by_id(item.id, item.user_id)
        return result  # type: ignore[return-value]

    async def restore(self, item: ClothingItem) -> ClothingItem:
        item.is_archived = False
        item.archived_at = None
        item.archive_reason = None
        item.status = ItemStatus.ready
        await self.db.flush()
        # Re-fetch with eager loading to ensure relationships are properly loaded
        result = await self.get_by_id(item.id, item.user_id)
        return result  # type: ignore[return-value]

    async def log_wear(
        self,
        item: ClothingItem,
        worn_at: date,
        occasion: str | None = None,
        notes: str | None = None,
        outfit_id: UUID | None = None,
    ) -> ItemHistory:
        # Create history entry
        history = ItemHistory(
            item_id=item.id,
            outfit_id=outfit_id,
            worn_at=worn_at,
            occasion=occasion,
            notes=notes,
        )
        self.db.add(history)

        # Update item stats
        item.wear_count += 1
        item.last_worn_at = worn_at

        # Update wash tracking
        item.wears_since_wash += 1
        effective_interval = (
            item.wash_interval
            if item.wash_interval is not None
            else DEFAULT_WASH_INTERVALS.get(item.type, 3)
        )
        item.needs_wash = item.wears_since_wash >= effective_interval

        await self.db.flush()
        await self.db.refresh(history)
        return history

    async def log_wash(
        self,
        item: ClothingItem,
        washed_at: date,
        method: str | None = None,
        notes: str | None = None,
    ) -> WashHistory:
        wash = WashHistory(
            item_id=item.id,
            washed_at=washed_at,
            method=method,
            notes=notes,
        )
        self.db.add(wash)

        # Reset wash tracking
        item.wears_since_wash = 0
        item.last_washed_at = washed_at
        item.needs_wash = False

        await self.db.flush()
        await self.db.refresh(wash)
        return wash

    async def get_wash_history(
        self,
        item_id: UUID,
        limit: int = 10,
    ) -> list[WashHistory]:
        result = await self.db.execute(
            select(WashHistory)
            .where(WashHistory.item_id == item_id)
            .order_by(WashHistory.washed_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_wear_history(
        self,
        item_id: UUID,
        limit: int = 10,
    ) -> list[ItemHistory]:
        result = await self.db.execute(
            select(ItemHistory)
            .where(ItemHistory.item_id == item_id)
            .order_by(ItemHistory.worn_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_wear_stats(self, item: ClothingItem, user_timezone: str = "UTC") -> dict:
        # Calculate today's date in user's timezone
        try:
            user_tz = ZoneInfo(user_timezone)
        except Exception:
            user_tz = ZoneInfo("UTC")
        user_today = datetime.now(UTC).astimezone(user_tz).date()

        # Days since last worn
        days_since_last_worn = None
        if item.last_worn_at:
            days_since_last_worn = (user_today - item.last_worn_at).days

        # Get all wear history for this item
        result = await self.db.execute(
            select(ItemHistory)
            .where(ItemHistory.item_id == item.id)
            .order_by(ItemHistory.worn_at.desc())
        )
        history = list(result.scalars().all())

        # Average wears per month (over last 6 months)
        six_months_ago = user_today - timedelta(days=180)
        recent_wears = [h for h in history if h.worn_at >= six_months_ago]
        avg_per_month = round(len(recent_wears) / 6, 1) if recent_wears else 0

        # Wear by month (last 6 months)
        wear_by_month: dict[str, int] = {}
        for i in range(5, -1, -1):
            d = user_today - timedelta(days=30 * i)
            key = d.strftime("%Y-%m")
            wear_by_month[key] = 0
        for h in recent_wears:
            key = h.worn_at.strftime("%Y-%m")
            if key in wear_by_month:
                wear_by_month[key] += 1

        # Wear by day of week
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        wear_by_day = dict.fromkeys(day_names, 0)
        for h in history:
            wear_by_day[day_names[h.worn_at.weekday()]] += 1

        # Most common occasion
        occasions = [h.occasion for h in history if h.occasion]
        most_common_occasion = Counter(occasions).most_common(1)[0][0] if occasions else None

        return {
            "total_wears": item.wear_count,
            "days_since_last_worn": days_since_last_worn,
            "average_wears_per_month": avg_per_month,
            "wear_by_month": wear_by_month,
            "wear_by_day_of_week": wear_by_day,
            "most_common_occasion": most_common_occasion,
        }

    async def get_item_types(self, user_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(ClothingItem.type, func.count(ClothingItem.id).label("count"))
            .where(
                and_(
                    ClothingItem.user_id == user_id,
                    ClothingItem.is_archived == False,  # noqa: E712
                )
            )
            .group_by(ClothingItem.type)
            .order_by(func.count(ClothingItem.id).desc())
        )
        return [{"type": row.type, "count": row.count} for row in result.all()]

    async def get_color_distribution(self, user_id: UUID) -> list[dict]:
        result = await self.db.execute(
            select(
                func.unnest(ClothingItem.colors).label("color"),
                func.count().label("count"),
            )
            .where(
                and_(
                    ClothingItem.user_id == user_id,
                    ClothingItem.is_archived == False,  # noqa: E712
                )
            )
            .group_by("color")
            .order_by(func.count().desc())
        )
        return [{"color": row.color, "count": row.count} for row in result.all()]
