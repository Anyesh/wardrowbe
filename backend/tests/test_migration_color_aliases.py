import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClothingItem, User, UserPreference
from app.utils.garment_vocabulary import canonical_color

REVISION = "952169051179"
PREVIOUS = "d5e6f7a8b9c0"
TESTS = Path(__file__).parent
COLOR_NAME_CASES = json.loads((TESTS / "fixtures" / "color_names.json").read_text())


def _migration(revision: str):
    (path,) = (TESTS.parent / "migrations" / "versions").glob(f"{revision}_*.py")
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    subprocess.run(["python", "-m", "alembic", *args], env=env, check=True, capture_output=True)


REMAPPED = {
    "pants": ("gray", ["gray", "tan", "blue", "olive", "brown"]),
    "shirt": ("light-blue", ["light-blue", "salmon"]),
    "jacket": ("light-blue", ["navy", "light-blue", "salmon", "gray", "i\u0307ndigo"]),
    "hat": (None, []),
    "scarf": (None, None),
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
                    colors=[
                        "Navy",
                        "NAVY",
                        "Light Blue",
                        None,
                        "light-blue",
                        "\u00a0\t",
                        "Salmon",
                        "dark\u00a0 blue",
                        "\tLight  Grey\n",
                        "\u0130ndigo",
                    ],
                ),
                ClothingItem(
                    user_id=user_id, type="hat", image_path="z.jpg", primary_color=None, colors=[]
                ),
                ClothingItem(
                    user_id=user_id, type="scarf", image_path="v.jpg", primary_color="\u00a0\t "
                ),
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


@pytest.mark.parametrize("revision", [REVISION, "6c1e8f2a9d47"])
def test_frozen_colour_rule_matches_canonical_color(revision):
    rule = _migration(revision).canonical_color
    expected = {case["name"]: case["canonical"] for case in COLOR_NAME_CASES}
    assert {name: rule(name) for name in expected} == expected
    assert {name: canonical_color(name) for name in expected} == expected
