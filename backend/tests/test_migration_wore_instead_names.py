import os
import subprocess
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.outfit import Outfit

PREVIOUS = "921b8d3bc2b8"


def _alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    subprocess.run(["python", "-m", "alembic", *args], env=env, check=True, capture_output=True)


@pytest.mark.asyncio
async def test_clears_only_generated_wore_instead_names(db_session: AsyncSession, test_user: User):
    user_id = test_user.id
    await db_session.commit()
    _alembic("downgrade", PREVIOUS)
    try:
        # Raw SQL: the ORM model also names columns that a later migration adds, and the
        # schema is deliberately downgraded below them here.
        async def insert(occasion: str, name: str | None, replaces: UUID | None = None) -> UUID:
            outfit_id = uuid4()
            await db_session.execute(
                text(
                    "INSERT INTO outfits (id, user_id, occasion, status, source, name,"
                    " replaces_outfit_id) VALUES (:id, :user_id, :occasion, 'pending', 'manual',"
                    " :name, :replaces)"
                ),
                {
                    "id": outfit_id,
                    "user_id": user_id,
                    "occasion": occasion,
                    "name": name,
                    "replaces": replaces,
                },
            )
            return outfit_id

        original = await insert("casual", None)
        await db_session.commit()
        generated = await insert("casual", "Casual (wore instead)", original)
        multiword = await insert("date_night", "Date_Night (wore instead)", original)
        renamed = await insert("casual", "My favourite look", original)
        kept = await insert("casual", "Casual (wore instead)")
        await db_session.commit()
        ids = {"generated": generated, "multiword": multiword, "renamed": renamed, "kept": kept}
    finally:
        _alembic("upgrade", "head")

    db_session.expire_all()
    assert (await db_session.get(Outfit, ids["generated"])).name is None
    assert (await db_session.get(Outfit, ids["multiword"])).name is None
    assert (await db_session.get(Outfit, ids["renamed"])).name == "My favourite look"
    assert (await db_session.get(Outfit, ids["kept"])).name == "Casual (wore instead)"
