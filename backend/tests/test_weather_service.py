import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import redis.asyncio as aioredis

from app.services.weather_service import (
    CACHE_PREFIX,
    WMO_CODES,
    WeatherData,
    WeatherService,
    WeatherServiceError,
)

FAKE_REQUEST = httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code, json=json_data, request=FAKE_REQUEST)


SAMPLE_API_RESPONSE = {
    "current": {
        "temperature_2m": 22.5,
        "apparent_temperature": 21.0,
        "relative_humidity_2m": 65,
        "precipitation": 0.0,
        "weather_code": 2,
        "wind_speed_10m": 12.3,
        "is_day": 1,
        "uv_index": 5.0,
    },
    "hourly": {
        "precipitation_probability": [30],
    },
}

SAMPLE_FORECAST_RESPONSE = {
    "daily": {
        "time": ["2026-02-28", "2026-03-01"],
        "temperature_2m_max": [18.0, 22.0],
        "temperature_2m_min": [8.0, 12.0],
        "precipitation_probability_max": [10, 40],
        "weather_code": [0, 61],
    },
}


def _make_weather_data(**overrides) -> WeatherData:
    defaults = {
        "temperature": 22.5,
        "feels_like": 21.0,
        "humidity": 65,
        "precipitation_chance": 30,
        "precipitation_mm": 0.0,
        "wind_speed": 12.3,
        "condition": "partly cloudy",
        "condition_code": 2,
        "is_day": True,
        "uv_index": 5.0,
        "timestamp": datetime(2026, 2, 28, 12, 0, 0),
    }
    defaults.update(overrides)
    return WeatherData(**defaults)


@pytest.fixture
def weather_service():
    return WeatherService()


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    with patch("app.services.weather_service.get_redis", return_value=redis):
        yield redis


class TestCacheKey:
    def test_rounds_coordinates(self):
        assert WeatherService._cache_key(40.7142, -74.0059) == f"{CACHE_PREFIX}40.71,-74.01"

    def test_exact_coordinates(self):
        assert WeatherService._cache_key(50.0, 10.0) == f"{CACHE_PREFIX}50.0,10.0"


class TestCacheGet:
    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self, weather_service, mock_redis):
        mock_redis.get.return_value = None
        result = await weather_service._cache_get(40.71, -74.01)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_weather_data_on_hit(self, weather_service, mock_redis):
        cached = _make_weather_data()
        mock_redis.get.return_value = json.dumps(cached.to_dict())

        result = await weather_service._cache_get(40.71, -74.01)

        assert result is not None
        assert result.temperature == 22.5
        assert result.condition == "partly cloudy"

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self, weather_service):
        with patch(
            "app.services.weather_service.get_redis",
            side_effect=aioredis.RedisError("connection refused"),
        ):
            result = await weather_service._cache_get(40.71, -74.01)
        assert result is None


class TestCacheSet:
    @pytest.mark.asyncio
    async def test_stores_weather_in_redis(self, weather_service, mock_redis):
        data = _make_weather_data()
        await weather_service._cache_set(40.71, -74.01, data)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == f"{CACHE_PREFIX}40.71,-74.01"
        assert call_args[1]["ex"] == 3600

        stored = json.loads(call_args[0][1])
        assert stored["temperature"] == 22.5

    @pytest.mark.asyncio
    async def test_silently_handles_redis_error(self, weather_service):
        with patch(
            "app.services.weather_service.get_redis",
            side_effect=aioredis.RedisError("connection refused"),
        ):
            await weather_service._cache_set(40.71, -74.01, _make_weather_data())


class TestValidateCoordinates:
    def test_valid_coordinates(self, weather_service):
        weather_service._validate_coordinates(40.71, -74.01)

    def test_invalid_latitude(self, weather_service):
        with pytest.raises(ValueError, match="Invalid latitude"):
            weather_service._validate_coordinates(91.0, 0.0)

    def test_invalid_longitude(self, weather_service):
        with pytest.raises(ValueError, match="Invalid longitude"):
            weather_service._validate_coordinates(0.0, 181.0)

    def test_boundary_values(self, weather_service):
        weather_service._validate_coordinates(90.0, 180.0)
        weather_service._validate_coordinates(-90.0, -180.0)


class TestInterpretWeatherCode:
    def test_known_code(self, weather_service):
        assert weather_service._interpret_weather_code(0) == "sunny"
        assert weather_service._interpret_weather_code(95) == "thunderstorm"

    def test_unknown_code(self, weather_service):
        assert weather_service._interpret_weather_code(999) == "unknown"

    def test_all_codes_mapped(self, weather_service):
        for code, condition in WMO_CODES.items():
            assert weather_service._interpret_weather_code(code) == condition


class TestGetCurrentWeather:
    @pytest.mark.asyncio
    async def test_fetches_from_api(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_API_RESPONSE)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_current_weather(40.71, -74.01)

        assert result.temperature == 22.5
        assert result.feels_like == 21.0
        assert result.humidity == 65
        assert result.precipitation_chance == 30
        assert result.condition == "partly cloudy"
        assert result.condition_code == 2
        assert result.is_day is True

    @pytest.mark.asyncio
    async def test_returns_cached_data(self, weather_service, mock_redis):
        cached = _make_weather_data(temperature=15.0)
        mock_redis.get.return_value = json.dumps(cached.to_dict())

        result = await weather_service.get_current_weather(40.71, -74.01)

        assert result.temperature == 15.0

    @pytest.mark.asyncio
    async def test_skips_cache_when_disabled(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_API_RESPONSE)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_current_weather(40.71, -74.01, use_cache=False)

        mock_redis.get.assert_not_called()
        assert result.temperature == 22.5

    @pytest.mark.asyncio
    async def test_caches_api_response(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_API_RESPONSE)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            await weather_service.get_current_weather(40.71, -74.01)

        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_invalid_coordinates(self, weather_service):
        with pytest.raises(ValueError):
            await weather_service.get_current_weather(100.0, 0.0)

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self, weather_service, mock_redis):
        with patch(
            "httpx.AsyncClient.get",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            with pytest.raises(WeatherServiceError, match="Failed to fetch weather"):
                await weather_service.get_current_weather(40.71, -74.01)

    @pytest.mark.asyncio
    async def test_handles_missing_hourly_precipitation(self, weather_service, mock_redis):
        response_data = {
            "current": SAMPLE_API_RESPONSE["current"],
            "hourly": {"precipitation_probability": []},
        }
        mock_response = _mock_response(json_data=response_data)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_current_weather(40.71, -74.01)

        assert result.precipitation_chance == 0


class TestGetDailyForecast:
    @pytest.mark.asyncio
    async def test_returns_forecast_days(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_FORECAST_RESPONSE)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_daily_forecast(40.71, -74.01, days=2)

        assert len(result) == 2
        assert result[0].date == "2026-02-28"
        assert result[0].temp_max == 18.0
        assert result[0].condition == "sunny"
        assert result[1].condition == "light rain"

    @pytest.mark.asyncio
    async def test_caps_days_at_16(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_FORECAST_RESPONSE)
        with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
            await weather_service.get_daily_forecast(40.71, -74.01, days=30)

        call_params = mock_get.call_args[1]["params"]
        assert call_params["forecast_days"] == 16

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self, weather_service, mock_redis):
        with patch(
            "httpx.AsyncClient.get",
            side_effect=httpx.ConnectError("timeout"),
        ):
            with pytest.raises(WeatherServiceError, match="Failed to fetch forecast"):
                await weather_service.get_daily_forecast(40.71, -74.01)


class TestGetTomorrowWeather:
    @pytest.mark.asyncio
    async def test_returns_tomorrow_forecast(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_FORECAST_RESPONSE)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_tomorrow_weather(40.71, -74.01)

        assert result.temperature == 17.0  # avg of 12.0 and 22.0
        assert result.feels_like == 22.0  # max temp
        assert result.condition == "light rain"
        assert result.precipitation_chance == 40
        assert result.is_day is True

    @pytest.mark.asyncio
    async def test_falls_back_to_current_weather(self, weather_service, mock_redis):
        empty_forecast = {"daily": {"time": []}}
        mock_forecast_response = _mock_response(json_data=empty_forecast)
        mock_current_response = _mock_response(json_data=SAMPLE_API_RESPONSE)

        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_forecast_response
            return mock_current_response

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            result = await weather_service.get_tomorrow_weather(40.71, -74.01)

        assert result.temperature == 22.5


class TestCheckHealth:
    @pytest.mark.asyncio
    async def test_healthy(self, weather_service):
        mock_response = _mock_response()
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.check_health()
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_unhealthy_on_error(self, weather_service):
        with patch(
            "httpx.AsyncClient.get",
            side_effect=httpx.ConnectError("refused"),
        ):
            result = await weather_service.check_health()
        assert result["status"] == "unhealthy"


class TestWeatherDataSerialization:
    def test_to_dict_roundtrip(self):
        original = _make_weather_data()
        serialized = original.to_dict()
        deserialized_data = serialized.copy()
        deserialized_data["timestamp"] = datetime.fromisoformat(deserialized_data["timestamp"])
        restored = WeatherData(**deserialized_data)

        assert restored.temperature == original.temperature
        assert restored.condition == original.condition
        assert restored.timestamp == original.timestamp
