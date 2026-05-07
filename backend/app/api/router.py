"""Main API router."""

from fastapi import APIRouter

from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.families import router as families_router
from app.api.health import router as health_router
from app.api.images import router as images_router
from app.api.items import router as items_router
from app.api.learning import router as learning_router
from app.api.notifications import router as notifications_router
from app.api.onboarding import router as onboarding_router
from app.api.outfits import router as outfits_router
from app.api.pairings import router as pairings_router
from app.api.preferences import router as preferences_router
from app.api.users import router as users_router
from app.api.weather import router as weather_router

api_router = APIRouter()

# Include sub-routers
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(items_router)
api_router.include_router(images_router)
api_router.include_router(preferences_router)
api_router.include_router(onboarding_router)
api_router.include_router(families_router)
api_router.include_router(weather_router)
api_router.include_router(outfits_router)
api_router.include_router(pairings_router)
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
api_router.include_router(analytics_router)
api_router.include_router(learning_router)
