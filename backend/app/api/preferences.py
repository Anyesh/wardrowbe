from typing import Annotated
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.preference import PreferenceResponse, PreferenceUpdate
from app.services.preference_service import PreferenceService
from app.utils.auth import get_current_user

router = APIRouter(prefix="/users/me/preferences", tags=["Preferences"])


def _build_preference_response(preferences) -> PreferenceResponse:
    default_style = {
        "casual": 50,
        "formal": 50,
        "sporty": 50,
        "minimalist": 50,
        "bold": 50,
    }
    return PreferenceResponse(
        color_favorites=preferences.color_favorites
        if preferences.color_favorites is not None
        else [],
        color_avoid=preferences.color_avoid if preferences.color_avoid is not None else [],
        style_profile=preferences.style_profile
        if preferences.style_profile is not None
        else default_style,
        default_occasion=preferences.default_occasion
        if preferences.default_occasion is not None
        else "casual",
        temperature_unit=preferences.temperature_unit
        if preferences.temperature_unit is not None
        else "celsius",
        temperature_sensitivity=preferences.temperature_sensitivity
        if preferences.temperature_sensitivity is not None
        else "normal",
        cold_threshold=preferences.cold_threshold if preferences.cold_threshold is not None else 10,
        hot_threshold=preferences.hot_threshold if preferences.hot_threshold is not None else 25,
        layering_preference=preferences.layering_preference
        if preferences.layering_preference is not None
        else "moderate",
        avoid_repeat_days=preferences.avoid_repeat_days
        if preferences.avoid_repeat_days is not None
        else 7,
        prefer_underused_items=preferences.prefer_underused_items
        if preferences.prefer_underused_items is not None
        else True,
        variety_level=preferences.variety_level
        if preferences.variety_level is not None
        else "moderate",
        ai_endpoints=preferences.ai_endpoints if preferences.ai_endpoints is not None else [],
    )


@router.get("", response_model=PreferenceResponse)
async def get_preferences(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PreferenceResponse:
    service = PreferenceService(db)
    preferences = await service.get_or_create_preferences(current_user.id)
    return _build_preference_response(preferences)


@router.patch("", response_model=PreferenceResponse)
async def update_preferences(
    data: PreferenceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PreferenceResponse:
    service = PreferenceService(db)
    preferences = await service.update_preferences(current_user.id, data)
    return _build_preference_response(preferences)


@router.post("/reset", response_model=PreferenceResponse)
async def reset_preferences(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PreferenceResponse:
    service = PreferenceService(db)
    preferences = await service.reset_preferences(current_user.id)
    return _build_preference_response(preferences)


@router.post("/excluded-items/{item_id}", response_model=dict)
async def add_excluded_item(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    service = PreferenceService(db)
    preferences = await service.add_excluded_item(current_user.id, item_id)
    return {"excluded_item_ids": [str(i) for i in preferences.excluded_item_ids]}


@router.delete("/excluded-items/{item_id}", response_model=dict)
async def remove_excluded_item(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    service = PreferenceService(db)
    preferences = await service.remove_excluded_item(current_user.id, item_id)
    return {"excluded_item_ids": [str(i) for i in preferences.excluded_item_ids]}


@router.post("/test-ai-endpoint", response_model=dict)
async def test_ai_endpoint(
    data: dict,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    url = data.get("url", "").rstrip("/")
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL is required",
        )

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only HTTP and HTTPS URLs are allowed",
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Try Ollama-style health check
            health_url = url.replace("/v1", "/api/tags")
            response = await client.get(health_url)

            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                model_names = [m.get("name", "") for m in models]

                # Categorize models
                vision_models = [
                    m
                    for m in model_names
                    if any(v in m.lower() for v in ["moondream", "llava", "bakllava", "vision"])
                ]
                text_models = [m for m in model_names if m not in vision_models]

                return {
                    "status": "connected",
                    "available_models": model_names,
                    "vision_models": vision_models,
                    "text_models": text_models,
                }
            else:
                return {
                    "status": "error",
                    "error": f"HTTP {response.status_code}",
                }
    except httpx.ConnectError:
        return {
            "status": "error",
            "error": "Connection refused - is the server running?",
        }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "error": "Connection timed out",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }
