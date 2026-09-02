import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import redis.asyncio as aioredis

from app.services.weather_service import (
    CACHE_PREFIX,
    GEOCODE_CACHE_PREFIX,
    WMO_CODES,
    GeocodingServiceError,
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

SAMPLE_FORECAST_RESPONSE_WITH_DAILY_FIELDS = {
    "daily": {
        "time": ["2026-02-28", "2026-03-01"],
        "temperature_2m_max": [18.0, 22.0],
        "temperature_2m_min": [8.0, 12.0],
        "precipitation_probability_max": [10, 40],
        "weather_code": [0, 61],
        "relative_humidity_2m_mean": [40, 42],
        "wind_speed_10m_max": [12.0, 14.0],
        "uv_index_max": [6.5, 7.0],
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


class TestGetCurrentWeatherRange:
    @pytest.mark.asyncio
    async def test_daily_block_populates_temp_min_max(self, weather_service, mock_redis):
        response_data = {
            **SAMPLE_API_RESPONSE,
            "daily": {"temperature_2m_max": [25.0], "temperature_2m_min": [15.0]},
        }
        mock_response = _mock_response(json_data=response_data)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_current_weather(40.71, -74.01)

        assert result.temp_min == pytest.approx(15.0)
        assert result.temp_max == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_missing_daily_key_leaves_range_none(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_API_RESPONSE)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_current_weather(40.71, -74.01)

        assert result.temp_min is None
        assert result.temp_max is None

    @pytest.mark.asyncio
    async def test_null_daily_block_leaves_range_none(self, weather_service, mock_redis):
        response_data = {**SAMPLE_API_RESPONSE, "daily": None}
        mock_response = _mock_response(json_data=response_data)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_current_weather(40.71, -74.01)

        assert result.temp_min is None
        assert result.temp_max is None

    @pytest.mark.asyncio
    async def test_empty_daily_lists_leave_range_none(self, weather_service, mock_redis):
        response_data = {
            **SAMPLE_API_RESPONSE,
            "daily": {"temperature_2m_max": [], "temperature_2m_min": []},
        }
        mock_response = _mock_response(json_data=response_data)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_current_weather(40.71, -74.01)

        assert result.temp_min is None
        assert result.temp_max is None

    @pytest.mark.asyncio
    async def test_null_entries_in_daily_lists_leave_range_none(self, weather_service, mock_redis):
        response_data = {
            **SAMPLE_API_RESPONSE,
            "daily": {"temperature_2m_max": [None], "temperature_2m_min": [None]},
        }
        mock_response = _mock_response(json_data=response_data)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_current_weather(40.71, -74.01)

        assert result.temp_min is None
        assert result.temp_max is None


def _hourly(start_hour, temps, day="2026-02-28", precipitation=None):
    times = []
    for i in range(len(temps)):
        hour = start_hour + i
        d = day if hour < 24 else "2026-03-01"
        times.append(f"{d}T{hour % 24:02d}:00")
    block = {"time": times, "temperature_2m": temps}
    block["precipitation_probability"] = precipitation or [10] + [0] * (len(temps) - 1)
    return block


class TestGetCurrentWeatherWindow:
    async def _fetch(self, weather_service, response_data):
        mock_response = _mock_response(json_data=response_data)
        with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
            result = await weather_service.get_current_weather(40.71, -74.01, use_cache=False)
        return result, mock_get

    @pytest.mark.asyncio
    async def test_requests_full_day_of_hourly_temperatures(self, weather_service, mock_redis):
        _, mock_get = await self._fetch(weather_service, SAMPLE_API_RESPONSE)
        params = mock_get.call_args[1]["params"]
        assert "temperature_2m" in params["hourly"]
        assert params["forecast_hours"] == 24

    @pytest.mark.asyncio
    async def test_morning_window_spans_current_hour_through_evening(
        self, weather_service, mock_redis
    ):
        temps = [
            5.0,
            7.0,
            12.0,
            18.0,
            24.0,
            29.0,
            30.0,
            28.0,
            25.0,
            22.0,
            20.0,
            18.0,
            16.0,
            14.0,
            12.0,
        ]
        temps += [10.0, 9.0, 8.0, 8.0, 7.0, 7.0, 6.0, 6.0, 5.0]
        response_data = {
            "current": {
                **SAMPLE_API_RESPONSE["current"],
                "time": "2026-02-28T07:30",
                "temperature_2m": 4.5,
            },
            "hourly": _hourly(7, temps),
        }
        result, _ = await self._fetch(weather_service, response_data)
        assert result.window_min == pytest.approx(4.5)
        assert result.window_max == pytest.approx(30.0)
        assert result.precipitation_chance == 10

    @pytest.mark.asyncio
    async def test_afternoon_window_ignores_the_morning_low(self, weather_service, mock_redis):
        temps = [
            28.0,
            30.0,
            29.0,
            26.0,
            22.0,
            19.0,
            17.0,
            15.0,
            13.0,
            11.0,
            9.0,
            8.0,
            7.0,
            6.0,
            5.0,
        ]
        temps += [5.0, 4.0, 4.0, 3.0, 3.0, 3.0, 4.0, 6.0, 9.0]
        response_data = {
            "current": {
                **SAMPLE_API_RESPONSE["current"],
                "time": "2026-02-28T14:30",
                "temperature_2m": 29.0,
            },
            "hourly": _hourly(14, temps),
            "daily": {"temperature_2m_max": [30.0], "temperature_2m_min": [3.0]},
        }
        result, _ = await self._fetch(weather_service, response_data)
        assert result.window_min == pytest.approx(15.0)
        assert result.window_max == pytest.approx(30.0)
        assert result.temp_min == pytest.approx(3.0)

    @pytest.mark.asyncio
    async def test_two_hours_left_still_forms_a_window(self, weather_service, mock_redis):
        temps = [20.0, 12.0] + [10.0] * 22
        response_data = {
            "current": {
                **SAMPLE_API_RESPONSE["current"],
                "time": "2026-02-28T20:30",
                "temperature_2m": 19.0,
            },
            "hourly": _hourly(20, temps),
        }
        result, _ = await self._fetch(weather_service, response_data)
        assert result.window_min == pytest.approx(12.0)
        assert result.window_max == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_late_evening_has_no_window(self, weather_service, mock_redis):
        temps = [20.0, 12.0] + [10.0] * 22
        response_data = {
            "current": {
                **SAMPLE_API_RESPONSE["current"],
                "time": "2026-02-28T21:30",
                "temperature_2m": 19.0,
            },
            "hourly": _hourly(21, temps),
        }
        result, _ = await self._fetch(weather_service, response_data)
        assert result.window_min is None
        assert result.window_max is None

    @pytest.mark.asyncio
    async def test_window_never_crosses_midnight(self, weather_service, mock_redis):
        temps = [20.0, 21.0, 22.0] + [40.0] * 21
        response_data = {
            "current": {
                **SAMPLE_API_RESPONSE["current"],
                "time": "2026-02-28T19:30",
                "temperature_2m": 20.0,
            },
            "hourly": _hourly(19, temps),
        }
        result, _ = await self._fetch(weather_service, response_data)
        assert result.window_max == pytest.approx(22.0)

    @pytest.mark.asyncio
    async def test_missing_hourly_temperatures_leave_window_none(self, weather_service, mock_redis):
        response_data = {
            "current": {**SAMPLE_API_RESPONSE["current"], "time": "2026-02-28T07:30"},
            "hourly": {"precipitation_probability": [35]},
        }
        result, _ = await self._fetch(weather_service, response_data)
        assert result.window_min is None
        assert result.precipitation_chance == 35

    @pytest.mark.asyncio
    async def test_missing_current_time_leaves_window_none(self, weather_service, mock_redis):
        response_data = {
            "current": SAMPLE_API_RESPONSE["current"],
            "hourly": _hourly(7, [5.0] * 24),
        }
        result, _ = await self._fetch(weather_service, response_data)
        assert result.window_min is None

    @pytest.mark.asyncio
    async def test_null_hourly_entries_are_skipped(self, weather_service, mock_redis):
        temps = [None, 8.0, None, 25.0] + [None] * 20
        response_data = {
            "current": {
                **SAMPLE_API_RESPONSE["current"],
                "time": "2026-02-28T07:30",
                "temperature_2m": 6.0,
            },
            "hourly": _hourly(7, temps),
        }
        result, _ = await self._fetch(weather_service, response_data)
        assert result.window_min == pytest.approx(6.0)
        assert result.window_max == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_all_null_hourly_entries_leave_window_none(self, weather_service, mock_redis):
        response_data = {
            "current": {**SAMPLE_API_RESPONSE["current"], "time": "2026-02-28T07:30"},
            "hourly": _hourly(7, [None] * 24),
        }
        result, _ = await self._fetch(weather_service, response_data)
        assert result.window_min is None


class TestGeocodeLocationName:
    @pytest.mark.asyncio
    async def test_raises_on_invalid_json_response(self, weather_service, mock_redis):
        request = httpx.Request("GET", "https://nominatim.openstreetmap.org/search")
        mock_response = httpx.Response(200, text="<html>rate limited</html>", request=request)

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            with pytest.raises(GeocodingServiceError, match="Failed to decode geocoding response"):
                await weather_service.geocode_location_name("New York City")

    @pytest.mark.asyncio
    async def test_caches_result_after_lookup(self, weather_service, mock_redis):
        request = httpx.Request("GET", "https://nominatim.openstreetmap.org/search")
        mock_response = httpx.Response(
            200,
            json=[{"lat": "51.5074", "lon": "-0.1278", "display_name": "London, England, UK"}],
            request=request,
        )

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.geocode_location_name("London")

        assert result == (51.5074, -0.1278, "London, England, UK")
        mock_redis.set.assert_awaited_once()
        assert mock_redis.set.call_args[0][0] == f"{GEOCODE_CACHE_PREFIX}london"

    @pytest.mark.asyncio
    async def test_uses_cache_without_http(self, weather_service, mock_redis):
        mock_redis.get.return_value = json.dumps(
            {"lat": 51.5074, "lon": -0.1278, "display_name": "London, England, UK"}
        )

        with patch(
            "httpx.AsyncClient.get", side_effect=AssertionError("must not call HTTP")
        ) as get:
            result = await weather_service.geocode_location_name("London")

        assert result == (51.5074, -0.1278, "London, England, UK")
        get.assert_not_called()


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

    @pytest.mark.asyncio
    async def test_parses_humidity_wind_uv(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_FORECAST_RESPONSE_WITH_DAILY_FIELDS)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_daily_forecast(40.71, -74.01, days=2)

        assert result[0].humidity == 40
        assert result[0].wind_speed == pytest.approx(12.0)
        assert result[0].uv_index == pytest.approx(6.5)
        assert result[1].humidity == 42

    @pytest.mark.asyncio
    async def test_old_shaped_payload_defaults_to_none(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_FORECAST_RESPONSE)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_daily_forecast(40.71, -74.01, days=2)

        assert result[0].humidity is None
        assert result[0].wind_speed is None
        assert result[0].uv_index is None


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
        assert result.temp_min == pytest.approx(12.0)
        assert result.temp_max == pytest.approx(22.0)
        assert result.window_min == pytest.approx(12.0)
        assert result.window_max == pytest.approx(22.0)
        assert result.humidity == 50
        assert result.wind_speed == 0
        assert result.uv_index == 0

    @pytest.mark.asyncio
    async def test_carries_forward_real_daily_fields(self, weather_service, mock_redis):
        mock_response = _mock_response(json_data=SAMPLE_FORECAST_RESPONSE_WITH_DAILY_FIELDS)
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            result = await weather_service.get_tomorrow_weather(40.71, -74.01)

        assert result.humidity == 42
        assert result.wind_speed == pytest.approx(14.0)
        assert result.uv_index == pytest.approx(7.0)
        assert result.temp_min == pytest.approx(12.0)
        assert result.temp_max == pytest.approx(22.0)

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

    def test_to_dict_round_trips_temp_range(self):
        original = _make_weather_data(temp_min=15.0, temp_max=25.0)
        data = original.to_dict()
        assert data["temp_min"] == 15.0
        assert data["temp_max"] == 25.0

    def test_to_dict_defaults_range_to_none(self):
        original = _make_weather_data()
        data = original.to_dict()
        assert data["temp_min"] is None
        assert data["temp_max"] is None

    def test_to_dict_round_trips_window(self):
        original = _make_weather_data(window_min=18.0, window_max=24.0)
        data = original.to_dict()
        assert data["window_min"] == 18.0
        assert data["window_max"] == 24.0

    def test_to_dict_defaults_window_to_none(self):
        original = _make_weather_data()
        data = original.to_dict()
        assert data["window_min"] is None
        assert data["window_max"] is None


class TestWeatherDataRedisCacheRoundTrip:
    @pytest.mark.asyncio
    async def test_cache_get_restores_window(self, weather_service, mock_redis):
        cached = _make_weather_data(window_min=12.0, window_max=27.5)
        mock_redis.get.return_value = json.dumps(cached.to_dict())

        result = await weather_service._cache_get(40.71, -74.01)

        assert result.window_min == pytest.approx(12.0)
        assert result.window_max == pytest.approx(27.5)

    @pytest.mark.asyncio
    async def test_cache_set_serializes_window(self, weather_service, mock_redis):
        data = _make_weather_data(window_min=10.0, window_max=20.0)
        await weather_service._cache_set(40.71, -74.01, data)

        stored = json.loads(mock_redis.set.call_args[0][1])
        assert stored["window_min"] == 10.0
        assert stored["window_max"] == 20.0

    @pytest.mark.asyncio
    async def test_cache_get_defaults_window_to_none_for_old_entries(
        self, weather_service, mock_redis
    ):
        legacy_payload = _make_weather_data().to_dict()
        del legacy_payload["window_min"]
        del legacy_payload["window_max"]
        mock_redis.get.return_value = json.dumps(legacy_payload)

        result = await weather_service._cache_get(40.71, -74.01)

        assert result.window_min is None
        assert result.window_max is None
