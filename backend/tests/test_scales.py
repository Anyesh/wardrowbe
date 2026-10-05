import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.api.outfits import FamilyRatingRequest, FeedbackRequest
from app.schemas.preference import PreferenceBase, PreferenceUpdate, StyleProfile
from app.utils.garment_vocabulary import OCCASIONS
from app.utils.locale import DEFAULT_LOCALE, SUPPORTED_LOCALES
from app.utils.preference_defaults import DEFAULT_OCCASION
from app.utils.scales import (
    AVOID_REPEAT_DAYS_MAX,
    AVOID_REPEAT_DAYS_MIN,
    COLD_THRESHOLD_MAX,
    COLD_THRESHOLD_MIN,
    DEFAULT_AVOID_REPEAT_DAYS,
    DEFAULT_COLD_THRESHOLD,
    DEFAULT_HOT_THRESHOLD,
    DEFAULT_STYLE_SCORE,
    HOT_THRESHOLD_MAX,
    HOT_THRESHOLD_MIN,
    RATING_MAX,
    RATING_MIN,
    STYLE_SCORE_MAX,
    STYLE_SCORE_MIN,
    rating_to_signed,
    rating_to_unit,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data"


def test_locales_come_from_the_shared_file():
    data = json.loads((DATA_DIR / "locales.json").read_text())

    assert SUPPORTED_LOCALES == tuple(data["supported"])
    assert DEFAULT_LOCALE == data["default"]
    assert DEFAULT_LOCALE in SUPPORTED_LOCALES


def test_scales_come_from_the_shared_file():
    data = json.loads((DATA_DIR / "scales.json").read_text())
    cold = data["temperature_thresholds_celsius"]["cold"]
    hot = data["temperature_thresholds_celsius"]["hot"]

    assert (RATING_MIN, RATING_MAX) == (data["rating"]["min"], data["rating"]["max"])
    assert (COLD_THRESHOLD_MIN, COLD_THRESHOLD_MAX, DEFAULT_COLD_THRESHOLD) == (
        cold["min"],
        cold["max"],
        cold["default"],
    )
    assert (HOT_THRESHOLD_MIN, HOT_THRESHOLD_MAX, DEFAULT_HOT_THRESHOLD) == (
        hot["min"],
        hot["max"],
        hot["default"],
    )

    avoid = data["avoid_repeat_days"]
    assert (AVOID_REPEAT_DAYS_MIN, AVOID_REPEAT_DAYS_MAX, DEFAULT_AVOID_REPEAT_DAYS) == (
        avoid["min"],
        avoid["max"],
        avoid["default"],
    )

    style = data["style_score"]
    assert (STYLE_SCORE_MIN, STYLE_SCORE_MAX, DEFAULT_STYLE_SCORE) == (
        style["min"],
        style["max"],
        style["default"],
    )


def test_style_profile_defaults_and_bounds_come_from_the_style_scale():
    profile = StyleProfile()
    assert set(profile.model_dump().values()) == {DEFAULT_STYLE_SCORE}
    assert StyleProfile(casual=STYLE_SCORE_MIN, bold=STYLE_SCORE_MAX)
    with pytest.raises(ValidationError):
        StyleProfile(casual=STYLE_SCORE_MIN - 1)
    with pytest.raises(ValidationError):
        StyleProfile(casual=STYLE_SCORE_MAX + 1)


def test_default_occasion_is_a_known_occasion():
    assert DEFAULT_OCCASION in OCCASIONS


@pytest.mark.parametrize("schema", [PreferenceBase, PreferenceUpdate])
def test_avoid_repeat_days_bounds_are_inclusive(schema):
    assert (
        schema(avoid_repeat_days=AVOID_REPEAT_DAYS_MIN).avoid_repeat_days == AVOID_REPEAT_DAYS_MIN
    )
    assert (
        schema(avoid_repeat_days=AVOID_REPEAT_DAYS_MAX).avoid_repeat_days == AVOID_REPEAT_DAYS_MAX
    )
    with pytest.raises(ValidationError):
        schema(avoid_repeat_days=AVOID_REPEAT_DAYS_MIN - 1)
    with pytest.raises(ValidationError):
        schema(avoid_repeat_days=AVOID_REPEAT_DAYS_MAX + 1)


@pytest.mark.parametrize("rating", [RATING_MIN, RATING_MAX])
def test_rating_requests_accept_the_scale_ends(rating):
    assert FamilyRatingRequest(rating=rating).rating == rating
    assert FeedbackRequest(rating=rating, comfort_rating=rating, style_rating=rating)


@pytest.mark.parametrize("rating", [RATING_MIN - 1, RATING_MAX + 1])
def test_rating_requests_reject_values_off_the_scale(rating):
    with pytest.raises(ValidationError):
        FamilyRatingRequest(rating=rating)
    for field in ("rating", "comfort_rating", "style_rating"):
        with pytest.raises(ValidationError):
            FeedbackRequest(**{field: rating})


@pytest.mark.parametrize("schema", [PreferenceBase, PreferenceUpdate])
@pytest.mark.parametrize(
    ("field", "low", "high"),
    [
        ("cold_threshold", COLD_THRESHOLD_MIN, COLD_THRESHOLD_MAX),
        ("hot_threshold", HOT_THRESHOLD_MIN, HOT_THRESHOLD_MAX),
    ],
)
def test_threshold_bounds_are_inclusive(schema, field, low, high):
    assert getattr(schema(**{field: low}), field) == low
    assert getattr(schema(**{field: high}), field) == high
    with pytest.raises(ValidationError):
        schema(**{field: low - 1})
    with pytest.raises(ValidationError):
        schema(**{field: high + 1})


def test_rating_maps_onto_unit_and_signed_ranges():
    midpoint = (RATING_MIN + RATING_MAX) / 2

    assert rating_to_unit(RATING_MIN) == 0
    assert rating_to_unit(RATING_MAX) == 1
    assert rating_to_unit(midpoint) == 0.5
    assert rating_to_signed(RATING_MIN) == -1
    assert rating_to_signed(midpoint) == 0
    assert rating_to_signed(RATING_MAX) == 1
