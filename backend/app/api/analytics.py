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


INSIGHT_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "no_items": "Start by adding some items to your wardrobe!",
        "never_worn": "You have {n} items you've never worn. Consider styling them!",
        "heavy_color": "Your wardrobe is heavy on {color} ({pct}%). Consider adding variety!",
        "limited_colors": "Your wardrobe has limited color variety. Explore new colors!",
        "more_tops": "You have many more tops than bottoms. Consider adding pants or skirts!",
        "more_bottoms": "You have more bottoms than tops. Consider adding some shirts!",
        "great_taste": "Great taste! You accept {pct}% of suggestions.",
        "many_rejects": "You reject many suggestions. Consider updating your style preferences.",
        "no_outfits_week": "You haven't generated any outfits this week. Try getting a suggestion!",
    },
    "zh": {
        "no_items": "先往衣橱里添加几件衣物吧！",
        "never_worn": "你有 {n} 件从未穿过的衣物，试试搭配它们！",
        "heavy_color": "你的衣橱以 {color} 为主（{pct}%），建议增加一些颜色变化！",
        "limited_colors": "你的衣橱颜色种类较少，试试探索新的颜色！",
        "more_tops": "你的上衣远多于下装，考虑添置裤子或裙子！",
        "more_bottoms": "你的下装多于上衣，考虑添置几件衬衫！",
        "great_taste": "品味不错！你接受了 {pct}% 的穿搭建议。",
        "many_rejects": "你拒绝了很多建议，考虑更新你的风格偏好。",
        "no_outfits_week": "本周还没有生成穿搭，快来获取一个推荐吧！",
    },
}


def _t(key: str, lang: str, **kwargs: object) -> str:
    """Translate an insight message."""
    template = INSIGHT_TRANSLATIONS.get(lang, INSIGHT_TRANSLATIONS["en"]).get(key, key)
    return template.format(**kwargs) if kwargs else template


@router.get("", response_model=AnalyticsResponse)
async def get_analytics(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    days: int = Query(30, ge=7, le=365, description="Number of days for trends"),
    lang: str = Query("en", description="Language for insight messages (en/zh)"),
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
        insights.append(_t("no_items", lang))
    else:
        # Wardrobe insights
        if len(never_worn) > 0:
            insights.append(
                _t("never_worn", lang, n=len(never_worn))
            )

        # Color insights
        if color_distribution:
            top_color = color_distribution[0].color
            if color_distribution[0].percentage > 40:
                insights.append(
                    _t("heavy_color", lang, color=top_color, pct=color_distribution[0].percentage)
                )
            elif len(color_distribution) <= 3 and ready_items > 10:
                insights.append(_t("limited_colors", lang))

        # Type insights
        if type_distribution:
            tops = sum(
                t.count
                for t in type_distribution
                if t.type in ["shirt", "blouse", "t-shirt", "top"]
            )
            bottoms = sum(
                t.count
                for t in type_distribution
                if t.type in ["pants", "jeans", "skirt", "shorts"]
            )
            if tops > 0 and bottoms > 0:
                ratio = tops / bottoms
                if ratio > 3:
                    insights.append(
                        _t("more_tops", lang)
                    )
                elif ratio < 0.5:
                    insights.append(_t("more_bottoms", lang))

        # Outfit insights
        if acceptance_rate is not None:
            if acceptance_rate > 80:
                insights.append(_t("great_taste", lang, pct=f"{acceptance_rate:.0f}"))
            elif acceptance_rate < 50:
                insights.append(
                    _t("many_rejects", lang)
                )

        if outfits_this_week == 0 and total_outfits > 0:
            insights.append(
                _t("no_outfits_week", lang)
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
