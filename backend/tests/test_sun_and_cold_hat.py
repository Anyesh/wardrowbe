from datetime import datetime

from app.services.item_scorer import _fit_factors
from app.services.recommendation_service import (
    RECOMMENDATION_PROMPT,
    cached_suggestion_fits,
    format_weather_details_text,
    suggestion_context,
    uv_bucket,
    wind_bucket,
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


class TestCacheContextSunAndWind:
    def _context(self, **weather):
        from app.models.outfit import TimeOfDay

        return suggestion_context(_weather_with(**weather), TimeOfDay.morning, None, None)

    def _fits(self, cached, now):
        return cached_suggestion_fits(cached, now, None)

    def test_uv_bucket_change_invalidates_the_cache(self):
        assert not self._fits(self._context(uv_index=2), self._context(uv_index=7))
        assert not self._fits(
            self._context(uv_index=2, uv_index_max=3), self._context(uv_index=2, uv_index_max=9)
        )

    def test_uv_within_a_bucket_is_reused(self):
        assert self._fits(self._context(uv_index=3.5), self._context(uv_index=5.5))

    def test_wind_crossing_the_threshold_invalidates_the_cache(self):
        assert not self._fits(self._context(wind_speed=10), self._context(wind_speed=30))
        assert not self._fits(self._context(wind_speed=20), self._context(wind_speed=26))

    def test_wind_within_a_bucket_is_reused(self):
        assert self._fits(self._context(wind_speed=5), self._context(wind_speed=12))
        assert self._fits(self._context(wind_speed=30), self._context(wind_speed=45))

    def test_old_cache_entries_without_sun_and_wind_are_not_reused(self):
        old = self._context()
        del old["uv"], old["wind"]
        assert not self._fits(old, self._context())

    def test_buckets(self):
        assert [uv_bucket(v) for v in (None, 0, 2.9, 3, 5.9, 6, 7.9, 8, 11)] == [
            None, 0, 0, 1, 1, 2, 2, 3, 3,
        ]  # fmt: skip
        assert [wind_bucket(v) for v in (0, 14.9, 15, 24.9, 25, 60)] == [0, 0, 1, 1, 2, 2]
