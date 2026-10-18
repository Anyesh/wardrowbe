from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image

from app.api import ai_status
from app.config import get_settings


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (400, 600), (90, 90, 90)).save(buffer, format="JPEG")
    return buffer.getvalue()


class TestAIStatus:
    def test_summarize_reports_a_missing_model(self):
        raw = {
            "endpoints": [
                {
                    "status": "healthy",
                    "vision_model": "Ornith-1.5-9B",
                    "text_model": "hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q5_K_M",
                    "available_models": ["hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q5_K_M"],
                }
            ]
        }
        result = ai_status.summarize(raw)
        assert result.status == "model_missing"
        assert result.missing_models == ["Ornith-1.5-9B"]

    def test_summarize_online_and_offline(self):
        online = {
            "endpoints": [
                {
                    "status": "healthy",
                    "vision_model": "gemma3",
                    "text_model": "gemma3",
                    "available_models": ["gemma3:latest"],
                }
            ]
        }
        assert ai_status.summarize(online).status == "online"
        offline = {"endpoints": [{"status": "unhealthy", "vision_model": "gemma3"}]}
        assert ai_status.summarize(offline).status == "offline"

    @pytest.mark.asyncio
    async def test_endpoint_needs_sign_in_and_answers(self, client: AsyncClient, auth_headers):
        assert (await client.get("/api/v1/ai/status")).status_code == 401
        ai_status._cache.clear()
        health = {
            "status": "unhealthy",
            "endpoints": [{"status": "unhealthy", "vision_model": "m", "text_model": "m"}],
        }
        check = AsyncMock(return_value=health)
        with (
            patch.object(type(get_settings()), "ai_enabled", property(lambda self: True)),
            patch("app.services.ai_service.AIService.check_health", check),
        ):
            response = await client.get("/api/v1/ai/status", headers=auth_headers)
        ai_status._cache.clear()
        assert response.status_code == 200
        assert response.json()["status"] == "offline"
        check.assert_awaited_once()

    def test_a_rotation_is_there_when_any_of_its_models_is(self):
        health = {
            "endpoints": [
                {
                    "status": "healthy",
                    "vision_model": "llava:7b, gemma3",
                    "text_model": "gemma3",
                    "available_models": ["gemma3:latest"],
                }
            ]
        }
        assert ai_status.summarize(health).status == "online"

    def test_a_switched_off_capability_cannot_be_missing(self):
        health = {
            "endpoints": [
                {
                    "status": "healthy",
                    "vision_model": "not-installed",
                    "text_model": "gemma3",
                    "available_models": ["gemma3:latest"],
                }
            ]
        }
        settings = type(get_settings())
        with (
            patch.object(settings, "effective_ai_vision_enabled", property(lambda self: False)),
            patch.object(settings, "effective_ai_text_enabled", property(lambda self: True)),
        ):
            result = ai_status.summarize(health)
        assert result.status == "online"
        assert result.missing_models == []


class TestLoadedModels:
    def _online(self):
        return ai_status.AIStatusResponse(
            status="online",
            vision_model="qwen2.5vl:7b",
            text_model="qwen2.5vl:7b",
            url="http://ollama:11434/v1",
        )

    @pytest.mark.asyncio
    async def test_reports_whether_the_model_is_in_memory(self):
        with patch("app.api.ai_status.loaded_models", AsyncMock(return_value=["qwen2.5vl:7b"])):
            assert (await ai_status.with_loaded_models(self._online())).model_loaded is True
        with patch("app.api.ai_status.loaded_models", AsyncMock(return_value=[])):
            result = await ai_status.with_loaded_models(self._online())
        # Reachable with the model installed but not loaded: still online, loads on first use.
        assert result.status == "online"
        assert result.model_loaded is False

    @pytest.mark.asyncio
    async def test_a_server_without_api_ps_leaves_it_unknown(self):
        with patch("app.api.ai_status.loaded_models", AsyncMock(return_value=None)):
            assert (await ai_status.with_loaded_models(self._online())).model_loaded is None

    @pytest.mark.asyncio
    async def test_an_unreachable_server_is_unknown_not_an_error(self):
        assert await ai_status.loaded_models("http://127.0.0.1:9/v1") is None
