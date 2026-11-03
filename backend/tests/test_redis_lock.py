"""Regression coverage for Redis lock expiry during a protected operation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import LockNotOwnedError

from app.utils import redis_lock


@pytest.mark.asyncio
async def test_expired_lock_does_not_mask_successful_work(monkeypatch, caplog) -> None:
    lock = SimpleNamespace(
        acquire=AsyncMock(return_value=True),
        release=AsyncMock(side_effect=LockNotOwnedError),
    )
    redis_client = SimpleNamespace(lock=lambda *args, **kwargs: lock)
    monkeypatch.setattr(redis_lock, "get_redis", AsyncMock(return_value=redis_client))

    async with redis_lock.distributed_lock("test-lock"):
        pass

    lock.release.assert_awaited_once()
    assert "already released" in caplog.text
