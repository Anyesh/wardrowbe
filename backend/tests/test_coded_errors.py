from io import BytesIO
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import coded_http_exception_handler
from app.models.notification import NotificationSettings
from app.services.image_service import ImageService, ImageTooLargeError
from app.services.notification_service import NotificationService
from app.services.recommendation_service import RecommendationInputError
from app.utils.errors import CodedHTTPException


def _app_raising(exc: Exception) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(CodedHTTPException, coded_http_exception_handler)

    @app.get("/boom")
    async def boom():
        raise exc

    return app


async def _get(exc: Exception):
    transport = ASGITransport(app=_app_raising(exc))
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.get("/boom")


class TestCodedHandler:
    @pytest.mark.asyncio
    async def test_body_without_params(self):
        response = await _get(CodedHTTPException(503, "AI_DISABLED", "AI is off"))

        assert response.status_code == 503
        assert response.json() == {"detail": "AI is off", "error_code": "AI_DISABLED"}

    @pytest.mark.asyncio
    async def test_body_with_params_keeps_detail_a_string(self):
        response = await _get(
            CodedHTTPException(413, "UPLOAD_TOO_LARGE", "Too big", {"limit_mb": 50})
        )

        body = response.json()
        assert response.status_code == 413
        assert body["detail"] == "Too big"
        assert body["error_code"] == "UPLOAD_TOO_LARGE"
        assert body["error_params"] == {"limit_mb": 50}

    @pytest.mark.asyncio
    async def test_headers_are_kept(self):
        response = await _get(
            CodedHTTPException(429, "RATE_LIMITED", "Slow down", headers={"Retry-After": "30"})
        )

        assert response.status_code == 429
        assert response.headers["retry-after"] == "30"

    def test_recommendation_input_error_stays_a_value_error(self):
        error = RecommendationInputError("LOCATION_NOT_SET", "no location")

        assert isinstance(error, ValueError)
        assert error.error_code == "LOCATION_NOT_SET"
        assert str(error) == "no location"


class TestCodedEndpoints:
    @pytest.mark.asyncio
    async def test_rate_limited_response_carries_code(
        self, client: AsyncClient, test_user, auth_headers
    ):
        for _ in range(10):
            await client.post(
                "/api/v1/outfits/suggest", json={"occasion": "casual"}, headers=auth_headers
            )
        response = await client.post(
            "/api/v1/outfits/suggest", json={"occasion": "casual"}, headers=auth_headers
        )

        assert response.status_code == 429
        assert response.json() == {
            "detail": "Too many requests. Please try again later.",
            "error_code": "RATE_LIMITED",
        }

    @pytest.mark.asyncio
    async def test_weather_without_location_carries_code(
        self, client: AsyncClient, test_user, auth_headers
    ):
        response = await client.get("/api/v1/weather/current", headers=auth_headers)

        assert response.status_code == 400
        body = response.json()
        assert body["error_code"] == "LOCATION_NOT_SET"
        assert body["detail"].startswith("Location not set")
        assert "error_params" not in body

    @pytest.mark.asyncio
    async def test_suggest_without_location_carries_service_code(
        self, client: AsyncClient, test_user, auth_headers
    ):
        response = await client.post(
            "/api/v1/outfits/suggest", json={"occasion": "casual"}, headers=auth_headers
        )

        assert response.status_code == 400
        body = response.json()
        assert body["error_code"] == "LOCATION_NOT_SET"
        assert body["detail"] == "User location not set. Please set location in settings."


class TestEndpointErrorCodes:
    @pytest.mark.asyncio
    async def test_too_many_pixels_upload(
        self, client: AsyncClient, test_user, auth_headers, monkeypatch
    ):
        monkeypatch.setattr(
            ImageService,
            "process_and_store",
            AsyncMock(side_effect=ImageTooLargeError(48_000_000, 40_000_000)),
        )
        buf = BytesIO()
        Image.new("RGB", (50, 50)).save(buf, format="JPEG")

        response = await client.post(
            "/api/v1/items",
            files={"image": ("shirt.jpg", buf.getvalue(), "image/jpeg")},
            headers=auth_headers,
        )

        body = response.json()
        assert response.status_code == 400
        assert body["error_code"] == "IMAGE_TOO_MANY_PIXELS"
        assert body["error_params"] == {"megapixels": 48.0, "limit": 40.0}

    @pytest.mark.asyncio
    async def test_notification_test_failure_carries_reason(
        self, client: AsyncClient, db_session, test_user, auth_headers, monkeypatch
    ):
        setting = NotificationSettings(
            user_id=test_user.id,
            channel="ntfy",
            priority=1,
            config={"server": "https://ntfy.example.com", "topic": "outfits"},
        )
        db_session.add(setting)
        await db_session.commit()
        monkeypatch.setattr(
            NotificationService,
            "test_setting",
            AsyncMock(return_value=(False, "HTTP 502 from ntfy")),
        )

        response = await client.post(
            f"/api/v1/notifications/settings/{setting.id}/test", headers=auth_headers
        )

        body = response.json()
        assert response.status_code == 400
        assert body["error_code"] == "NOTIFICATION_TEST_FAILED"
        assert body["error_params"] == {"reason": "HTTP 502 from ntfy"}

    @pytest.mark.asyncio
    async def test_ai_endpoint_refused_connection(
        self, client: AsyncClient, test_user, auth_headers
    ):
        with patch.object(
            httpx.AsyncClient, "get", AsyncMock(side_effect=httpx.ConnectError("refused"))
        ):
            response = await client.post(
                "/api/v1/users/me/preferences/test-ai-endpoint",
                json={"url": "http://localhost:11434/v1"},
                headers=auth_headers,
            )

        body = response.json()
        assert body["status"] == "error"
        assert body["error_code"] == "AI_ENDPOINT_UNREACHABLE"
