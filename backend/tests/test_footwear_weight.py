from datetime import date

import pytest

from app.models.item import ClothingItem
from app.services.item_scorer import (
    HEAVY_FOOTWEAR_WARM_FACTOR,
    LIGHT_FOOTWEAR_COLD_FACTOR,
    MEDIUM_FOOTWEAR_WARM_FACTOR,
    ScoredItem,
    _fit_factors,
    _footwear_weight_score,
    footwear_weight,
    has_light_footwear,
    score_items,
)
from app.services.recommendation_service import (
    RECOMMENDATION_PROMPT,
    RecommendationService,
)
from tests.test_item_scorer import _item, _prefs, _weather


def _shoe(**kwargs) -> ClothingItem:
    kwargs.setdefault("type", "sneakers")
    return _item(**kwargs)


class TestFootwearWeight:
    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            # Chunky sole but a mesh upper in nylon: neither leather bulk nor truly airy.
            (
                {
                    "ai_description": (
                        "Black lace-up sneakers with a chunky sole and textured mesh upper"
                    ),
                    "material": "nylon",
                    "season": ["all-season"],
                },
                "medium",
            ),
            ({"subtype": "knit sneaker", "material": "knit", "season": ["all-season"]}, "light"),
            ({"ai_description": "Slip-on knit trainers"}, "light"),
            ({"type": "boots", "subtype": "combat boots", "material": "leather"}, "heavy"),
            ({"type": "boots", "subtype": "suede chukka boots", "material": "suede"}, "heavy"),
            ({"type": "sandals"}, "light"),
            ({"type": "shoes", "subtype": "espadrilles"}, "light"),
            ({"type": "shoes", "subtype": "slides"}, "light"),
            ({"material": "canvas"}, "light"),
            ({"material": "linen"}, "light"),
            ({"ai_description": "High-top sneakers in white leather"}, "heavy"),
            ({"ai_description": "Sneakers lined with soft fleece"}, "heavy"),
            ({"ai_description": "Unlined leather sneakers"}, "medium"),
            ({"material": "shearling"}, "heavy"),
            ({"ai_description": "Chunky leather platform sneakers"}, "heavy"),
            ({"material": "suede", "ai_description": "Chunky suede sneakers"}, "heavy"),
            ({"season": ["winter"]}, "heavy"),
            ({"season": ["fall", "winter"]}, "medium"),
            ({"season": ["summer"]}, "light"),
            ({"season": ["summer", "spring"]}, "light"),
            ({"season": ["all-season"], "material": "leather"}, "medium"),
            ({"type": "flats", "material": "leather"}, "medium"),
            ({"type": "heels", "material": "leather"}, "medium"),
        ],
    )
    def test_classification(self, kwargs, expected):
        assert footwear_weight(_shoe(**kwargs)) == expected

    def test_not_footwear_is_none(self):
        assert footwear_weight(_item(type="shirt")) is None
        assert footwear_weight(_item(type="hat")) is None

    def test_winter_boots_with_all_season_tag_are_still_heavy(self):
        assert footwear_weight(_shoe(type="boots", season=["all-season"])) == "heavy"


def _factor(item, weather, light_available=True, prefs=None):
    return _fit_factors(item, weather, "casual", "spring", prefs, None, light_available)[0]


def _feels(temp, feels_like, **kwargs):
    weather = _weather(temp=temp, **kwargs)
    weather.feels_like = feels_like
    return weather


class TestFootwearScoring:
    def test_warm_day_prefers_light_over_heavy(self):
        weather = _feels(22.6, 24)
        light = _factor(_shoe(material="knit"), weather)
        medium = _factor(_shoe(material="leather"), weather)
        heavy = _factor(_shoe(ai_description="Chunky leather sneakers"), weather)
        assert light > medium > heavy
        assert heavy == pytest.approx(
            HEAVY_FOOTWEAR_WARM_FACTOR * _factor(_item(type="hat"), weather)
        )

    def test_medium_penalty_only_when_a_light_alternative_exists(self):
        weather = _feels(22.6, 24)
        medium = _shoe(material="leather")
        with_light = _factor(medium, weather, light_available=True)
        without = _factor(medium, weather, light_available=False)
        assert with_light == pytest.approx(without * MEDIUM_FOOTWEAR_WARM_FACTOR)

    def test_feels_like_alone_makes_it_warm(self):
        heavy = _shoe(type="boots")
        cool_air = _factor(heavy, _feels(18, 18))
        hot_feel = _factor(heavy, _feels(18, 23))
        assert hot_feel < cool_air

    def test_temp_range_uses_its_midpoint(self):
        heavy = _shoe(ai_description="High-top sneakers")
        swing = _weather(temp=20, window_min=8, window_max=18)
        assert _footwear_weight_score(heavy, swing, None, True) == _footwear_weight_score(
            heavy, _weather(temp=13), None, True
        )
        hot_swing = _weather(temp=20, window_min=18, window_max=30)
        assert _footwear_weight_score(heavy, hot_swing, None, True) < 1.0

    def test_threshold_follows_user_preference(self):
        heavy = _shoe(ai_description="High-top sneakers")
        weather = _feels(20, 20)
        assert _factor(heavy, weather, prefs=_prefs(hot_threshold=25)) > _factor(
            heavy, weather, prefs=_prefs(hot_threshold=20)
        )

    def test_cold_day_mildly_penalises_light_shoes(self):
        weather = _weather(temp=4)
        light = _shoe(material="knit")
        heavy = _shoe(type="boots")
        assert _footwear_weight_score(heavy, weather, None, True) == 1.0
        assert _footwear_weight_score(light, weather, None, True) == LIGHT_FOOTWEAR_COLD_FACTOR
        assert LIGHT_FOOTWEAR_COLD_FACTOR > 0.5

    def test_mild_day_does_not_change_footwear(self):
        weather = _weather(temp=15)
        assert (
            _factor(_shoe(type="boots"), weather)
            == _factor(_shoe(material="knit"), weather)
            == _factor(_item(type="hat"), weather)
        )

    def test_nothing_is_excluded(self):
        assert _factor(_shoe(type="boots"), _feels(22.6, 24)) > 0

    def test_has_light_footwear(self):
        assert has_light_footwear([_shoe(material="knit")])
        assert not has_light_footwear([_shoe(type="boots"), _item(type="shirt")])

    def test_score_items_ranks_light_shoe_above_heavy_on_a_warm_day(self):
        heavy = _shoe(ai_description="Chunky leather sneakers")
        light = _shoe(material="knit")
        items = [heavy, light, *[_item() for _ in range(60)]]
        result = score_items(
            items=items,
            weather=_feels(22.6, 24),
            occasion="casual",
            preferences=None,
            user_today=date(2026, 3, 8),
            current_season="spring",
            learned_prefs=None,
            good_pairs={},
            recently_worn_dates={},
        )
        order = [s.item.id for s in result]
        assert order.index(light.id) < order.index(heavy.id)


class TestFootwearPrompt:
    def test_rule_in_prompt(self):
        assert "Match footwear weight to the weather" in RECOMMENDATION_PROMPT
        assert "light, breathable shoes when warm" in RECOMMENDATION_PROMPT

    def test_items_text_lists_footwear_weight_only_for_shoes(self):
        service = RecommendationService.__new__(RecommendationService)
        boots = _shoe(type="boots")
        knit = _shoe(material="knit")
        shirt = _item(type="shirt")
        text, _ = service._format_items_for_prompt(
            [ScoredItem(item=i) for i in (boots, knit, shirt)], {}, date(2026, 3, 8)
        )
        lines = text.splitlines()
        assert "footwear weight: heavy" in lines[0]
        assert "footwear weight: light" in lines[1]
        assert "footwear weight" not in lines[2]
