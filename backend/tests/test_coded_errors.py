import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import coded_http_exception_handler
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
