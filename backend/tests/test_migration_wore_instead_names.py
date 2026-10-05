import os
import subprocess

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.outfit import Outfit, OutfitSource

PREVIOUS = "6c1e8f2a9d47"


def _alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    subprocess.run(["python", "-m", "alembic", *args], env=env, check=True, capture_output=True)


@pytest.mark.asyncio
async def test_clears_only_generated_wore_instead_names(db_session: AsyncSession, test_user: User):
    user_id = test_user.id
    await db_session.commit()
    _alembic("downgrade", PREVIOUS)
    try:
        original = Outfit(user_id=user_id, occasion="casual", source=OutfitSource.manual)
        db_session.add(original)
        await db_session.flush()

        def wore_instead(occasion: str, name: str) -> Outfit:
            return Outfit(
                user_id=user_id,
                occasion=occasion,
                source=OutfitSource.manual,
                replaces_outfit_id=original.id,
                name=name,
            )

        generated = wore_instead("casual", "Casual (wore instead)")
        multiword = wore_instead("date_night", "Date_Night (wore instead)")
        renamed = wore_instead("casual", "My favourite look")
        kept = Outfit(
            user_id=user_id,
            occasion="casual",
            source=OutfitSource.manual,
            name="Casual (wore instead)",
        )
        db_session.add_all([generated, multiword, renamed, kept])
        await db_session.commit()
        ids = {
            "generated": generated.id,
            "multiword": multiword.id,
            "renamed": renamed.id,
            "kept": kept.id,
        }
    finally:
        _alembic("upgrade", "head")

    db_session.expire_all()
    assert (await db_session.get(Outfit, ids["generated"])).name is None
    assert (await db_session.get(Outfit, ids["multiword"])).name is None
    assert (await db_session.get(Outfit, ids["renamed"])).name == "My favourite look"
    assert (await db_session.get(Outfit, ids["kept"])).name == "Casual (wore instead)"
