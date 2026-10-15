from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image

from app.api import ai_status


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
        with patch(
            "app.services.ai_service.AIService.check_health", AsyncMock(return_value=health)
        ):
            response = await client.get("/api/v1/ai/status", headers=auth_headers)
        ai_status._cache.clear()
        assert response.status_code == 200
        assert response.json()["status"] in ("offline", "disabled")
