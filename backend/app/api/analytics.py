from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, computed_field
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import Outfit, OutfitStatus, UserFeedback
from app.models.user import User
from app.utils.auth import get_current_user
from app.utils.clothing import WardrobeComposition, count_composition
from app.utils.signed_urls import sign_image_url

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class ColorDistribution(BaseModel):
    color: str
    count: int
    percentage: float


class TypeDistribution(BaseModel):
    type: str
    count: int
    percentage: float


class WearStats(BaseModel):
    id: UUID
    name: str | None
    type: str
    primary_color: str | None
    thumbnail_path: str | None
    wear_count: int
    last_worn_at: date | None

    @computed_field
    @property
    def thumbnail_url(self) -> str | None:
        if self.thumbnail_path:
            return sign_image_url(self.thumbnail_path)
        return None


class AcceptanceRateTrend(BaseModel):
    period: str
    total: int
    accepted: int
    rejected: int
    rate: float


class WardrobeStats(BaseModel):
    total_items: int
    items_by_status: dict[str, int]
    total_outfits: int
    outfits_this_week: int
    outfits_this_month: int
    acceptance_rate: float | None
    average_rating: float | None
    total_wears: int


class AnalyticsResponse(BaseModel):
    wardrobe: WardrobeStats
    color_distribution: list[ColorDistribution]
    type_distribution: list[TypeDistribution]
    most_worn: list[WearStats]
    least_worn: list[WearStats]
    never_worn: list[WearStats]
    acceptance_trend: list[AcceptanceRateTrend]
    insights: list[str]


def composition_insights(c: WardrobeComposition) -> list[str]:
    # Layers (cardigans, vests) need something underneath, so they are judged against
    # base tops rather than counted as tops themselves. Dresses count as something to
    # layer over too, because cardigans and vests are worn over dresses as often as over shirts.
    if c.layers >= 3 and c.layers > 2 * (c.base_tops + c.full_body):
        return [
            "Most of your tops are layers like cardigans and vests. Add a few basics to wear under them!"
        ]

    # A dress-first wardrobe doesn't need its few separates to balance.
    if c.full_body >= c.base_tops + c.bottoms:
        return []

    if c.base_tops > 0 and c.bottoms > 0:
        ratio = c.base_tops / c.bottoms
        if ratio > 3:
            return ["You have many more tops than bottoms. Consider adding pants or skirts!"]
        if ratio < 0.5:
            return ["You have more bottoms than tops. Consider adding some shirts!"]
    return []


@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: int = Query(30, ge=7, le=365, description="Number of days for trends"),
) -> AnalyticsResponse:
    # Calculate date ranges
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # === Wardrobe Stats ===
    # Total items and status breakdown
    items_query = select(
        func.count(ClothingItem.id).label("total"),
        func.sum(case((ClothingItem.status == ItemStatus.ready, 1), else_=0)).label("ready"),
        func.sum(case((ClothingItem.status == ItemStatus.processing, 1), else_=0)).label(
            "processing"
        ),
        func.sum(case((ClothingItem.status == ItemStatus.archived, 1), else_=0)).label("archived"),
        func.sum(case((ClothingItem.status == ItemStatus.error, 1), else_=0)).label("error"),
        func.sum(ClothingItem.wear_count).label("total_wears"),
    ).where(ClothingItem.user_id == current_user.id)

    items_result = await db.execute(items_query)
    items_row = items_result.one()

    total_items = items_row.total or 0
    items_by_status = {
        "ready": items_row.ready or 0,
        "processing": items_row.processing or 0,
        "archived": items_row.archived or 0,
        "error": items_row.error or 0,
    }
    total_wears = items_row.total_wears or 0

    # Outfit stats
    outfits_query = select(
        func.count(Outfit.id).label("total"),
        func.sum(case((Outfit.created_at >= week_ago, 1), else_=0)).label("this_week"),
        func.sum(case((Outfit.created_at >= month_ago, 1), else_=0)).label("this_month"),
        func.sum(case((Outfit.status == OutfitStatus.accepted, 1), else_=0)).label("accepted"),
        func.sum(case((Outfit.status == OutfitStatus.rejected, 1), else_=0)).label("rejected"),
    ).where(Outfit.user_id == current_user.id)

    outfits_result = await db.execute(outfits_query)
    outfits_row = outfits_result.one()

    total_outfits = outfits_row.total or 0
    outfits_this_week = outfits_row.this_week or 0
    outfits_this_month = outfits_row.this_month or 0
    accepted = outfits_row.accepted or 0
    rejected = outfits_row.rejected or 0

    responded = accepted + rejected
    acceptance_rate = (accepted / responded * 100) if responded > 0 else None

    # Average rating from feedback table
    rating_query = (
        select(func.avg(UserFeedback.rating))
        .join(Outfit)
        .where(and_(Outfit.user_id == current_user.id, UserFeedback.rating.isnot(None)))
    )
    rating_result = await db.execute(rating_query)
    avg_rating_raw = rating_result.scalar()
    average_rating = round(float(avg_rating_raw), 2) if avg_rating_raw else None

    wardrobe_stats = WardrobeStats(
        total_items=total_items,
        items_by_status=items_by_status,
        total_outfits=total_outfits,
        outfits_this_week=outfits_this_week,
        outfits_this_month=outfits_this_month,
        acceptance_rate=round(acceptance_rate, 1) if acceptance_rate else None,
        average_rating=average_rating,
        total_wears=total_wears,
    )

    # === Color Distribution ===
    color_query = (
        select(
            ClothingItem.primary_color,
            func.count(ClothingItem.id).label("count"),
        )
        .where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.primary_color.isnot(None),
                ClothingItem.status == ItemStatus.ready,
            )
        )
        .group_by(ClothingItem.primary_color)
        .order_by(func.count(ClothingItem.id).desc())
        .limit(10)
    )
    color_result = await db.execute(color_query)
    color_rows = color_result.all()

    ready_items = items_by_status["ready"]
    color_distribution = [
        ColorDistribution(
            color=row.primary_color,
            count=row.count,
            percentage=round(row.count / ready_items * 100, 1) if ready_items > 0 else 0,
        )
        for row in color_rows
    ]

    # === Type Distribution ===
    type_query = (
        select(
            ClothingItem.type,
            func.count(ClothingItem.id).label("count"),
        )
        .where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.status == ItemStatus.ready,
            )
        )
        .group_by(ClothingItem.type)
        .order_by(func.count(ClothingItem.id).desc())
    )
    type_result = await db.execute(type_query)
    type_rows = type_result.all()

    type_distribution = [
        TypeDistribution(
            type=row.type,
            count=row.count,
            percentage=round(row.count / ready_items * 100, 1) if ready_items > 0 else 0,
        )
        for row in type_rows
    ]

    # === Most/Least/Never Worn ===
    def wear_stats_query(order_desc: bool, limit: int, never_worn: bool = False):
        q = select(ClothingItem).where(
            and_(
                ClothingItem.user_id == current_user.id,
                ClothingItem.status == ItemStatus.ready,
            )
        )
        if never_worn:
            q = q.where(ClothingItem.wear_count == 0)
            q = q.order_by(ClothingItem.created_at.desc())
        elif order_desc:
            q = q.where(ClothingItem.wear_count > 0)
            q = q.order_by(ClothingItem.wear_count.desc())
        else:
            q = q.where(ClothingItem.wear_count > 0)
            q = q.order_by(ClothingItem.wear_count.asc())
        return q.limit(limit)

    most_worn_result = await db.execute(wear_stats_query(order_desc=True, limit=5))
    most_worn = [
        WearStats(
            id=item.id,
            name=item.name,
            type=item.type,
            primary_color=item.primary_color,
            thumbnail_path=item.thumbnail_path,
            wear_count=item.wear_count,
            last_worn_at=item.last_worn_at,
        )
        for item in most_worn_result.scalars().all()
    ]

    least_worn_result = await db.execute(wear_stats_query(order_desc=False, limit=5))
    least_worn = [
        WearStats(
            id=item.id,
            name=item.name,
            type=item.type,
            primary_color=item.primary_color,
            thumbnail_path=item.thumbnail_path,
            wear_count=item.wear_count,
            last_worn_at=item.last_worn_at,
        )
        for item in least_worn_result.scalars().all()
    ]

    never_worn_result = await db.execute(
        wear_stats_query(order_desc=False, limit=5, never_worn=True)
    )
    never_worn = [
        WearStats(
            id=item.id,
            name=item.name,
            type=item.type,
            primary_color=item.primary_color,
            thumbnail_path=item.thumbnail_path,
            wear_count=item.wear_count,
            last_worn_at=item.last_worn_at,
        )
        for item in never_worn_result.scalars().all()
    ]

    # === Acceptance Rate Trend (weekly) ===
    acceptance_trend = []
    weeks = min(days // 7, 12)  # Max 12 weeks

    for i in range(weeks):
        week_end = now - timedelta(days=i * 7)
        week_start = week_end - timedelta(days=7)

        week_query = select(
            func.count(Outfit.id).label("total"),
            func.sum(case((Outfit.status == OutfitStatus.accepted, 1), else_=0)).label("accepted"),
            func.sum(case((Outfit.status == OutfitStatus.rejected, 1), else_=0)).label("rejected"),
        ).where(
            and_(
                Outfit.user_id == current_user.id,
                Outfit.created_at >= week_start,
                Outfit.created_at < week_end,
            )
        )

        week_result = await db.execute(week_query)
        week_row = week_result.one()

        week_total = week_row.total or 0
        week_accepted = week_row.accepted or 0
        week_rejected = week_row.rejected or 0
        week_responded = week_accepted + week_rejected

        acceptance_trend.append(
            AcceptanceRateTrend(
                period=week_start.strftime("%b %d"),
                total=week_total,
                accepted=week_accepted,
                rejected=week_rejected,
                rate=round(week_accepted / week_responded * 100, 1) if week_responded > 0 else 0,
            )
        )

    acceptance_trend.reverse()  # Oldest first

    # === Generate Insights ===
    insights = []

    if total_items == 0:
        insights.append("Start by adding some items to your wardrobe!")
    else:
        # Wardrobe insights
        if len(never_worn) > 0:
            insights.append(
                f"You have {len(never_worn)} items you've never worn. Consider styling them!"
            )

        # Color insights
        if color_distribution:
            top_color = color_distribution[0].color
            if color_distribution[0].percentage > 40:
                insights.append(
                    f"Your wardrobe is heavy on {top_color} ({color_distribution[0].percentage}%). Consider adding variety!"
                )
            elif len(color_distribution) <= 3 and ready_items > 10:
                insights.append("Your wardrobe has limited color variety. Explore new colors!")

        # Type insights
        if type_distribution:
            insights.extend(
                composition_insights(
                    count_composition([(t.type, t.count) for t in type_distribution])
                )
            )

        # Outfit insights
        if acceptance_rate is not None:
            if acceptance_rate > 80:
                insights.append(f"Great taste! You accept {acceptance_rate:.0f}% of suggestions.")
            elif acceptance_rate < 50:
                insights.append(
                    "You reject many suggestions. Consider updating your style preferences."
                )

        if outfits_this_week == 0 and total_outfits > 0:
            insights.append(
                "You haven't generated any outfits this week. Try getting a suggestion!"
            )

    return AnalyticsResponse(
        wardrobe=wardrobe_stats,
        color_distribution=color_distribution,
        type_distribution=type_distribution,
        most_worn=most_worn,
        least_worn=least_worn,
        never_worn=never_worn,
        acceptance_trend=acceptance_trend,
        insights=insights,
    )
