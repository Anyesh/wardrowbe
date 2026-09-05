import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.suggestion_cache import (
    _cache_key,
    clear_suggestions,
    has_cached,
    pop_suggestion,
    push_suggestions,
)


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.lpop = AsyncMock(return_value=None)
    redis.llen = AsyncMock(return_value=0)
    redis.delete = AsyncMock()

    pipe = MagicMock()
    pipe.execute = AsyncMock()
    redis.pipeline.return_value = pipe
    return redis, pipe


class TestSuggestionCache:
    @pytest.mark.asyncio
    async def test_push_and_pop_fifo(self, user_id, mock_redis):
        redis, pipe = mock_redis

        with patch("app.services.suggestion_cache.get_redis", AsyncMock(return_value=redis)):
            suggestions = [
                {"items": [1, 2], "headline": "First"},
                {"items": [3, 4], "headline": "Second"},
            ]
            await push_suggestions(user_id, "casual", suggestions)

            assert pipe.rpush.call_count == 2
            pipe.expire.assert_called_once()
            pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_pop_empty_returns_none(self, user_id, mock_redis):
        redis, _ = mock_redis
        redis.lpop.return_value = None

        with patch("app.services.suggestion_cache.get_redis", AsyncMock(return_value=redis)):
            result = await pop_suggestion(user_id, "casual")
            assert result is None

    @pytest.mark.asyncio
    async def test_pop_returns_dict(self, user_id, mock_redis):
        redis, _ = mock_redis
        redis.lpop.return_value = json.dumps({"items": [1, 2], "headline": "Test"})

        with patch("app.services.suggestion_cache.get_redis", AsyncMock(return_value=redis)):
            result = await pop_suggestion(user_id, "casual")
            assert result == {"items": [1, 2], "headline": "Test"}

    @pytest.mark.asyncio
    async def test_clear_removes_all(self, user_id, mock_redis):
        redis, _ = mock_redis

        with patch("app.services.suggestion_cache.get_redis", AsyncMock(return_value=redis)):
            await clear_suggestions(user_id, "casual")
            key = _cache_key(user_id, "casual")
            redis.delete.assert_called_once_with(key)

    @pytest.mark.asyncio
    async def test_has_cached_true(self, user_id, mock_redis):
        redis, _ = mock_redis
        redis.llen.return_value = 2

        with patch("app.services.suggestion_cache.get_redis", AsyncMock(return_value=redis)):
            assert await has_cached(user_id, "casual") is True

    @pytest.mark.asyncio
    async def test_redis_error_degrades_gracefully(self, user_id):
        async def failing_redis():
            raise ConnectionError("Redis down")

        with patch("app.services.suggestion_cache.get_redis", side_effect=failing_redis):
            result = await pop_suggestion(user_id, "casual")
            assert result is None

            cached = await has_cached(user_id, "casual")
            assert cached is False

            await push_suggestions(user_id, "casual", [{"items": [1]}])
            await clear_suggestions(user_id, "casual")

    @pytest.mark.asyncio
    async def test_push_and_pop_with_include_items(self, user_id, mock_redis):
        redis, pipe = mock_redis
        item1 = uuid4()
        item2 = uuid4()

        with patch("app.services.suggestion_cache.get_redis", AsyncMock(return_value=redis)):
            suggestions = [
                {"items": [1, 2], "headline": "Alt 1"},
                {"items": [1, 3], "headline": "Alt 2"},
            ]
            await push_suggestions(user_id, "casual", suggestions, include_items=[item2, item1])

            key = _cache_key(user_id, "casual", include_items=[item1, item2])
            assert pipe.rpush.call_count == 2
            assert pipe.rpush.call_args_list[0][0][0] == key

            redis.lpop.return_value = json.dumps({"items": [1, 2], "headline": "Alt 1"})
            popped = await pop_suggestion(user_id, "casual", include_items=[item1, item2])
            assert popped == {"items": [1, 2], "headline": "Alt 1"}
            redis.lpop.assert_called_with(key)

    def test_cache_key_deterministic_sorting(self, user_id):
        id_a = uuid4()
        id_b = uuid4()
        key1 = _cache_key(user_id, "casual", include_items=[id_a, id_b])
        key2 = _cache_key(user_id, "casual", include_items=[id_b, id_a])
        assert key1 == key2
        assert str(id_a) in key1
        assert str(id_b) in key1
