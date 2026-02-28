import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem, ItemHistory, ItemStatus
from app.models.learning import ItemPairScore, UserLearningProfile
from app.models.outfit import (
    FamilyOutfitRating,
    Outfit,
    OutfitItem,
    OutfitSource,
    OutfitStatus,
    UserFeedback,
)
from app.models.preference import UserPreference
from app.models.user import User
from app.services.ai_service import AIService
from app.services.weather_service import WeatherData, WeatherService, WeatherServiceError
from app.utils.prompts import load_prompt

logger = logging.getLogger(__name__)


def get_user_today(user: User) -> date:
    try:
        user_tz = ZoneInfo(user.timezone or "UTC")
    except Exception:
        user_tz = ZoneInfo("UTC")
    return datetime.now(UTC).astimezone(user_tz).date()


@dataclass
class RecommendationContext:
    user: User
    preferences: UserPreference | None
    weather: WeatherData
    occasion: str
    exclude_items: list[UUID]
    include_items: list[UUID]


# Formality mapping for occasions
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

# Season mapping based on month
MONTH_TO_SEASON = {
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

RECOMMENDATION_PROMPT = load_prompt("recommendation")


class RecommendationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.weather_service = WeatherService()

    async def get_candidate_items(
        self,
        user: User,
        weather: WeatherData,
        occasion: str,
        preferences: UserPreference | None,
        exclude_items: list[UUID],
    ) -> list[ClothingItem]:
        # Get all ready, non-archived items
        query = select(ClothingItem).where(
            and_(
                ClothingItem.user_id == user.id,
                ClothingItem.status == ItemStatus.ready,
                ClothingItem.is_archived.is_(False),
            )
        )

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        if not items:
            return []

        # Exclude items that need washing
        items = [i for i in items if not i.needs_wash]

        # Only exclude explicitly excluded items (user request or preferences)
        if exclude_items:
            exclude_set = set(exclude_items)
            items = [i for i in items if i.id not in exclude_set]

        if preferences and preferences.excluded_item_ids:
            excluded = set(preferences.excluded_item_ids)
            items = [i for i in items if i.id not in excluded]

        # Exclude recently worn items (user preference)
        if preferences and preferences.avoid_repeat_days:
            items = await self._exclude_recently_worn(items, user, preferences.avoid_repeat_days)

        return items

    def _filter_by_season(self, items: list[ClothingItem], user: User) -> list[ClothingItem]:
        user_today = get_user_today(user)
        current_season = MONTH_TO_SEASON[user_today.month]

        filtered = []
        for item in items:
            seasons = item.season or []
            # Include if no season specified (all-season) or matches current
            if not seasons or current_season in seasons:
                filtered.append(item)

        return filtered

    def _filter_by_weather(
        self,
        items: list[ClothingItem],
        weather: WeatherData,
        preferences: UserPreference | None,
    ) -> list[ClothingItem]:
        temp = weather.temperature

        # Get thresholds from preferences or use defaults
        cold_threshold = 10
        hot_threshold = 25

        if preferences:
            if preferences.cold_threshold is not None:
                cold_threshold = preferences.cold_threshold
            if preferences.hot_threshold is not None:
                hot_threshold = preferences.hot_threshold

            # Adjust for sensitivity
            if preferences.temperature_sensitivity == "cold":
                cold_threshold += 5  # Feel cold earlier
            elif preferences.temperature_sensitivity == "warm":
                hot_threshold -= 5  # Feel warm earlier

        filtered = []
        for item in items:
            item_type = item.type.lower() if item.type else ""
            material = (item.material or "").lower()
            seasons = item.season or []

            if temp < cold_threshold:
                # Cold weather: need warm items
                if item_type in ["outerwear", "sweater"]:
                    filtered.append(item)
                elif "winter" in seasons:
                    filtered.append(item)
                elif material in ["wool", "fleece", "knit"]:
                    filtered.append(item)
                elif item_type not in ["shorts", "tank-top", "sandals"]:
                    filtered.append(item)
            elif temp > hot_threshold:
                # Hot weather: need light items
                if "summer" in seasons:
                    filtered.append(item)
                elif material in ["cotton", "linen", "silk"]:
                    filtered.append(item)
                elif item_type not in ["outerwear", "sweater", "boots"]:
                    filtered.append(item)
            else:
                # Moderate weather: most items okay
                filtered.append(item)

        return filtered

    def _filter_by_formality(self, items: list[ClothingItem], occasion: str) -> list[ClothingItem]:
        allowed_formality = OCCASION_FORMALITY.get(occasion.lower(), ["casual", "smart-casual"])

        filtered = []
        for item in items:
            item_formality = (item.formality or "casual").lower()
            if item_formality in allowed_formality:
                filtered.append(item)

        return filtered

    async def _exclude_recently_worn(
        self, items: list[ClothingItem], user: User, avoid_days: int
    ) -> list[ClothingItem]:
        if avoid_days <= 0:
            return items

        # Use user's current date for the cutoff
        user_today = get_user_today(user)
        cutoff_date = user_today - timedelta(days=avoid_days)

        # Get recently worn item IDs
        query = (
            select(ItemHistory.item_id)
            .join(ClothingItem)
            .where(
                and_(
                    ClothingItem.user_id == user.id,
                    ItemHistory.worn_at >= cutoff_date,
                )
            )
            .distinct()
        )

        result = await self.db.execute(query)
        recently_worn = set(result.scalars().all())

        return [i for i in items if i.id not in recently_worn]

    async def _get_recently_worn_outfit_combinations(
        self, user: User, days: int = 7
    ) -> set[frozenset[UUID]]:
        if days <= 0:
            return set()

        user_today = get_user_today(user)
        cutoff_date = user_today - timedelta(days=days)

        # Get outfits that were marked as worn in the cutoff period
        query = (
            select(Outfit)
            .join(UserFeedback, Outfit.id == UserFeedback.outfit_id)
            .where(
                and_(
                    Outfit.user_id == user.id,
                    UserFeedback.worn_at >= cutoff_date,
                )
            )
            .options(selectinload(Outfit.items))
        )

        result = await self.db.execute(query)
        worn_outfits = list(result.scalars().all())

        # Build set of item combinations
        combinations = set()
        for outfit in worn_outfits:
            item_ids = frozenset(outfit_item.item_id for outfit_item in outfit.items)
            if len(item_ids) >= 2:  # Only track if it's a real outfit
                combinations.add(item_ids)

        logger.info(f"Found {len(combinations)} worn outfit combinations in last {days} days")
        return combinations

    def _format_items_for_prompt(self, items: list[ClothingItem]) -> tuple[str, dict[int, UUID]]:
        lines = []
        number_map: dict[int, UUID] = {}

        for i, item in enumerate(items, 1):
            number_map[i] = item.id

            # Build detailed item description
            parts = []

            # Type and subtype
            item_type = item.type or "item"
            if item.subtype:
                parts.append(f"{item.subtype} ({item_type})")
            else:
                parts.append(item_type)

            # Colors
            if item.colors and len(item.colors) > 1:
                parts.append(f"colors: {', '.join(item.colors)}")
            elif item.primary_color:
                parts.append(item.primary_color)

            # Pattern
            if item.pattern and item.pattern != "solid":
                parts.append(item.pattern)

            # Material
            if item.material:
                parts.append(item.material)

            # Formality
            if item.formality:
                parts.append(item.formality)

            # Style tags
            if item.style:
                parts.append(f"style: {', '.join(item.style)}")

            # Name if set
            if item.name:
                parts.insert(0, f'"{item.name}"')

            line = f"[{i}] {' | '.join(parts)}"
            lines.append(line)

        return "\n".join(lines), number_map

    def _format_preferences_for_prompt(
        self,
        preferences: UserPreference | None,
        learned_prefs: dict | None = None,
        worn_combinations: set[frozenset[UUID]] | None = None,
        number_map: dict[int, UUID] | None = None,
    ) -> str:
        lines = []

        # Explicit user preferences
        if preferences:
            if preferences.color_favorites:
                lines.append(f"- Favorite colors: {', '.join(preferences.color_favorites)}")
            if preferences.color_avoid:
                lines.append(f"- Colors to avoid: {', '.join(preferences.color_avoid)}")
            if preferences.variety_level:
                lines.append(f"- Variety preference: {preferences.variety_level}")

        # Learned preferences (from feedback history)
        if learned_prefs:
            if learned_prefs.get("learned_favorite_colors"):
                colors = learned_prefs["learned_favorite_colors"]
                lines.append(f"- Learned favorite colors (from feedback): {', '.join(colors)}")
            if learned_prefs.get("learned_avoid_colors"):
                colors = learned_prefs["learned_avoid_colors"]
                lines.append(f"- Learned colors to avoid (from feedback): {', '.join(colors)}")
            if learned_prefs.get("learned_preferred_styles"):
                styles = learned_prefs["learned_preferred_styles"]
                lines.append(f"- Learned preferred styles: {', '.join(styles)}")

        # Recently worn outfit combinations to deprioritize
        if worn_combinations and number_map:
            # Map UUIDs back to item numbers
            uuid_to_number = {uuid: num for num, uuid in number_map.items()}
            worn_sets = []
            for combo in worn_combinations:
                numbers = sorted([uuid_to_number[uuid] for uuid in combo if uuid in uuid_to_number])
                if numbers:
                    worn_sets.append("[" + ", ".join(map(str, numbers)) + "]")
            if worn_sets:
                lines.append(
                    f"- Recently worn outfits (prefer variety, only repeat if necessary): {', '.join(worn_sets)}"
                )

        if lines:
            return "\nUSER PREFERENCES:\n" + "\n".join(lines)
        return ""

    async def _get_learned_preferences(self, user_id: UUID) -> dict:
        result = await self.db.execute(
            select(UserLearningProfile).where(UserLearningProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()

        if not profile or not profile.last_computed_at:
            return {}

        preferences = {}

        # Top liked colors
        if profile.learned_color_scores:
            liked_colors = sorted(
                [(c, s) for c, s in profile.learned_color_scores.items() if s > 0.2],
                key=lambda x: x[1],
                reverse=True,
            )[:5]
            disliked_colors = sorted(
                [(c, s) for c, s in profile.learned_color_scores.items() if s < -0.2],
                key=lambda x: x[1],
            )[:3]

            if liked_colors:
                preferences["learned_favorite_colors"] = [c for c, _ in liked_colors]
            if disliked_colors:
                preferences["learned_avoid_colors"] = [c for c, _ in disliked_colors]

        # Top liked styles
        if profile.learned_style_scores:
            liked_styles = sorted(
                [(s, score) for s, score in profile.learned_style_scores.items() if score > 0.2],
                key=lambda x: x[1],
                reverse=True,
            )[:3]
            if liked_styles:
                preferences["learned_preferred_styles"] = [s for s, _ in liked_styles]

        return preferences

    async def _get_good_item_pairs(self, user_id: UUID) -> dict[UUID, list[UUID]]:
        result = await self.db.execute(
            select(ItemPairScore)
            .where(
                and_(
                    ItemPairScore.user_id == user_id,
                    ItemPairScore.compatibility_score > 0.3,
                    ItemPairScore.times_paired >= 2,
                )
            )
            .order_by(ItemPairScore.compatibility_score.desc())
            .limit(50)
        )
        pairs = list(result.scalars().all())

        # Build adjacency list of good pairs
        good_pairs: dict[UUID, list[UUID]] = {}
        for pair in pairs:
            if pair.item1_id not in good_pairs:
                good_pairs[pair.item1_id] = []
            good_pairs[pair.item1_id].append(pair.item2_id)

            if pair.item2_id not in good_pairs:
                good_pairs[pair.item2_id] = []
            good_pairs[pair.item2_id].append(pair.item1_id)

        return good_pairs

    def _parse_ai_response(self, content: str) -> dict:
        def strip_comments(json_str: str) -> str:
            # Remove single-line comments (// ...)
            json_str = re.sub(r"//[^\n]*", "", json_str)
            # Remove multi-line comments (/* ... */)
            json_str = re.sub(r"/\*[\s\S]*?\*/", "", json_str)
            return json_str

        # Try direct JSON parse
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass

        # Try with comments stripped
        try:
            return json.loads(strip_comments(content.strip()))
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if json_match:
            extracted = json_match.group(1)
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass
            # Try with comments stripped
            try:
                return json.loads(strip_comments(extracted))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object with balanced braces
        start_idx = content.find("{")
        if start_idx != -1:
            brace_count = 0
            for i, char in enumerate(content[start_idx:], start_idx):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = content[start_idx : i + 1]
                        try:
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            pass
                        # Try with comments stripped
                        try:
                            return json.loads(strip_comments(json_str))
                        except json.JSONDecodeError:
                            break

        # Try finding JSON array with balanced brackets (small models sometimes return arrays)
        start_idx = content.find("[")
        if start_idx != -1:
            bracket_count = 0
            for i, char in enumerate(content[start_idx:], start_idx):
                if char == "[":
                    bracket_count += 1
                elif char == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        json_str = content[start_idx : i + 1]
                        try:
                            result = json.loads(json_str)
                            # If it's an array of dicts, return the first one
                            if isinstance(result, list) and len(result) > 0:
                                if isinstance(result[0], dict):
                                    return result[0]
                                # If it's an array of numbers (item IDs), wrap it
                                return {"items": result}
                            return result
                        except json.JSONDecodeError:
                            break

        raise ValueError(f"Could not parse AI response as JSON: {content[:200]}")

    async def generate_recommendation(
        self,
        user: User,
        occasion: str,
        weather_override: WeatherData | None = None,
        exclude_items: list[UUID] | None = None,
        include_items: list[UUID] | None = None,
        source: OutfitSource = OutfitSource.on_demand,
    ) -> Outfit:
        exclude_items = exclude_items or []
        include_items = include_items or []

        # Get weather
        if weather_override:
            weather = weather_override
        else:
            if user.location_lat is None or user.location_lon is None:
                raise ValueError("User location not set. Please set location in settings.")
            try:
                weather = await self.weather_service.get_current_weather(
                    float(user.location_lat), float(user.location_lon)
                )
            except WeatherServiceError as e:
                logger.error(f"Weather service failed: {e}")
                raise ValueError(
                    "Could not fetch weather data. Please try again or provide weather manually."
                ) from e

        # Get preferences
        preferences = user.preferences

        # Create AI service with user's configured endpoints
        ai_endpoints = None
        if preferences and preferences.ai_endpoints:
            ai_endpoints = preferences.ai_endpoints
        ai_service = AIService(endpoints=ai_endpoints)

        # Get candidate items
        candidates = await self.get_candidate_items(
            user=user,
            weather=weather,
            occasion=occasion,
            preferences=preferences,
            exclude_items=exclude_items,
        )

        # Force-include specific items if requested (fetch and add to candidates)
        if include_items:
            include_set = set(include_items)
            existing_ids = {item.id for item in candidates}
            missing_ids = include_set - existing_ids

            if missing_ids:
                # Fetch the missing items from database
                result = await self.db.execute(
                    select(ClothingItem).where(
                        and_(
                            ClothingItem.id.in_(missing_ids),
                            ClothingItem.user_id == user.id,
                            ClothingItem.status == ItemStatus.ready,
                            ClothingItem.is_archived.is_(False),
                        )
                    )
                )
                forced_items = list(result.scalars().all())
                candidates.extend(forced_items)
                logger.info(f"Force-included {len(forced_items)} items in recommendation")

        if len(candidates) < 2:
            raise InsufficientWardrobeError(
                "Not enough items in wardrobe for recommendation. "
                "Please add more items or adjust filters."
            )

        # Get learned preferences from feedback history
        learned_prefs = await self._get_learned_preferences(user.id)
        if learned_prefs:
            logger.info(
                f"Using learned preferences for user {user.id}: {list(learned_prefs.keys())}"
            )

        # Build prompt with numbered items
        items_text, number_map = self._format_items_for_prompt(candidates)

        # Get recently worn outfit combinations to deprioritize
        worn_combinations = await self._get_recently_worn_outfit_combinations(user, days=7)

        preferences_text = self._format_preferences_for_prompt(
            preferences, learned_prefs, worn_combinations, number_map
        )

        prompt = RECOMMENDATION_PROMPT.format(
            occasion=occasion,
            temperature=weather.temperature,
            feels_like=weather.feels_like,
            condition=weather.condition,
            precipitation_chance=weather.precipitation_chance,
            preferences_text=preferences_text,
            items_text=items_text,
        )

        # Generate recommendation using AI
        logger.info(
            f"Generating recommendation for user {user.id}, occasion: {occasion}, items: {len(candidates)}"
        )

        try:
            result = await ai_service.generate_text(prompt, return_metadata=True)
            logger.info(
                f"AI recommendation generated (model: {result.model}, endpoint: {result.endpoint})"
            )
            logger.debug(f"AI raw response: {result.content[:500]}")
            outfit_data = self._parse_ai_response(result.content)
            # Handle case where AI returns a list instead of object
            if isinstance(outfit_data, list) and len(outfit_data) > 0:
                outfit_data = outfit_data[0]
            if not isinstance(outfit_data, dict):
                raise ValueError(f"Expected dict, got {type(outfit_data)}")
            # Add model info to outfit data for storage
            outfit_data["_ai_model"] = result.model
            outfit_data["_ai_endpoint"] = result.endpoint
        except Exception as e:
            logger.error(f"AI recommendation failed: {e}")
            raise AIRecommendationError(
                "AI service is not available. Please check your AI endpoint configuration in Settings."
            ) from e

        # Convert item numbers back to UUIDs
        selected_numbers = outfit_data.get("items", [])
        valid_ids = []

        for num in selected_numbers:
            # Handle both int and string numbers
            try:
                num_int = int(num)
                if num_int in number_map:
                    valid_ids.append(number_map[num_int])
                else:
                    logger.warning(f"AI selected invalid item number: {num}")
            except (ValueError, TypeError):
                logger.warning(f"AI returned non-numeric item: {num}")

        if not valid_ids:
            raise AIRecommendationError("AI did not select any valid items")

        # Create outfit record
        # Map structured AI response:
        # - headline → reasoning (for backwards compat with notifications)
        # - highlights → stored in ai_raw_response
        # - styling_tip → style_notes
        reasoning = outfit_data.get("headline") or outfit_data.get("reasoning")
        style_notes = outfit_data.get("styling_tip") or outfit_data.get("style_notes")

        outfit = Outfit(
            user_id=user.id,
            occasion=occasion,
            weather_data=weather.to_dict(),
            scheduled_for=get_user_today(user),
            reasoning=reasoning,
            style_notes=style_notes,
            ai_raw_response=outfit_data,
            source=source,
            status=OutfitStatus.pending,
        )

        self.db.add(outfit)
        await self.db.flush()  # Get the outfit ID

        # Add outfit items
        layers = outfit_data.get("layers", {})
        for position, item_id in enumerate(valid_ids):
            # Determine layer type
            layer_type = None
            for layer_name, layer_id in layers.items():
                if layer_id == str(item_id):
                    layer_type = layer_name
                    break

            outfit_item = OutfitItem(
                outfit_id=outfit.id,
                item_id=item_id,
                position=position,
                layer_type=layer_type,
            )
            self.db.add(outfit_item)

        await self.db.commit()
        await self.db.refresh(outfit)

        # Load relationships for response
        result = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == outfit.id)
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
                selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
            )
        )
        outfit = result.scalar_one()

        logger.info(f"Created outfit {outfit.id} with {len(valid_ids)} items")

        return outfit


class InsufficientWardrobeError(Exception):
    pass


class AIRecommendationError(Exception):
    pass
