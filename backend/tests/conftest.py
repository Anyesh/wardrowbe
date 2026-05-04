import asyncio
import os
import subprocess
import sys

# Set test environment — clear OIDC vars so auth tests run with a known state
os.environ["DEBUG"] = "true"
os.environ["SECRET_KEY"] = "change-me-in-production"
os.environ["STORAGE_PATH"] = "/tmp/wardrobe_test"
os.environ.pop("OIDC_ISSUER_URL", None)
os.environ.pop("OIDC_CLIENT_ID", None)
os.environ.pop("OIDC_CLIENT_SECRET", None)

from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.auth import create_access_token
from app.config import get_settings
from app.database import get_db
from app.main import app
from app.models import User, UserPreference

# Test database URL from environment — set in docker-compose.dev.yml, never falls back to DATABASE_URL.
TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
_ADMIN_DSN = TEST_DATABASE_URL.replace("+asyncpg", "").rsplit("/", 1)[0] + "/postgres"

_test_db_ready = False


async def _ensure_test_db():
    global _test_db_ready
    if _test_db_ready:
        return

    conn = await asyncpg.connect(_ADMIN_DSN)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'wardrobe_test'")
        if not exists:
            await conn.execute("CREATE DATABASE wardrobe_test")
    finally:
        await conn.close()

    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        check=True,
        capture_output=True,
    )
    _test_db_ready = True


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    await _ensure_test_db()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(autouse=True)
async def _clear_rate_limits():
    settings = get_settings()
    try:
        redis = Redis.from_url(str(settings.redis_url))
        keys = await redis.keys("rate_limit:*")
        if keys:
            await redis.delete(*keys)
        await redis.aclose()
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    unique_id = uuid4()
    user = User(
        id=unique_id,
        external_id=f"test-user-{unique_id}",
        email=f"test-{unique_id}@example.com",
        display_name="Test User",
        timezone="UTC",
        is_active=True,
        onboarding_completed=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user_with_preferences(db_session: AsyncSession, test_user: User) -> User:
    preferences = UserPreference(
        user_id=test_user.id,
        color_favorites=["black", "navy", "white"],
        color_avoid=["orange"],
    )
    db_session.add(preferences)
    await db_session.commit()
    await db_session.refresh(test_user)
    return test_user


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    token = create_access_token(test_user.external_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_item_data() -> dict[str, Any]:
    return {
        "type": "shirt",
        "subtype": "casual",
        "name": "Blue Oxford Shirt",
        "brand": "Uniqlo",
        "colors": ["blue", "white"],
        "primary_color": "blue",
        "favorite": False,
    }


@pytest.fixture
def sample_tags() -> dict[str, Any]:
    return {
        "type": "shirt",
        "subtype": "oxford",
        "primary_color": "blue",
        "colors": ["blue", "white"],
        "pattern": "solid",
        "material": "cotton",
        "style": ["casual", "smart-casual"],
        "formality": "smart-casual",
        "season": ["spring", "fall", "all-season"],
        "confidence": 0.85,
    }
