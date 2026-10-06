import os
import subprocess

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClothingItem, User, UserPreference

REVISION = "952169051179"
PREVIOUS = "d5e6f7a8b9c0"


def _alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    subprocess.run(["python", "-m", "alembic", *args], env=env, check=True, capture_output=True)


REMAPPED = {
    "pants": ("gray", ["gray", "tan", "blue", "olive", "brown"]),
    "shirt": ("light-blue", ["light-blue", "salmon"]),
    "jacket": ("light-blue", ["navy", "light-blue", "salmon"]),
    "hat": (None, []),
    "scarf": ("", None),
    "favorites": ["tan", "navy", "gray", "olive"],
    "avoid": None,
}


async def _stored_colours(db_session: AsyncSession, user_id) -> dict:
    db_session.expire_all()
    stored = {
        item.type: (item.primary_color, item.colors)
        for item in await db_session.scalars(
            select(ClothingItem).where(ClothingItem.user_id == user_id)
        )
    }
    preferences = await db_session.get(UserPreference, user_id)
    stored["favorites"] = preferences.color_favorites
    stored["avoid"] = preferences.color_avoid
    return stored


async def _rerun_migration(db_session: AsyncSession) -> None:
    await db_session.commit()
    _alembic("downgrade", PREVIOUS)
    _alembic("upgrade", "head")


@pytest.mark.asyncio
async def test_remaps_and_deduplicates_colours_idempotently(
    db_session: AsyncSession, test_user: User
):
    user_id = test_user.id
    await db_session.commit()
    _alembic("downgrade", PREVIOUS)
    try:
        db_session.add_all(
            [
                ClothingItem(
                    user_id=user_id,
                    type="pants",
                    image_path="x.jpg",
                    primary_color="charcoal",
                    colors=["charcoal", "gray", "Khaki", "tan", "teal", "army-green", "dark-brown"],
                ),
                ClothingItem(
                    user_id=user_id,
                    type="shirt",
                    image_path="y.jpg",
                    primary_color="light-blue",
                    colors=["light-blue", "salmon"],
                ),
                ClothingItem(
                    user_id=user_id,
                    type="jacket",
                    image_path="w.jpg",
                    primary_color=" Light Blue ",
                    colors=["Navy", "NAVY", "Light Blue", None, "light-blue", "  ", "Salmon"],
                ),
                ClothingItem(
                    user_id=user_id, type="hat", image_path="z.jpg", primary_color=None, colors=[]
                ),
                ClothingItem(user_id=user_id, type="scarf", image_path="v.jpg", primary_color=""),
                UserPreference(
                    user_id=user_id,
                    color_favorites=["khaki", "tan", "NAVY", "charcoal", "Army Green"],
                ),
            ]
        )
        await db_session.flush()
        # The ORM writes the column default for a None list, so NULL arrays need an explicit UPDATE.
        await db_session.execute(
            update(ClothingItem).where(ClothingItem.type == "scarf").values(colors=None)
        )
        await db_session.execute(
            update(UserPreference).where(UserPreference.user_id == user_id).values(color_avoid=None)
        )
        await db_session.commit()
    finally:
        _alembic("upgrade", "head")

    assert await _stored_colours(db_session, user_id) == REMAPPED
    await _rerun_migration(db_session)
    assert await _stored_colours(db_session, user_id) == REMAPPED
