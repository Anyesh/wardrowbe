from datetime import date, datetime
from uuid import uuid4

import pytest

from app.models.item import ClothingItem
from app.models.preference import UserPreference
from app.services.item_scorer import (
    MIN_ITEMS_FOR_SCORING,
    _formality_score,
    _pair_bonus,
    _preference_score,
    _recency_score,
    _season_score,
    _weather_score,
    get_season,
    score_items,
    scoring_temp_range,
)
from app.services.weather_service import WeatherData


def _item(**kwargs) -> ClothingItem:
    defaults = {
        "id": uuid4(),
        "user_id": uuid4(),
        "type": "shirt",
        "subtype": None,
        "image_path": "test.jpg",
        "primary_color": None,
        "colors": [],
        "pattern": None,
        "material": None,
        "style": [],
        "formality": "casual",
        "season": [],
        "last_worn_at": None,
        "needs_wash": False,
        "is_archived": False,
    }
    defaults.update(kwargs)
    return ClothingItem(**defaults)


def _weather(
    temp=20,
    precipitation=0,
    temp_min=None,
    temp_max=None,
    is_day=True,
    window_min=None,
    window_max=None,
) -> WeatherData:
    return WeatherData(
        temperature=temp,
        feels_like=temp,
        humidity=50,
        precipitation_chance=precipitation,
        precipitation_mm=0,
        wind_speed=10,
        condition="clear",
        condition_code=0,
        is_day=is_day,
        uv_index=5,
        timestamp=datetime(2026, 3, 8, 12, 0),
        temp_min=temp_min,
        temp_max=temp_max,
        window_min=window_min,
        window_max=window_max,
    )


def _prefs(**kwargs) -> UserPreference:
    defaults = {
        "user_id": uuid4(),
        "cold_threshold": 10,
        "hot_threshold": 25,
        "temperature_sensitivity": "normal",
        "color_favorites": [],
        "color_avoid": [],
        "avoid_repeat_days": 7,
        "variety_level": "moderate",
    }
    defaults.update(kwargs)
    return UserPreference(**defaults)


class TestWeatherScore:
    def test_cold_outerwear_scores_high(self):
        item = _item(type="outerwear")
        assert _weather_score(item, _weather(temp=5), None) == 1.0

    def test_cold_shorts_scores_low(self):
        item = _item(type="shorts")
        assert _weather_score(item, _weather(temp=5), None) == 0.05

    def test_hot_cotton_scores_high(self):
        item = _item(type="shirt", material="cotton")
        assert _weather_score(item, _weather(temp=30), None) == 1.0

    def test_moderate_all_pass(self):
        item = _item(type="shirt")
        assert _weather_score(item, _weather(temp=18), None) == 1.0

    def test_cold_threshold_sensitivity(self):
        item = _item(type="shorts")
        prefs = _prefs(temperature_sensitivity="high")
        # high sensitivity: cold_threshold=10+5=15, hot_threshold=25-5=20
        # temp=12 < 15 → cold weather, shorts get 0.05
        assert _weather_score(item, _weather(temp=12), prefs) == 0.05

    def test_rain_boosts_outerwear(self):
        item = _item(type="outerwear")
        assert _weather_score(item, _weather(temp=18, precipitation=60), None) == 1.0

    def test_cold_wool_scores_high(self):
        item = _item(type="shirt", material="wool")
        assert _weather_score(item, _weather(temp=5), None) == 1.0

    def test_hot_sweater_scores_low(self):
        item = _item(type="sweater")
        assert _weather_score(item, _weather(temp=30), None) == 0.05

    def test_cold_regular_shirt(self):
        item = _item(type="shirt")
        assert _weather_score(item, _weather(temp=5), None) == 0.7


class TestWeatherScoreRange:
    def test_range_ignored_when_min_max_absent(self):
        item = _item(type="sweater", material="wool")
        assert _weather_score(item, _weather(temp=30), None) == 0.05

    def test_range_ignored_when_swing_small(self):
        item = _item(type="sweater", material="wool")
        weather = _weather(temp=22, window_min=18, window_max=24)
        assert _weather_score(item, weather, None) == 1.0

    def test_daily_range_alone_does_not_trigger_blend(self):
        item = _item(type="sweater", material="wool")
        weather = _weather(temp=12, temp_min=5, temp_max=30)
        assert _weather_score(item, weather, None) == 1.0

    def test_window_applies_regardless_of_is_day(self):
        item = _item(type="sweater", material="wool")
        weather = _weather(temp=5, window_min=5, window_max=30, is_day=False)
        assert _weather_score(item, weather, None) == pytest.approx(0.525)

    def test_heavy_sweater_penalized_on_big_swing(self):
        item = _item(type="sweater", material="wool")
        weather = _weather(temp=12, window_min=5, window_max=30)
        assert _weather_score(item, weather, None) == pytest.approx(0.525)

    def test_wool_coat_penalized_on_big_swing(self):
        item = _item(type="coat", material="wool")
        weather = _weather(temp=12, window_min=5, window_max=30)
        assert _weather_score(item, weather, None) == pytest.approx(0.525)

    def test_light_jacket_beats_heavy_coat(self):
        weather = _weather(temp=12, window_min=5, window_max=30)
        jacket = _weather_score(_item(type="jacket", material="nylon"), weather, None)
        coat = _weather_score(_item(type="coat", material="wool"), weather, None)
        assert jacket == pytest.approx(0.80)
        assert jacket > coat

    def test_shorts_not_near_zero_on_hot_afternoon(self):
        item = _item(type="shorts")
        weather = _weather(temp=12, window_min=5, window_max=30)
        assert _weather_score(item, weather, None) == pytest.approx(0.425)

    def test_adaptable_shirt_outranks_both_extremes(self):
        weather = _weather(temp=12, window_min=5, window_max=30)
        shirt = _weather_score(_item(type="shirt", material="cotton"), weather, None)
        sweater = _weather_score(_item(type="sweater", material="wool"), weather, None)
        shorts = _weather_score(_item(type="shorts"), weather, None)
        assert shirt == pytest.approx(0.85)
        assert shirt > sweater
        assert shirt > shorts

    def test_rain_boost_still_applies_in_range_mode(self):
        item = _item(type="jacket", material="nylon")
        weather = _weather(temp=12, window_min=5, window_max=30, precipitation=60)
        boosted = _weather_score(item, weather, None)
        no_rain = _weather_score(item, _weather(temp=12, window_min=5, window_max=30), None)
        assert boosted == pytest.approx(min(1.0, no_rain + 0.1))

    def test_threshold_preferences_feed_both_bucket_evaluations(self):
        item = _item(type="shirt")
        prefs = _prefs(temperature_sensitivity="high")
        weather = _weather(temp=17, window_min=13, window_max=21)
        assert _weather_score(item, weather, prefs) == pytest.approx(0.75)


class TestWeatherScoreHeavyLayers:
    def _swing(self, **kwargs):
        weather = _weather(temp=12, window_min=5, window_max=30)
        return _weather_score(_item(**kwargs), weather, None)

    def test_puffer_with_unknown_material_is_heavy(self):
        assert self._swing(type="jacket", subtype="puffer") == pytest.approx(0.525)

    def test_parka_with_light_shell_material_is_heavy(self):
        assert self._swing(type="jacket", subtype="parka", material="nylon") == pytest.approx(0.525)

    def test_coat_with_unknown_material_is_heavy(self):
        assert self._swing(type="coat") == pytest.approx(0.525)

    def test_anorak_with_unknown_material_gets_removable_floor(self):
        assert self._swing(type="jacket", subtype="anorak") == pytest.approx(0.80)

    def test_jacket_with_unknown_material_and_subtype_gets_removable_floor(self):
        assert self._swing(type="jacket") == pytest.approx(0.80)

    def test_subtype_match_is_case_insensitive(self):
        assert self._swing(type="jacket", subtype="Puffer") == pytest.approx(0.525)

    def test_light_jacket_outranks_null_material_puffer(self):
        assert self._swing(type="jacket", subtype="windbreaker") > self._swing(
            type="jacket", subtype="puffer"
        )


class TestScoringTempRange:
    def test_none_without_window(self):
        assert scoring_temp_range(_weather(temp=12, temp_min=5, temp_max=30)) is None

    def test_none_below_swing_threshold(self):
        assert scoring_temp_range(_weather(temp=18, window_min=15, window_max=20)) is None

    def test_none_when_one_bound_missing(self):
        assert scoring_temp_range(_weather(window_min=5)) is None
        assert scoring_temp_range(_weather(window_max=30)) is None

    def test_returns_bounds_at_threshold(self):
        assert scoring_temp_range(_weather(window_min=10, window_max=18)) == (10, 18)


class TestWeatherScoreRealItemTypes:
    def test_cold_jacket_scores_as_warm_layer(self):
        item = _item(type="jacket")
        assert _weather_score(item, _weather(temp=5), None) == 1.0

    def test_hot_coat_penalized(self):
        item = _item(type="coat")
        assert _weather_score(item, _weather(temp=30), None) == 0.05

    def test_rain_boost_fires_for_real_jacket_type(self):
        item = _item(type="jacket")
        assert _weather_score(item, _weather(temp=18, precipitation=60), None) == 1.0

    def test_cardigan_and_vest_get_removable_floor_but_no_rain_boost(self):
        swing = _weather(temp=12, window_min=5, window_max=30)
        rain = _weather(temp=30, precipitation=60)
        for item_type in ("cardigan", "vest"):
            assert _weather_score(_item(type=item_type), swing, None) == pytest.approx(0.80)
            assert _weather_score(_item(type=item_type), rain, None) == pytest.approx(0.05)

    def test_rain_boost_fires_for_coat_and_hoodie(self):
        for item_type in ("coat", "hoodie"):
            item = _item(type=item_type)
            assert _weather_score(item, _weather(temp=30, precipitation=60), None) == pytest.approx(
                0.15
            )

    def test_blazer_gets_no_rain_boost(self):
        item = _item(type="blazer")
        assert _weather_score(item, _weather(temp=30, precipitation=60), None) == pytest.approx(
            0.05
        )

    def test_legacy_outerwear_type_still_honored(self):
        item = _item(type="outerwear")
        assert _weather_score(item, _weather(temp=5), None) == 1.0


class TestFormalityScore:
    def test_exact_match(self):
        item = _item(formality="casual")
        assert _formality_score(item, "casual") == 1.0

    def test_one_off(self):
        item = _item(formality="business-casual")
        assert _formality_score(item, "casual") == 0.5

    def test_two_off(self):
        item = _item(formality="formal")
        assert _formality_score(item, "casual") == 0.15

    def test_unknown_occasion_defaults(self):
        item = _item(formality="casual")
        assert _formality_score(item, "picnic") == 1.0


class TestSeasonScore:
    def test_match(self):
        item = _item(season=["summer"])
        assert _season_score(item, "summer") == 1.0

    def test_adjacent(self):
        item = _item(season=["summer"])
        assert _season_score(item, "spring") == 0.6

    def test_opposite(self):
        item = _item(season=["summer"])
        assert _season_score(item, "winter") == 0.2

    def test_no_tags(self):
        item = _item(season=[])
        assert _season_score(item, "winter") == 1.0

    def test_all_season(self):
        item = _item(season=["all-season"])
        assert _season_score(item, "winter") == 1.0
        assert _season_score(item, "summer") == 1.0
        assert _season_score(item, "spring") == 1.0
        assert _season_score(item, "fall") == 1.0

    def test_summer_item_in_fall_with_hot_weather(self):
        item = _item(season=["summer"])
        hot_weather = _weather(temp=28)
        assert _season_score(item, "fall", hot_weather) == 1.0

    def test_summer_item_in_fall_with_cool_weather(self):
        item = _item(season=["summer"])
        cool_weather = _weather(temp=18)
        assert _season_score(item, "fall", cool_weather) == 0.6

    def test_winter_item_in_spring_with_cold_weather(self):
        item = _item(season=["winter"])
        cold_weather = _weather(temp=5)
        assert _season_score(item, "spring", cold_weather) == 1.0


class TestGetSeason:
    def test_northern_hemisphere(self):
        assert get_season(1, 40.0) == "winter"
        assert get_season(7, 40.0) == "summer"

    def test_southern_hemisphere(self):
        assert get_season(1, -33.0) == "summer"
        assert get_season(7, -33.0) == "winter"

    def test_equator_defaults_north(self):
        assert get_season(1, 0.0) == "winter"

    def test_none_latitude_defaults_north(self):
        assert get_season(7, None) == "summer"


class TestRecencyScore:
    def test_never_worn(self):
        item = _item()
        assert _recency_score(item, date(2026, 3, 8), 7, {}) == 1.0

    def test_worn_today(self):
        item = _item()
        today = date(2026, 3, 8)
        assert _recency_score(item, today, 7, {item.id: today}) == 0.1

    def test_linear_interpolation(self):
        item = _item()
        today = date(2026, 3, 8)
        worn = date(2026, 3, 4)
        score = _recency_score(item, today, 7, {item.id: worn})
        expected = 0.1 + 0.9 * (4 / 7)
        assert abs(score - expected) < 0.001

    def test_beyond_avoid_days(self):
        item = _item()
        today = date(2026, 3, 8)
        worn = date(2026, 2, 20)
        assert _recency_score(item, today, 7, {item.id: worn}) == 1.0


class TestPreferenceScore:
    def test_fav_color_boost(self):
        item = _item(primary_color="blue")
        prefs = _prefs(color_favorites=["blue"])
        assert _preference_score(item, prefs, None) == 1.1

    def test_avoid_color_penalty(self):
        item = _item(primary_color="orange")
        prefs = _prefs(color_avoid=["orange"])
        assert _preference_score(item, prefs, None) == 0.7

    def test_clamped_bounds(self):
        item = _item(primary_color="orange")
        prefs = _prefs(color_avoid=["orange"])
        learned = {
            "learned_avoid_colors": ["orange"],
            "learned_favorite_colors": [],
        }
        score = _preference_score(item, prefs, learned)
        assert score >= 0.3
        assert score <= 1.2

    def test_learned_fav_boost(self):
        item = _item(primary_color="blue")
        learned = {"learned_favorite_colors": ["blue"]}
        assert _preference_score(item, None, learned) == 1.05

    def test_learned_style_match(self):
        item = _item(style=["casual", "minimal"])
        learned = {"learned_preferred_styles": ["casual", "minimal"]}
        score = _preference_score(item, None, learned)
        assert score == pytest.approx(1.06, abs=0.001)


class TestPairBonus:
    def test_good_pairs(self):
        items = [_item() for _ in range(3)]
        pairs = {items[0].id: [items[1].id, items[2].id]}
        bonus = _pair_bonus(items[0], items, pairs)
        assert bonus == 0.1

    def test_capped_at_015(self):
        items = [_item() for _ in range(5)]
        pairs = {items[0].id: [i.id for i in items[1:]]}
        bonus = _pair_bonus(items[0], items, pairs)
        assert bonus == 0.15

    def test_no_pairs(self):
        items = [_item() for _ in range(3)]
        assert _pair_bonus(items[0], items, {}) == 0.0


class TestScoreItems:
    def test_sorts_descending(self):
        items = [
            _item(type="shorts"),
            _item(type="outerwear"),
        ]
        filler = [_item() for _ in range(MIN_ITEMS_FOR_SCORING - 2)]
        all_items = items + filler

        result = score_items(
            items=all_items,
            weather=_weather(temp=5),
            occasion="casual",
            preferences=None,
            user_today=date(2026, 3, 8),
            current_season="spring",
            learned_prefs=None,
            good_pairs={},
            recently_worn_dates={},
        )

        outerwear_pos = next(i for i, s in enumerate(result) if s.item.type == "outerwear")
        shorts_pos = next(i for i, s in enumerate(result) if s.item.type == "shorts")
        assert outerwear_pos < shorts_pos

    def test_returns_top_n(self):
        items = [_item() for _ in range(100)]
        result = score_items(
            items=items,
            weather=_weather(),
            occasion="casual",
            preferences=None,
            user_today=date(2026, 3, 8),
            current_season="spring",
            learned_prefs=None,
            good_pairs={},
            recently_worn_dates={},
        )
        assert len(result) <= 70

    def test_prioritizes_mandatory_items_into_top_n(self):
        items = [_item(type="shirt") for _ in range(100)]
        mandatory_item = _item(type="shorts")
        items.append(mandatory_item)

        result = score_items(
            items=items,
            weather=_weather(temp=5),
            occasion="casual",
            preferences=None,
            user_today=date(2026, 3, 8),
            current_season="spring",
            learned_prefs=None,
            good_pairs={},
            recently_worn_dates={},
            mandatory_item_ids={mandatory_item.id},
        )

        assert result[0].item.id == mandatory_item.id
        assert mandatory_item.id in {s.item.id for s in result}

    def test_small_wardrobe_skips_scoring(self):
        items = [_item() for _ in range(10)]
        result = score_items(
            items=items,
            weather=_weather(),
            occasion="casual",
            preferences=None,
            user_today=date(2026, 3, 8),
            current_season="spring",
            learned_prefs=None,
            good_pairs={},
            recently_worn_dates={},
        )
        assert len(result) == 10
        assert all(s.score == 1.0 for s in result)

    def test_bad_weather_tanks_score(self):
        items = [_item(type="shorts") for _ in range(MIN_ITEMS_FOR_SCORING)]
        result = score_items(
            items=items,
            weather=_weather(temp=5),
            occasion="casual",
            preferences=None,
            user_today=date(2026, 3, 8),
            current_season="spring",
            learned_prefs=None,
            good_pairs={},
            recently_worn_dates={},
        )
        assert all(s.score < 0.1 for s in result)

    def test_big_swing_day_shirt_outranks_sweater(self):
        shirt = _item(type="shirt", material="cotton")
        sweater = _item(type="sweater", material="wool")
        filler = [_item() for _ in range(MIN_ITEMS_FOR_SCORING - 2)]
        result = score_items(
            items=[shirt, sweater] + filler,
            weather=_weather(temp=12, window_min=5, window_max=30),
            occasion="casual",
            preferences=None,
            user_today=date(2026, 3, 8),
            current_season="spring",
            learned_prefs=None,
            good_pairs={},
            recently_worn_dates={},
        )
        shirt_pos = next(i for i, s in enumerate(result) if s.item.id == shirt.id)
        sweater_pos = next(i for i, s in enumerate(result) if s.item.id == sweater.id)
        assert shirt_pos < sweater_pos

    def test_without_range_data_sweater_still_beats_shirt(self):
        shirt = _item(type="shirt", material="cotton")
        sweater = _item(type="sweater", material="wool")
        filler = [_item() for _ in range(MIN_ITEMS_FOR_SCORING - 2)]
        result = score_items(
            items=[shirt, sweater] + filler,
            weather=_weather(temp=5),
            occasion="casual",
            preferences=None,
            user_today=date(2026, 3, 8),
            current_season="spring",
            learned_prefs=None,
            good_pairs={},
            recently_worn_dates={},
        )
        shirt_pos = next(i for i, s in enumerate(result) if s.item.id == shirt.id)
        sweater_pos = next(i for i, s in enumerate(result) if s.item.id == sweater.id)
        assert sweater_pos < shirt_pos

    def test_ensures_footwear_represented_in_top_n(self):
        # 75 shirts (scoring high) + 3 footwear (scoring lower)
        shirts = [_item(type="shirt") for _ in range(75)]
        shoes = [_item(type="sneakers") for _ in range(3)]
        all_items = shirts + shoes
        result = score_items(
            items=all_items,
            weather=_weather(temp=20),
            occasion="casual",
            preferences=None,
            user_today=date(2026, 3, 8),
            current_season="spring",
            learned_prefs=None,
            good_pairs={},
            recently_worn_dates={},
        )
        footwear_in_result = [s for s in result if s.item.type == "sneakers"]
        assert len(footwear_in_result) == 3
