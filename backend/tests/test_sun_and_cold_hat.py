from datetime import datetime

from app.services.item_scorer import _fit_factors
from app.services.recommendation_service import (
    RECOMMENDATION_PROMPT,
    format_weather_details_text,
)
from app.services.weather_service import WeatherData
from tests.test_item_scorer import _item, _weather


def _factor(item, weather):
    return _fit_factors(item, weather, "casual", "spring", None, None)[0]


def _weather_with(**kwargs) -> WeatherData:
    weather = _weather(temp=20)
    for key, value in kwargs.items():
        setattr(weather, key, value)
    return weather


class TestSunAndColdHat:
    def _format(self, weather):
        return RECOMMENDATION_PROMPT.format(
            occasion="casual",
            time_of_day="morning",
            temperature=weather.temperature,
            feels_like=weather.feels_like,
            condition=weather.condition,
            precipitation_chance=weather.precipitation_chance,
            temp_range_text="",
            weather_details_text=format_weather_details_text(weather),
            preferences_text="",
            items_text="[1] sneakers",
            mandatory_items_section="",
        )

    def test_uv_index_reaches_the_prompt(self):
        prompt = self._format(_weather_with(uv_index=7.0, uv_index_max=8.5))
        assert "UV index 7 now, up to 8.5 today" in prompt

    def test_uv_without_daily_max(self):
        assert format_weather_details_text(_weather_with(uv_index=3.0)) == "- UV index 3"

    def test_wind_is_mentioned_when_strong(self):
        text = format_weather_details_text(_weather_with(wind_speed=32))
        assert "windy (32 km/h)" in text
        assert "windy" not in format_weather_details_text(_weather_with(wind_speed=10))

    def test_hat_rule(self):
        assert "Never add a hat just to complete the look" in RECOMMENDATION_PROMPT
        assert "UV index is 6 or higher" in RECOMMENDATION_PROMPT
        assert "(belt, scarf, hat" not in RECOMMENDATION_PROMPT

    def test_hats_are_not_boosted_by_any_weather(self):
        hat = _item(type="hat")
        shirt = _item(type="shirt")
        for weather in (_weather(temp=2), _weather(temp=15), _weather(temp=32)):
            assert _factor(hat, weather) <= 1.0
            assert _factor(hat, weather) <= _factor(shirt, weather) + 1e-9


def test_weather_data_round_trips_uv_max():
    weather = _weather_with(uv_index_max=7.5)
    assert (
        WeatherData(**{**weather.to_dict(), "timestamp": datetime(2026, 3, 8)}).uv_index_max == 7.5
    )
