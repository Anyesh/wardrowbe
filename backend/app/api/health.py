from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.services.ai_service import get_ai_service

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    """Report effective AI capabilities for external agents.

    `ai.*` — whether the internal AI capability is active. `false` means the backend
    is deferring that work to an external agent.
    `features.*` — whether the write-back endpoint for that capability exists and
    accepts agent-authored results. `false` until the endpoint lands.
    Public / no-auth: leaks no user data.
    """
    settings = get_settings()
    return {
        "ai": {
            "vision": settings.effective_ai_vision_enabled,
            "text": settings.effective_ai_text_enabled,
        },
        "features": {
            "external_tagging": True,
            "external_suggestions": False,
            "external_pairings": False,
        },
        "version": "1.0.0",
    }


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    checks = {
        "database": "unhealthy",
    }

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"

    overall = "healthy" if all(v == "healthy" for v in checks.values()) else "unhealthy"

    return {
        "status": overall,
        "checks": checks,
    }


@router.get("/health/features")
async def feature_check() -> dict[str, Any]:
    features = {}
    try:
        from app.services.background_removal import get_provider

        get_provider()
        features["background_removal"] = True
    except Exception:
        features["background_removal"] = False
    return features


@router.get("/health/ai")
async def ai_health_check() -> dict[str, Any]:
    if not get_settings().ai_enabled:
        return {"status": "disabled", "endpoints": []}

    ai_service = get_ai_service()
    raw = await ai_service.check_health()

    sanitized_endpoints = []
    for ep in raw.get("endpoints", []):
        sanitized_endpoints.append(
            {
                "name": ep.get("name"),
                "status": ep.get("status"),
            }
        )

    return {
        "status": raw.get("status", "unknown"),
        "endpoints": sanitized_endpoints,
    }
