import os
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


def alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    result = subprocess.run(
        ["python", "-m", "alembic", *args], env=env, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed:\n{result.stderr[-4000:]}")


@asynccontextmanager
async def migration_downgrade(db_session: AsyncSession, revision: str) -> AsyncIterator[None]:
    # Migrations lock users, so the test's own transaction must end before each alembic run or
    # the migration waits on it until lock_timeout; a failed body leaves it idle or aborted.
    await db_session.commit()
    alembic("downgrade", revision)
    try:
        yield
    finally:
        await db_session.rollback()
        alembic("upgrade", "head")
