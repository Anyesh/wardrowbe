import os
import subprocess

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClothingItem, User, UserPreference

REVISION = "952169051179"
PREVIOUS = "d5e6f7a8b9c0"


def _alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    subprocess.run(["python", "-m", "alembic", *args], env=env, check=True, capture_output=True)


@pytest.mark.asyncio
async def test_remaps_and_deduplicates_frontend_only_colors(
    db_session: AsyncSession, test_user: User
):
    user_id = test_user.id
    await db_session.commit()
    _alembic("downgrade", PREVIOUS)
    try:
        aliased = ClothingItem(
            user_id=user_id,
            type="pants",
            image_path="x.jpg",
            primary_color="charcoal",
            colors=["charcoal", "gray", "Khaki", "tan", "teal", "army-green", "dark-brown"],
        )
        untouched = ClothingItem(
            user_id=user_id,
            type="shirt",
            image_path="y.jpg",
            primary_color="light-blue",
            colors=["light-blue", "salmon"],
        )
        empty = ClothingItem(
            user_id=user_id, type="hat", image_path="z.jpg", primary_color=None, colors=[]
        )
        preferences = UserPreference(
            user_id=user_id,
            color_favorites=["khaki", "tan", "navy", "charcoal"],
            color_avoid=["teal", "blue", "dark-brown"],
        )
        db_session.add_all([aliased, untouched, empty, preferences])
        await db_session.commit()
    finally:
        _alembic("upgrade", "head")

    db_session.expire_all()
    items = {
        item.type: item
        for item in await db_session.scalars(
            select(ClothingItem).where(ClothingItem.user_id == user_id)
        )
    }
    assert items["pants"].primary_color == "gray"
    assert items["pants"].colors == ["gray", "tan", "blue", "olive", "brown"]
    assert items["shirt"].primary_color == "light-blue"
    assert items["shirt"].colors == ["light-blue", "salmon"]
    assert items["hat"].primary_color is None
    assert items["hat"].colors == []

    stored = await db_session.get(UserPreference, user_id)
    assert stored.color_favorites == ["tan", "navy", "gray"]
    assert stored.color_avoid == ["blue", "brown"]
