import pytest

from app.api.outfits import WeatherOverrideRequest


@pytest.mark.parametrize(
    ("feels_like", "expected"),
    [(0, 0), (-4.5, -4.5), (None, 12)],
    ids=["zero", "negative", "unset-uses-air-temperature"],
)
def test_override_feels_like_falls_back_only_when_unset(feels_like, expected):
    weather = WeatherOverrideRequest(temperature=12, feels_like=feels_like).to_weather()
    assert weather.temperature == 12
    assert weather.feels_like == expected
