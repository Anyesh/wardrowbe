"""Learning system API endpoints."""

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.database import DbSession
from app.models.learning import UserLearningProfile
from app.models.user import User
from app.services.learning_service import LearningService
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/learning", tags=["Learning"])


# Response schemas
class LearnedColorScore(BaseModel):
    """Color preference score."""

    color: str
    score: float
    interpretation: str  # "strongly liked", "liked", "neutral", "disliked", "strongly disliked"


class LearnedStyleScore(BaseModel):
    """Style preference score."""

    style: str
    score: float


class OccasionPattern(BaseModel):
    """Learned occasion pattern."""

    occasion: str
    preferred_colors: list[str]
    success_rate: float


class WeatherPreference(BaseModel):
    """Learned weather preference."""

    weather_type: str  # cold, cool, mild, hot
    preferred_layers: float
    success_rate: float


class LearningProfileResponse(BaseModel):
    """User's learning profile."""

    has_learning_data: bool
    feedback_count: int
    outfits_rated: int
    overall_acceptance_rate: float | None = None
    average_rating: float | None = None
    average_comfort_rating: float | None = None
    average_style_rating: float | None = None
    color_preferences: list[LearnedColorScore]
    style_preferences: list[LearnedStyleScore]
    occasion_patterns: list[OccasionPattern]
    weather_preferences: list[WeatherPreference]
    last_computed_at: datetime | None = None


class ItemPairResponse(BaseModel):
    """Item pair that works well together."""

    item1: dict
    item2: dict
    compatibility_score: float
    times_paired: int
    times_accepted: int


class InsightResponse(BaseModel):
    """Style insight."""

    id: UUID
    category: str
    insight_type: str
    title: str
    description: str
    confidence: float
    created_at: datetime


class LearningInsightsResponse(BaseModel):
    """Learning insights response."""

    profile: LearningProfileResponse
    best_pairs: list[ItemPairResponse]
    insights: list[InsightResponse]
    preference_suggestions: dict


def _interpret_score(score: float) -> str:
    """Convert numeric score to human-readable interpretation."""
    if score >= 0.5:
        return "strongly liked"
    elif score >= 0.2:
        return "liked"
    elif score >= -0.2:
        return "neutral"
    elif score >= -0.5:
        return "disliked"
    else:
        return "strongly disliked"


def _profile_response(profile: UserLearningProfile | None) -> LearningProfileResponse:
    if profile is None:
        return LearningProfileResponse(
            has_learning_data=False,
            feedback_count=0,
            outfits_rated=0,
            color_preferences=[],
            style_preferences=[],
            occasion_patterns=[],
            weather_preferences=[],
        )

    has_data = profile.last_computed_at is not None
    color_scores = profile.color_scores if has_data else {}
    style_scores = profile.style_scores if has_data else {}
    occasion_patterns = profile.occasion_patterns if has_data else {}
    weather_preferences = profile.weather_preferences if has_data else {}

    return LearningProfileResponse(
        has_learning_data=has_data,
        feedback_count=profile.feedback_count,
        outfits_rated=profile.outfits_rated,
        overall_acceptance_rate=float(profile.overall_acceptance_rate)
        if profile.overall_acceptance_rate
        else None,
        average_rating=float(profile.average_overall_rating)
        if profile.average_overall_rating
        else None,
        average_comfort_rating=float(profile.average_comfort_rating)
        if profile.average_comfort_rating
        else None,
        average_style_rating=float(profile.average_style_rating)
        if profile.average_style_rating
        else None,
        color_preferences=[
            LearnedColorScore(color=color, score=score, interpretation=_interpret_score(score))
            for color, score in sorted(color_scores.items(), key=lambda x: x[1], reverse=True)
        ],
        style_preferences=[
            LearnedStyleScore(style=style, score=score)
            for style, score in sorted(style_scores.items(), key=lambda x: x[1], reverse=True)
        ],
        occasion_patterns=[
            OccasionPattern(
                occasion=occasion,
                preferred_colors=data.get("preferred_colors", []),
                success_rate=data.get("success_rate", 0),
            )
            for occasion, data in occasion_patterns.items()
        ],
        weather_preferences=[
            WeatherPreference(
                weather_type=weather,
                preferred_layers=data.get("preferred_layers", 0),
                success_rate=data.get("success_rate", 0),
            )
            for weather, data in weather_preferences.items()
        ],
        last_computed_at=profile.last_computed_at,
    )


@router.get("", response_model=LearningInsightsResponse)
async def get_learning_insights(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> LearningInsightsResponse:
    """
    Get comprehensive learning insights for the current user.

    Returns the user's learning profile, best item pairs, active insights,
    and suggested preference updates based on feedback history.
    """
    learning_service = LearningService(db)

    # Get or compute learning profile
    result = await db.execute(
        select(UserLearningProfile).where(UserLearningProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    profile_response = _profile_response(profile)

    # Get best item pairs
    best_pairs_data = await learning_service.get_best_item_pairs(current_user.id, limit=10)
    best_pairs = [
        ItemPairResponse(
            item1=pair["item1"],
            item2=pair["item2"],
            compatibility_score=pair["compatibility_score"],
            times_paired=pair["times_paired"],
            times_accepted=pair["times_accepted"],
        )
        for pair in best_pairs_data
    ]

    # Get active insights
    active_insights = await learning_service.get_active_insights(current_user.id)
    insights = [
        InsightResponse(
            id=insight.id,
            category=insight.category,
            insight_type=insight.insight_type,
            title=insight.title,
            description=insight.description,
            confidence=float(insight.confidence),
            created_at=insight.created_at,
        )
        for insight in active_insights
    ]

    # Get preference suggestions
    suggestions = await learning_service.apply_learning_to_preferences(current_user.id)

    return LearningInsightsResponse(
        profile=profile_response,
        best_pairs=best_pairs,
        insights=insights,
        preference_suggestions=suggestions,
    )


@router.post("/recompute", response_model=LearningProfileResponse)
async def recompute_learning_profile(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> LearningProfileResponse:
    """
    Force recomputation of the learning profile.

    This analyzes all historical feedback to update learned preferences.
    Usually happens automatically, but can be triggered manually.
    """
    learning_service = LearningService(db)

    profile = await learning_service.recompute_learning_profile(current_user.id)

    return _profile_response(profile)


@router.post("/generate-insights", response_model=list[InsightResponse])
async def generate_insights(
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[InsightResponse]:
    """
    Generate new style insights based on learning data.

    Creates human-readable insights about the user's style patterns.
    """
    learning_service = LearningService(db)

    insights = await learning_service.generate_insights(current_user.id)

    return [
        InsightResponse(
            id=insight.id,
            category=insight.category,
            insight_type=insight.insight_type,
            title=insight.title,
            description=insight.description,
            confidence=float(insight.confidence),
            created_at=insight.created_at,
        )
        for insight in insights
    ]


@router.post("/insights/{insight_id}/acknowledge")
async def acknowledge_insight(
    insight_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Mark an insight as acknowledged/dismissed."""
    learning_service = LearningService(db)

    success = await learning_service.acknowledge_insight(current_user.id, insight_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insight not found",
        )

    return {"acknowledged": True}


@router.get("/item-pairs/{item_id}", response_model=list[dict])
async def get_item_pair_suggestions(
    item_id: UUID,
    db: DbSession,
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(5, ge=1, le=20),
) -> list[dict]:
    """
    Get items that pair well with a specific item.

    Based on historical feedback, returns items that have been
    positively received when combined with the given item.
    """
    learning_service = LearningService(db)

    pairs = await learning_service.get_item_pair_suggestions(current_user.id, item_id, limit=limit)

    return [
        {
            "item": {
                "id": str(item.id),
                "type": item.type,
                "name": item.name,
                "primary_color": item.primary_color,
                "thumbnail_path": item.thumbnail_path,
            },
            "compatibility_score": score,
        }
        for item, score in pairs
    ]
