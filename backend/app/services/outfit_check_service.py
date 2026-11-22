"""Ask the AI stylist for an opinion on an outfit the user put together in the studio.

The user names the pieces and where they are going; the model rates the look for that
destination and may suggest swapping in, adding or removing pieces. Suggestions can only
point at the outfit's own items or at the user's other wardrobe items, by the numbers the
prompt gives them, so every item a suggestion names is one the user owns.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.ai_service import DESCRIPTION_LANGUAGES, AIService, require_internal_ai
from app.services.item_scorer import get_season, rank_by_fit
from app.services.studio_service import ItemOwnershipError
from app.services.weather_service import WeatherData, WeatherService, WeatherServiceError
from app.utils.ai_json import parse_ai_json
from app.utils.errors import Coded
from app.utils.locale import DEFAULT_LOCALE
from app.utils.prompts import load_prompt, picked_item_ids
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)

OUTFIT_CHECK_PROMPT = load_prompt("outfit_check")
SYSTEM_PROMPT = "You are an honest, encouraging personal stylist. You answer only with JSON."

# The prompt numbers the outfit's own items from 1 and the rest of the wardrobe from this
# offset, so a number alone says which list it came from.
ALTERNATIVE_OFFSET = 101
MAX_ALTERNATIVES = 60
MAX_SUGGESTIONS = 6
MAX_POINTS = 5

Action = Literal["replace", "add", "remove", "styling_tip"]


class OutfitCheckError(Coded, RuntimeError):
    code = "AI_SERVICE_UNAVAILABLE"


@dataclass
class Suggestion:
    action: Action
    title: str
    description: str
    reason: str
    target: ClothingItem | None = None
    replacement: ClothingItem | None = None


@dataclass
class OutfitCheck:
    rating: int
    verdict: str
    opinion: str
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)


def _item_line(number: int, item: ClothingItem) -> str:
    parts = [f'"{item.name}"'] if item.name else []
    parts.append(f"{item.subtype} ({item.type})" if item.subtype else item.type)
    colors = item.colors or ([item.primary_color] if item.primary_color else [])
    if colors:
        parts.append(f"colors: {', '.join(colors)}")
    if item.pattern and item.pattern != "solid":
        parts.append(item.pattern)
    if item.material:
        parts.append(item.material)
    if item.formality:
        parts.append(item.formality)
    if item.style:
        parts.append(f"style: {', '.join(item.style)}")
    fit = (item.tags or {}).get("fit")
    if isinstance(fit, str) and fit:
        parts.append(f"{fit} fit")
    return f"[{number}] {' | '.join(parts)}"


def _weather_line(weather: WeatherData | None) -> str:
    if weather is None:
        return "unknown"
    return (
        f"{weather.temperature:.0f}°C (feels like {weather.feels_like:.0f}°C), "
        f"{weather.condition}, {weather.precipitation_chance}% chance of rain"
    )


def _preference_lines(user: User) -> str:
    prefs = user.preferences
    if not prefs:
        return "none given"
    lines = []
    if prefs.color_favorites:
        lines.append(f"favorite colors: {', '.join(prefs.color_favorites)}")
    if prefs.color_avoid:
        lines.append(f"colors to avoid: {', '.join(prefs.color_avoid)}")
    strong = [
        style
        for style, weight in (prefs.style_profile or {}).items()
        if isinstance(weight, int | float) and weight >= 60
    ]
    if strong:
        lines.append(f"preferred styles: {', '.join(strong)}")
    return "; ".join(lines) or "none given"


def _text(value: object, limit: int = 1500) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _points(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (_text(v, 300) for v in value) if text][:MAX_POINTS]


def _rating(value: object) -> int:
    # Models answer 8, "8", "8/10" or 8.5; anything unreadable sits in the middle.
    match = re.search(r"\d+(\.\d+)?", str(value)) if not isinstance(value, bool) else None
    rating = round(float(match.group())) if match else 5
    return max(1, min(10, rating))


def _one(number: object, items: dict[int, ClothingItem]) -> ClothingItem | None:
    ids = {n: item.id for n, item in items.items()}
    picked = picked_item_ids([number], ids) if number is not None else []
    by_id = {item.id: item for item in items.values()}
    return by_id[picked[0]] if picked else None


def _suggestion(
    raw: object,
    outfit: dict[int, ClothingItem],
    alternatives: dict[int, ClothingItem],
) -> Suggestion | None:
    if not isinstance(raw, dict):
        return None
    title = _text(raw.get("title"), 120)
    description = _text(raw.get("description"), 600)
    if not title and not description:
        return None
    action = raw.get("action")
    target = _one(raw.get("target_item_num"), outfit)
    replacement = _one(raw.get("replacement_item_num"), alternatives)
    # A suggestion keeps its action only when it names the items that action needs, so the
    # client can apply every replace, add or remove it is given.
    if action == "replace" and not replacement:
        action = "styling_tip"
    elif action == "add" and not replacement:
        action = "styling_tip"
    elif action == "remove" and not target:
        action = "styling_tip"
    elif action not in ("replace", "add", "remove"):
        action = "styling_tip"
    if action == "styling_tip":
        target = replacement = None
    if action == "add":
        target = None
    if action == "remove":
        replacement = None
    return Suggestion(
        action=action,
        title=title or description[:120],
        description=description,
        reason=_text(raw.get("reason"), 400),
        target=target,
        replacement=replacement,
    )


def parse_check(
    content: str,
    outfit: dict[int, ClothingItem],
    alternatives: dict[int, ClothingItem],
) -> OutfitCheck:
    try:
        data = parse_ai_json(content)
    except ValueError as e:
        raise OutfitCheckError(
            "The AI stylist's answer could not be read", code="AI_RESPONSE_UNUSABLE"
        ) from e
    if not isinstance(data, dict):
        raise OutfitCheckError(
            "The AI stylist's answer could not be read", code="AI_RESPONSE_UNUSABLE"
        )
    raw_suggestions = data.get("suggestions")
    suggestions = [
        s
        for s in (
            _suggestion(raw, outfit, alternatives)
            for raw in (raw_suggestions if isinstance(raw_suggestions, list) else [])
        )
        if s
    ][:MAX_SUGGESTIONS]
    return OutfitCheck(
        rating=_rating(data.get("rating")),
        verdict=_text(data.get("verdict"), 80),
        opinion=_text(data.get("opinion"), 3000),
        strengths=_points(data.get("strengths")),
        improvements=_points(data.get("improvements")),
        suggestions=suggestions,
    )


class OutfitCheckService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.weather_service = WeatherService()

    async def _weather(self, user: User) -> WeatherData | None:
        # Weather sharpens the advice but is not needed for it, so a missing location or a
        # weather outage leaves it out rather than failing the check.
        lat = float(user.location_lat) if user.location_lat is not None else None
        lon = float(user.location_lon) if user.location_lon is not None else None
        try:
            if (lat is None or lon is None) and user.location_name:
                geocoded = await self.weather_service.geocode_location_name(user.location_name)
                if geocoded:
                    lat, lon, _ = geocoded
            if lat is None or lon is None:
                return None
            return await self.weather_service.get_current_weather(lat, lon)
        except WeatherServiceError as e:
            logger.info("outfit check without weather: %s", e)
            return None

    async def _outfit_items(self, user: User, item_ids: list[UUID]) -> list[ClothingItem]:
        result = await self.db.execute(
            select(ClothingItem).where(
                ClothingItem.user_id == user.id, ClothingItem.id.in_(item_ids)
            )
        )
        by_id = {item.id: item for item in result.scalars().all()}
        if len(by_id) != len(set(item_ids)):
            raise ItemOwnershipError("One or more items do not belong to you")
        return [by_id[item_id] for item_id in dict.fromkeys(item_ids)]

    async def _alternatives(
        self,
        user: User,
        exclude: list[UUID],
        weather: WeatherData | None,
        occasion: str,
    ) -> list[ClothingItem]:
        result = await self.db.execute(
            select(ClothingItem).where(
                ClothingItem.user_id == user.id,
                ClothingItem.status == ItemStatus.ready,
                ClothingItem.is_archived.is_(False),
                ClothingItem.needs_wash.is_(False),
                ClothingItem.id.not_in(exclude),
            )
        )
        items = list(result.scalars().all())
        if weather is not None:
            season = get_season(
                get_user_today(user).month,
                float(user.location_lat) if user.location_lat is not None else None,
            )
            order = rank_by_fit(items, weather, occasion, season, user.preferences, None)
            by_id = {item.id: item for item in items}
            items = [by_id[item_id] for item_id in order]
        else:
            items.sort(key=lambda i: (not i.favorite, -(i.wear_count or 0)))
        return items[:MAX_ALTERNATIVES]

    async def check(
        self,
        user: User,
        item_ids: list[UUID],
        destination: str,
        occasion: str,
    ) -> OutfitCheck:
        require_internal_ai("text")

        outfit_items = await self._outfit_items(user, item_ids)
        weather = await self._weather(user)
        alternative_items = await self._alternatives(user, item_ids, weather, occasion)

        outfit = dict(enumerate(outfit_items, start=1))
        alternatives = dict(enumerate(alternative_items, start=ALTERNATIVE_OFFSET))
        prompt = OUTFIT_CHECK_PROMPT.format(
            destination=destination,
            occasion=occasion,
            weather=_weather_line(weather),
            preferences=_preference_lines(user),
            language=DESCRIPTION_LANGUAGES.get(user.locale, DESCRIPTION_LANGUAGES[DEFAULT_LOCALE]),
            outfit_items="\n".join(_item_line(n, i) for n, i in outfit.items()),
            alternative_items="\n".join(_item_line(n, i) for n, i in alternatives.items())
            or "none",
        )

        prefs = user.preferences
        ai = AIService(endpoints=prefs.ai_endpoints if prefs and prefs.ai_endpoints else None)
        try:
            content = await ai.generate_text(prompt=prompt, system_prompt=SYSTEM_PROMPT)
        except httpx.HTTPError as e:
            # The client's own failures (an empty, truncated or provider-error reply) are coded
            # RuntimeErrors and pass through; a transport error is given a code here.
            logger.warning("outfit check AI call failed: %s", e)
            raise OutfitCheckError("The AI stylist is unavailable right now") from e
        return parse_check(content, outfit, alternatives)
