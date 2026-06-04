from dataclasses import dataclass
from datetime import date
from statistics import median
from uuid import UUID

from app.models.item import ClothingItem
from app.models.preference import UserPreference
from app.services.weather_service import WeatherData

OCCASION_FORMALITY = {
    "casual": ["very-casual", "casual", "smart-casual"],
    "work": ["smart-casual", "business-casual", "formal"],
    "office": ["smart-casual", "business-casual", "formal"],
    "formal": ["business-casual", "formal", "very-formal"],
    "sporty": ["very-casual", "casual"],
    "outdoor": ["very-casual", "casual"],
    "date": ["smart-casual", "business-casual", "formal"],
    "party": ["smart-casual", "business-casual", "formal"],
}

_NORTH_SEASON = {
    1: "winter",
    2: "winter",
    3: "spring",
    4: "spring",
    5: "spring",
    6: "summer",
    7: "summer",
    8: "summer",
    9: "fall",
    10: "fall",
    11: "fall",
    12: "winter",
}

_SOUTH_SEASON = {
    1: "summer",
    2: "summer",
    3: "fall",
    4: "fall",
    5: "fall",
    6: "winter",
    7: "winter",
    8: "winter",
    9: "spring",
    10: "spring",
    11: "spring",
    12: "summer",
}


def get_season(month: int, latitude: float | None = None) -> str:
    if latitude is not None and latitude < 0:
        return _SOUTH_SEASON[month]
    return _NORTH_SEASON[month]


FORMALITY_ORDER = [
    "very-casual",
    "casual",
    "smart-casual",
    "business-casual",
    "formal",
    "very-formal",
]

SEASON_ADJACENCY = {
    "spring": ["summer", "winter"],
    "summer": ["spring", "fall"],
    "fall": ["summer", "winter"],
    "winter": ["fall", "spring"],
}

TOP_N = 70
MIN_ITEMS_FOR_SCORING = 50


@dataclass
class ScoredItem:
    item: ClothingItem
    score: float = 1.0
    weather_score: float = 1.0
    formality_score: float = 1.0
    season_score: float = 1.0
    recency_score: float = 1.0
    preference_score: float = 1.0
    usage_score: float = 1.0
    pair_bonus: float = 0.0


def _weather_score(
    item: ClothingItem,
    weather: WeatherData,
    preferences: UserPreference | None,
) -> float:
    temp = weather.temperature
    cold_threshold = 10
    hot_threshold = 25

    if preferences:
        if preferences.cold_threshold is not None:
            cold_threshold = preferences.cold_threshold
        if preferences.hot_threshold is not None:
            hot_threshold = preferences.hot_threshold
        if preferences.temperature_sensitivity == "high":
            cold_threshold += 5
            hot_threshold -= 5
        elif preferences.temperature_sensitivity == "low":
            cold_threshold -= 5
            hot_threshold += 5

    item_type = (item.type or "").lower()
    material = (item.material or "").lower()
    seasons = item.season or []
    score = 1.0

    if temp < cold_threshold:
        if item_type in ("outerwear", "sweater") or material in ("wool", "fleece", "knit"):
            score = 1.0
        elif "winter" in seasons:
            score = 1.0
        elif item_type in ("shorts", "tank-top", "sandals"):
            score = 0.05
        else:
            score = 0.7
    elif temp > hot_threshold:
        if material in ("cotton", "linen", "silk") or "summer" in seasons:
            score = 1.0
        elif item_type in ("outerwear", "sweater", "boots"):
            score = 0.05
        else:
            score = 0.8
    else:
        score = 1.0

    if weather.precipitation_chance > 50 and item_type == "outerwear":
        score = min(1.0, score + 0.1)

    return score


def _formality_score(item: ClothingItem, occasion: str) -> float:
    item_formality = (item.formality or "casual").lower()
    allowed = OCCASION_FORMALITY.get(occasion.lower(), ["casual", "smart-casual"])

    if item_formality in allowed:
        return 1.0

    if item_formality not in FORMALITY_ORDER:
        return 0.5

    item_idx = FORMALITY_ORDER.index(item_formality)
    min_distance = min(
        (abs(item_idx - FORMALITY_ORDER.index(a)) for a in allowed if a in FORMALITY_ORDER),
        default=2,
    )

    if min_distance == 1:
        return 0.5
    return 0.15


def _season_score(item: ClothingItem, current_season: str) -> float:
    seasons = item.season or []
    if not seasons:
        return 1.0
    if current_season in seasons:
        return 1.0

    adjacent = SEASON_ADJACENCY.get(current_season, [])
    if any(s in adjacent for s in seasons):
        return 0.6

    return 0.2


def _recency_score(
    item: ClothingItem,
    user_today: date,
    avoid_days: int,
    worn_dates: dict[UUID, date],
) -> float:
    last_worn = worn_dates.get(item.id)
    if last_worn is None:
        return 1.0

    days_since = (user_today - last_worn).days
    if days_since <= 0:
        return 0.1
    if avoid_days <= 0:
        return 1.0

    return min(1.0, 0.1 + 0.9 * (days_since / avoid_days))


def _preference_score(
    item: ClothingItem,
    preferences: UserPreference | None,
    learned: dict | None,
) -> float:
    score = 1.0
    color = (item.primary_color or "").lower()

    if preferences:
        fav_colors = [c.lower() for c in (preferences.color_favorites or [])]
        avoid_colors = [c.lower() for c in (preferences.color_avoid or [])]

        if color and color in fav_colors:
            score += 0.1
        if color and color in avoid_colors:
            score -= 0.3

    if learned:
        learned_favs = [c.lower() for c in learned.get("learned_favorite_colors", [])]
        learned_avoids = [c.lower() for c in learned.get("learned_avoid_colors", [])]

        if color and color in learned_favs:
            score += 0.05
        if color and color in learned_avoids:
            score -= 0.15

        learned_styles = [s.lower() for s in learned.get("learned_preferred_styles", [])]
        item_styles = [s.lower() for s in (item.style or [])]
        style_bonus = sum(0.03 for s in item_styles if s in learned_styles)
        score += min(0.1, style_bonus)

    return max(0.3, min(1.2, score))


def _usage_score(item: ClothingItem, median_wear: float) -> float:
    wear_count = item.wear_count or 0
    if median_wear <= 1:
        return 1.0
    ratio = wear_count / median_wear
    if ratio <= 0.3:
        return 1.15
    elif ratio <= 0.7:
        return 1.05
    elif ratio <= 1.5:
        return 1.0
    else:
        return 0.9


def _sort_mandatory_first(
    scored: list[ScoredItem],
    mandatory_item_ids: set[UUID] | None,
) -> list[ScoredItem]:
    if not mandatory_item_ids:
        return scored

    return sorted(scored, key=lambda s: s.item.id not in mandatory_item_ids)


def _pair_bonus(
    item: ClothingItem,
    top_items: list[ClothingItem],
    good_pairs: dict[UUID, list[UUID]],
) -> float:
    if not good_pairs:
        return 0.0

    partners = good_pairs.get(item.id, [])
    if not partners:
        return 0.0

    top_ids = {i.id for i in top_items}
    count = sum(1 for p in partners if p in top_ids)
    return min(0.15, count * 0.05)


def score_items(
    items: list[ClothingItem],
    weather: WeatherData,
    occasion: str,
    preferences: UserPreference | None,
    user_today: date,
    current_season: str,
    learned_prefs: dict | None,
    good_pairs: dict[UUID, list[UUID]],
    recently_worn_dates: dict[UUID, date],
    mandatory_item_ids: set[UUID] | None = None,
) -> list[ScoredItem]:
    if len(items) < MIN_ITEMS_FOR_SCORING:
        scored = [ScoredItem(item=item) for item in items]
        return _sort_mandatory_first(scored, mandatory_item_ids)

    avoid_days = 7
    if preferences and preferences.avoid_repeat_days is not None:
        avoid_days = preferences.avoid_repeat_days

    if preferences and preferences.variety_level:
        if preferences.variety_level == "high":
            avoid_days = max(avoid_days, int(avoid_days * 1.5))
        elif preferences.variety_level == "low":
            avoid_days = max(1, int(avoid_days * 0.5))

    use_underused = preferences.prefer_underused_items if preferences else True
    median_wear = median([i.wear_count or 0 for i in items]) if use_underused and items else 0

    scored = []
    for item in items:
        ws = _weather_score(item, weather, preferences)
        fs = _formality_score(item, occasion)
        ss = _season_score(item, current_season)
        rs = _recency_score(item, user_today, avoid_days, recently_worn_dates)
        ps = _preference_score(item, preferences, learned_prefs)
        us = _usage_score(item, median_wear) if use_underused else 1.0

        total = ws * fs * ss * rs * ps * us

        scored.append(
            ScoredItem(
                item=item,
                score=total,
                weather_score=ws,
                formality_score=fs,
                season_score=ss,
                recency_score=rs,
                preference_score=ps,
                usage_score=us,
            )
        )

    scored.sort(key=lambda s: s.score, reverse=True)

    # Compute pair bonus for top 20 only
    top_20_items = [s.item for s in scored[:20]]
    for si in scored[:20]:
        si.pair_bonus = _pair_bonus(si.item, top_20_items, good_pairs)
        si.score += si.pair_bonus

    scored.sort(key=lambda s: s.score, reverse=True)
    scored = _sort_mandatory_first(scored, mandatory_item_ids)
    return scored[:TOP_N]
