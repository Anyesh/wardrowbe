import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.preference import (
    DEFAULT_AVOID_REPEAT_DAYS,
    DEFAULT_COLD_THRESHOLD,
    DEFAULT_HOT_THRESHOLD,
    UserPreference,
)
from app.schemas.preference import PreferenceUpdate


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
            style_profile={
                "casual": 50,
                "formal": 50,
                "sporty": 50,
                "minimalist": 50,
                "bold": 50,
            },
            default_occasion="casual",
            temperature_sensitivity="normal",
            cold_threshold=DEFAULT_COLD_THRESHOLD,
            hot_threshold=DEFAULT_HOT_THRESHOLD,
            layering_preference="moderate",
            avoid_repeat_days=DEFAULT_AVOID_REPEAT_DAYS,
            prefer_underused_items=True,
            variety_level="moderate",
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
            overlap = set(update_data["color_favorites"]) & set(update_data["color_avoid"])
            if overlap:
                update_data["color_avoid"] = [
                    c for c in update_data["color_avoid"] if c not in overlap
                ]
        elif has_favorites:
            new_favorites = set(update_data["color_favorites"])
            saved_avoid = list(preferences.color_avoid or [])
            stripped = [c for c in saved_avoid if c not in new_favorites]
            if stripped != saved_avoid:
                update_data["color_avoid"] = stripped
        elif has_avoid:
            new_avoid = set(update_data["color_avoid"])
            saved_favorites = list(preferences.color_favorites or [])
            stripped = [c for c in saved_favorites if c not in new_avoid]
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
