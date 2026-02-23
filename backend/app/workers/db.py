"""Shared database lifecycle helpers for arq workers.

The engine and session factory are created in the worker ``on_startup`` hook,
stored in the arq ``ctx`` dict, and disposed in ``on_shutdown``.  No module-
level mutable state — everything lives in ``ctx``.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

logger = logging.getLogger(__name__)


async def init_db(ctx: dict) -> None:
    """Create the engine + session factory and store them in *ctx*.

    Call this from the worker ``on_startup`` hook.
    """
    settings = get_settings()
    engine = create_async_engine(
        str(settings.database_url),
        echo=settings.database_echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    ctx["db_engine"] = engine
    ctx["db_session_factory"] = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("Worker DB engine created")


async def close_db(ctx: dict) -> None:
    """Dispose the engine and release all pooled connections.

    Call this from the worker ``on_shutdown`` hook.
    """
    engine = ctx.pop("db_engine", None)
    ctx.pop("db_session_factory", None)
    if engine is not None:
        await engine.dispose()
        logger.info("Worker DB engine disposed")


def get_db_session(ctx: dict) -> AsyncSession:
    """Get a database session from the pool stored in *ctx*."""
    factory = ctx.get("db_session_factory")
    if factory is None:
        raise RuntimeError(
            "Database session factory not initialized. "
            "Ensure init_db(ctx) is called in the worker on_startup hook."
        )
    return factory()
