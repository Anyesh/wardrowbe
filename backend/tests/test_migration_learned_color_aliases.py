import os
import subprocess

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.learning import UserLearningProfile

REVISION = "6c1e8f2a9d47"
PREVIOUS = "952169051179"


def _alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    subprocess.run(["python", "-m", "alembic", *args], env=env, check=True, capture_output=True)


@pytest.mark.asyncio
async def test_remaps_learned_profile_colours(db_session: AsyncSession, test_user: User):
    user_id = test_user.id
    await db_session.commit()
    _alembic("downgrade", PREVIOUS)
    try:
        db_session.add(
            UserLearningProfile(
                user_id=user_id,
                learned_color_scores={
                    "charcoal": 0.6,
                    "gray": 0.2,
                    "Khaki": -0.5,
                    "navy": 0.35,
                    "salmon": 0.1,
                },
                learned_occasion_patterns={
                    "work": {
                        "preferred_colors": ["charcoal", "navy", "gray", "teal"],
                        "success_rate": 0.75,
                    },
                    "casual": {"preferred_colors": [], "success_rate": 0.5},
                    "date": {"success_rate": 1.0},
                },
            )
        )
        await db_session.commit()
    finally:
        _alembic("upgrade", "head")

    db_session.expire_all()
    stored = await db_session.get(UserLearningProfile, user_id)
    assert stored.learned_color_scores == {"gray": 0.4, "tan": -0.5, "navy": 0.35, "salmon": 0.1}
    assert stored.learned_occasion_patterns == {
        "work": {"preferred_colors": ["gray", "navy", "blue"], "success_rate": 0.75},
        "casual": {"preferred_colors": [], "success_rate": 0.5},
        "date": {"success_rate": 1.0},
    }


@pytest.mark.asyncio
async def test_leaves_empty_profiles_alone(db_session: AsyncSession, test_user: User):
    user_id = test_user.id
    await db_session.commit()
    _alembic("downgrade", PREVIOUS)
    try:
        db_session.add(
            UserLearningProfile(
                user_id=user_id, learned_color_scores={}, learned_occasion_patterns={}
            )
        )
        await db_session.commit()
    finally:
        _alembic("upgrade", "head")

    db_session.expire_all()
    stored = await db_session.get(UserLearningProfile, user_id)
    assert stored.learned_color_scores == {}
    assert stored.learned_occasion_patterns == {}
