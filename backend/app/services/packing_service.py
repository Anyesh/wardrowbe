"""Packing list for a trip: how many of each garment the weather and length call for, filled
from the user's own wardrobe with the same weather, season and formality scores the outfit
recommender uses."""

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem, ItemStatus
from app.models.preference import UserPreference
from app.models.user import User
from app.services.item_scorer import (
    HEAVY_LAYER_TYPES,
    RAIN_LAYER_TYPES,
    _formality_score,
    _is_heavy_layer,
    _resolve_temp_thresholds,
    _season_score,
    _weather_score,
    get_season,
)
from app.services.weather_service import DailyForecast, WeatherData
from app.utils.garment_vocabulary import ITEM_ROLE

MAX_TRIP_DAYS = 30
FORECAST_HORIZON_DAYS = 16
RAIN_DAY_CHANCE = 50
# Below this score an item is wrong for the trip (shorts in the snow), so it is never packed
# just to reach a count.
MIN_PACKING_SCORE = 0.2

# Rough day/night ranges when the trip is beyond the forecast horizon.
SEASON_TEMPERATURES: dict[str, tuple[float, float]] = {
    "winter": (1.0, 9.0),
    "spring": (9.0, 19.0),
    "summer": (19.0, 30.0),
    "fall": (8.0, 17.0),
}

ROLE_ORDER = (
    "outer_layer",
    "mid_layer",
    "base_top",
    "full_body",
    "bottom",
    "footwear",
    "accessory",
)
COLD_ACCESSORY_TYPES = {"scarf", "hat"}
# Nice to have, not a gap: a wardrobe without dresses or scarves is not missing anything.
OPTIONAL_ROLES = {"mid_layer", "full_body", "accessory"}
# WMO codes for drizzle, rain, showers and thunderstorms: a day forecast as rain counts as rainy
# even when the reported chance is at or under RAIN_DAY_CHANCE.
WET_CODES = set(range(51, 68)) | {80, 81, 82, 95, 96, 99}


@dataclass
class TripWeather:
    temp_min: float
    temp_max: float
    rain_days: int
    estimated: bool
    days: list[DailyForecast] = field(default_factory=list)


@dataclass
class PackingGroup:
    role: str
    needed: int
    items: list[ClothingItem]


def trip_length(start: date, end: date) -> int:
    return (end - start).days + 1


def is_wet(day: DailyForecast) -> bool:
    return day.precipitation_chance > RAIN_DAY_CHANCE or day.condition_code in WET_CODES


def summarize_forecast(
    forecast: list[DailyForecast], start: date, end: date, season: str
) -> TripWeather:
    """Trip-wide extremes from the forecast days inside the trip, or a seasonal estimate when
    the trip lies beyond the forecast horizon."""
    in_trip = [d for d in forecast if start.isoformat() <= d.date <= end.isoformat()]
    if not in_trip:
        low, high = SEASON_TEMPERATURES[season]
        return TripWeather(temp_min=low, temp_max=high, rain_days=0, estimated=True)
    return TripWeather(
        temp_min=min(d.temp_min for d in in_trip),
        temp_max=max(d.temp_max for d in in_trip),
        rain_days=sum(1 for d in in_trip if is_wet(d)),
        estimated=False,
        days=in_trip,
    )


def plan_quantities(
    days: int, weather: TripWeather, laundry: bool, preferences: UserPreference | None
) -> dict[str, int]:
    """Pieces per role. With laundry available a few days' worth is enough."""
    cold_threshold, hot_threshold = _resolve_temp_thresholds(preferences)
    cycle = min(days, 4) if laundry else days
    tops = max(1, min(cycle, 10))
    cold = weather.temp_min < cold_threshold
    cool_evenings = weather.temp_min < cold_threshold + 6
    hot = weather.temp_min > hot_threshold - 4

    plan = {
        "base_top": tops,
        "bottom": max(1, math.ceil(tops / 3)),
        "full_body": 1 if days >= 3 else 0,
        "footwear": 2 if days > 3 or weather.rain_days > 0 else 1,
        "mid_layer": 1 if cool_evenings else 0,
        "outer_layer": 1 if (cool_evenings or weather.rain_days > 0) and not hot else 0,
        "accessory": 2 if cold else 0,
    }
    return plan


def trip_weather_data(weather: TripWeather) -> WeatherData:
    middle = (weather.temp_min + weather.temp_max) / 2
    return WeatherData(
        temperature=middle,
        feels_like=middle,
        humidity=60,
        precipitation_chance=70 if weather.rain_days else 0,
        precipitation_mm=0.0,
        wind_speed=0.0,
        condition="rainy" if weather.rain_days else "mixed",
        condition_code=61 if weather.rain_days else 2,
        is_day=True,
        uv_index=0.0,
        timestamp=datetime.now(UTC),
        temp_min=weather.temp_min,
        temp_max=weather.temp_max,
        window_min=weather.temp_min,
        window_max=weather.temp_max,
    )


def packing_score(
    item: ClothingItem,
    weather: TripWeather,
    season: str,
    occasion: str,
    preferences: UserPreference | None,
) -> float:
    data = trip_weather_data(weather)
    score = (
        _weather_score(item, data, preferences)
        * _season_score(item, season, data, preferences)
        * _formality_score(item, occasion)
    )
    item_type = (item.type or "").lower()
    if ITEM_ROLE.get(item_type) == "outer_layer":
        cold_threshold, _ = _resolve_temp_thresholds(preferences)
        heavy = _is_heavy_layer(
            item_type, (item.material or "").lower(), (item.subtype or "").lower()
        )
        if weather.temp_min < cold_threshold:
            score *= 1.3 if heavy or item_type in HEAVY_LAYER_TYPES else 0.8
        elif weather.rain_days and item_type in RAIN_LAYER_TYPES:
            score *= 1.15
    if ITEM_ROLE.get(item_type) == "accessory" and item_type not in COLD_ACCESSORY_TYPES:
        score *= 0.3
    if item.favorite:
        score *= 1.1
    return score


def choose_items(
    items: list[ClothingItem],
    plan: dict[str, int],
    weather: TripWeather,
    season: str,
    occasion: str,
    preferences: UserPreference | None,
) -> list[PackingGroup]:
    by_role: dict[str, list[tuple[float, ClothingItem]]] = {role: [] for role in ROLE_ORDER}
    for item in items:
        role = ITEM_ROLE.get((item.type or "").lower())
        if role not in by_role:
            continue
        score = packing_score(item, weather, season, occasion, preferences)
        if score >= MIN_PACKING_SCORE:
            by_role[role].append((score, item))

    groups = []
    for role in ROLE_ORDER:
        needed = plan.get(role, 0)
        if needed <= 0:
            continue
        ranked = sorted(by_role[role], key=lambda pair: pair[0], reverse=True)
        if not ranked and role in OPTIONAL_ROLES:
            continue
        groups.append(PackingGroup(role=role, needed=needed, items=[i for _, i in ranked[:needed]]))
    return groups


class PackingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def wardrobe(self, user: User) -> list[ClothingItem]:
        result = await self.db.execute(
            select(ClothingItem)
            .where(
                and_(
                    ClothingItem.user_id == user.id,
                    ClothingItem.status == ItemStatus.ready,
                    ClothingItem.is_archived.is_(False),
                )
            )
            .options(selectinload(ClothingItem.additional_images))
        )
        return [i for i in result.scalars().all() if i.type and i.type != "unknown"]

    async def preferences(self, user: User) -> UserPreference | None:
        return await self.db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))

    async def plan(
        self,
        user: User,
        start: date,
        end: date,
        latitude: float,
        forecast: list[DailyForecast],
        occasion: str,
        laundry: bool,
    ) -> tuple[TripWeather, str, list[PackingGroup]]:
        season = get_season(start.month, latitude)
        weather = summarize_forecast(forecast, start, end, season)
        preferences = await self.preferences(user)
        quantities = plan_quantities(trip_length(start, end), weather, laundry, preferences)
        groups = choose_items(
            await self.wardrobe(user), quantities, weather, season, occasion, preferences
        )
        return weather, season, groups
