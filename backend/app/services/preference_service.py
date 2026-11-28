import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.preference import UserPreference
from app.schemas.preference import PreferenceUpdate, StyleProfile
from app.utils.garment_vocabulary import color_family
from app.utils.preference_defaults import (
    DEFAULT_LAYERING_PREFERENCE,
    DEFAULT_OCCASION,
    DEFAULT_PREFER_UNDERUSED_ITEMS,
    DEFAULT_TEMPERATURE_SENSITIVITY,
    DEFAULT_TEMPERATURE_UNIT,
    DEFAULT_VARIETY_LEVEL,
)
from app.utils.scales import (
    DEFAULT_AVOID_REPEAT_DAYS,
    DEFAULT_COLD_THRESHOLD,
    DEFAULT_HOT_THRESHOLD,
)


# Scoring matches a colour by its name or its family, so a favourite and an avoided colour that
# share a family ("navy" and "blues") would pull the same items both ways. The newly chosen list
# wins and the other one drops every colour that overlaps it.
def _color_keys(name: str) -> set[str]:
    family = color_family(name)
    return {name.lower(), family} if family else {name.lower()}


def _without_overlaps(colors: list[str], winners: list[str]) -> list[str]:
    taken = set().union(*(_color_keys(c) for c in winners))
    return [c for c in colors if not _color_keys(c) & taken]


class PreferenceService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_preferences(self, user_id: uuid.UUID) -> UserPreference | None:
        result = await self.db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_preferences(self, user_id: uuid.UUID) -> UserPreference:
        preferences = await self.get_preferences(user_id)
        if preferences:
            return preferences

        # Create default preferences
        preferences = UserPreference(
            user_id=user_id,
            color_favorites=[],
            color_avoid=[],
            style_profile=StyleProfile().model_dump(),
            default_occasion=DEFAULT_OCCASION,
            temperature_unit=DEFAULT_TEMPERATURE_UNIT,
            temperature_sensitivity=DEFAULT_TEMPERATURE_SENSITIVITY,
            cold_threshold=DEFAULT_COLD_THRESHOLD,
            hot_threshold=DEFAULT_HOT_THRESHOLD,
            layering_preference=DEFAULT_LAYERING_PREFERENCE,
            avoid_repeat_days=DEFAULT_AVOID_REPEAT_DAYS,
            prefer_underused_items=DEFAULT_PREFER_UNDERUSED_ITEMS,
            variety_level=DEFAULT_VARIETY_LEVEL,
            excluded_item_ids=[],
            excluded_combinations=[],
        )
        self.db.add(preferences)
        await self.db.commit()
        await self.db.refresh(preferences)
        return preferences

    async def update_preferences(
        self, user_id: uuid.UUID, data: PreferenceUpdate
    ) -> UserPreference:
        preferences = await self.get_or_create_preferences(user_id)

        update_data = data.model_dump(exclude_unset=True)
        update_data = self._strip_color_overlaps(update_data, preferences)

        for field, value in update_data.items():
            if field == "style_profile" and value is not None:
                current_profile = dict(preferences.style_profile or {})
                update_value = value.model_dump() if hasattr(value, "model_dump") else value
                current_profile.update(update_value)
                preferences.style_profile = current_profile
                flag_modified(preferences, "style_profile")
            elif field in (
                "color_favorites",
                "color_avoid",
                "excluded_item_ids",
                "excluded_combinations",
            ):
                setattr(preferences, field, value)
                flag_modified(preferences, field)
            else:
                setattr(preferences, field, value)

        await self.db.commit()
        await self.db.refresh(preferences)
        return preferences

    @staticmethod
    def _strip_color_overlaps(update_data: dict, preferences: UserPreference) -> dict:
        has_favorites = "color_favorites" in update_data
        has_avoid = "color_avoid" in update_data

        if has_favorites and has_avoid:
            update_data["color_avoid"] = _without_overlaps(
                update_data["color_avoid"], update_data["color_favorites"]
            )
        elif has_favorites:
            saved_avoid = list(preferences.color_avoid or [])
            stripped = _without_overlaps(saved_avoid, update_data["color_favorites"])
            if stripped != saved_avoid:
                update_data["color_avoid"] = stripped
        elif has_avoid:
            saved_favorites = list(preferences.color_favorites or [])
            stripped = _without_overlaps(saved_favorites, update_data["color_avoid"])
            if stripped != saved_favorites:
                update_data["color_favorites"] = stripped

        return update_data

    async def reset_preferences(self, user_id: uuid.UUID) -> UserPreference:
        preferences = await self.get_preferences(user_id)
        if preferences:
            await self.db.delete(preferences)
            await self.db.commit()

        return await self.get_or_create_preferences(user_id)

    async def add_excluded_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> UserPreference:
        preferences = await self.get_or_create_preferences(user_id)
        if item_id not in preferences.excluded_item_ids:
            preferences.excluded_item_ids = [*preferences.excluded_item_ids, item_id]
            flag_modified(preferences, "excluded_item_ids")
            await self.db.commit()
            await self.db.refresh(preferences)
        return preferences

    async def remove_excluded_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> UserPreference:
        preferences = await self.get_or_create_preferences(user_id)
        if item_id in preferences.excluded_item_ids:
            preferences.excluded_item_ids = [
                i for i in preferences.excluded_item_ids if i != item_id
            ]
            flag_modified(preferences, "excluded_item_ids")
            await self.db.commit()
            await self.db.refresh(preferences)
        return preferences
