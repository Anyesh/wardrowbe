from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.ai_service import get_ai_service

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


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
