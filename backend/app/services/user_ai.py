"""The AI service as the user configured it.

Settings > AI lets each user pick their own endpoints and models (stored in
UserPreference.ai_endpoints). Tagging, outfit suggestions and pairings already honour them;
every feature that talks to the model should, so it goes through here. The server's
AI_BASE_URL / AI_*_MODEL stay as the fallback after the user's endpoints, as in AIService.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preference import UserPreference
from app.services.ai_service import AIService, get_ai_service


async def user_ai_endpoints(db: AsyncSession, user_id: UUID) -> list[dict]:
    endpoints = await db.scalar(
        select(UserPreference.ai_endpoints).where(UserPreference.user_id == user_id)
    )
    return [ep for ep in endpoints or [] if ep.get("enabled", True)]


async def ai_service_for(db: AsyncSession, user_id: UUID) -> AIService:
    """AIService using the user's own endpoints first; the shared default when they set none.

    Raises AIDisabledError when internal AI is off, like get_ai_service.
    """
    endpoints = await user_ai_endpoints(db, user_id)
    if not endpoints:
        return get_ai_service()
    return AIService(endpoints=endpoints)
