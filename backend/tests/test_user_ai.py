"""Features that call the model use the endpoints and models the user picked in Settings."""

import pytest

from app.models.preference import UserPreference
from app.services.ai_service import get_ai_service
from app.services.user_ai import ai_service_for


class TestUserModels:
    @pytest.mark.asyncio
    async def test_the_users_own_endpoint_comes_first(self, db_session, test_user):
        db_session.add(
            UserPreference(
                user_id=test_user.id,
                ai_endpoints=[
                    {
                        "name": "mine",
                        "url": "http://ollama.local:11434/v1",
                        "vision_model": "qwen2.5vl:7b",
                        "text_model": "qwen3:8b",
                        "enabled": True,
                    },
                    {"name": "off", "url": "http://off/v1", "enabled": False},
                ],
            )
        )
        await db_session.commit()

        ai = await ai_service_for(db_session, test_user.id)
        first = ai._endpoints[0]
        assert (first.url, first.vision_model, first.text_model) == (
            "http://ollama.local:11434/v1",
            "qwen2.5vl:7b",
            "qwen3:8b",
        )
        assert all(ep.name != "off" for ep in ai._endpoints)

    @pytest.mark.asyncio
    async def test_without_own_endpoints_the_server_default_is_used(self, db_session, test_user):
        assert await ai_service_for(db_session, test_user.id) is get_ai_service()
