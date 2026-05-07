from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.onboarding import (
    OnboardingStateResponse,
    StyleQuizDefinitionResponse,
    StyleQuizSubmitRequest,
    StyleQuizSubmitResponse,
)
from app.schemas.preference import PreferenceResponse
from app.services.onboarding_service import OnboardingService
from app.utils.auth import get_current_user

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


def _preference_response(preferences) -> PreferenceResponse:
    default_style = {
        "casual": 50,
        "formal": 50,
        "sporty": 50,
        "minimalist": 50,
        "bold": 50,
    }

    return PreferenceResponse(
        color_favorites=preferences.color_favorites or [],
        color_avoid=preferences.color_avoid or [],
        style_profile=preferences.style_profile or default_style,
        default_occasion=preferences.default_occasion or "casual",
        temperature_unit=preferences.temperature_unit or "celsius",
        temperature_sensitivity=preferences.temperature_sensitivity or "normal",
        cold_threshold=preferences.cold_threshold if preferences.cold_threshold is not None else 10,
        hot_threshold=preferences.hot_threshold if preferences.hot_threshold is not None else 25,
        layering_preference=preferences.layering_preference or "moderate",
        avoid_repeat_days=preferences.avoid_repeat_days if preferences.avoid_repeat_days is not None else 7,
        prefer_underused_items=(
            preferences.prefer_underused_items
            if preferences.prefer_underused_items is not None
            else True
        ),
        variety_level=preferences.variety_level or "moderate",
        ai_endpoints=preferences.ai_endpoints or [],
    )


@router.get("/state", response_model=OnboardingStateResponse)
async def get_onboarding_state(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OnboardingStateResponse:
    service = OnboardingService(db)
    payload = await service.get_state_payload(current_user.id)
    await db.commit()
    return OnboardingStateResponse(**payload)


@router.get("/steps/style-quiz", response_model=StyleQuizDefinitionResponse)
async def get_style_quiz_definition(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StyleQuizDefinitionResponse:
    service = OnboardingService(db)
    await service.ensure_default_state(current_user.id)
    await db.commit()
    return service.get_style_quiz_definition()


@router.post("/steps/style-quiz/submit", response_model=StyleQuizSubmitResponse)
async def submit_style_quiz(
    payload: StyleQuizSubmitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StyleQuizSubmitResponse:
    service = OnboardingService(db)
    updated_preferences, style_insight = await service.submit_style_quiz(
        current_user,
        payload.answers,
    )
    await db.commit()
    return StyleQuizSubmitResponse(
        updated_preferences=_preference_response(updated_preferences),
        style_insight=style_insight,
        next_step=None,
    )


@router.post("/steps/style-quiz/reopen")
async def reopen_style_quiz(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    service = OnboardingService(db)
    await service.reopen_style_quiz(current_user.id)
    current_user.onboarding_completed = False
    await db.commit()
    return {"ok": True}
