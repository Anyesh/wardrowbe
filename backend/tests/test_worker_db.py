from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.db import close_db, get_db_session, init_db
from app.workers.tagging import shutdown, startup


class TestInitDb:
    @pytest.mark.asyncio
    async def test_populates_ctx_with_engine_and_factory(self):
        ctx: dict = {}
        with patch("app.workers.db.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock()
            await init_db(ctx)

        assert "db_engine" in ctx
        assert "db_session_factory" in ctx
        assert ctx["db_engine"] is mock_create.return_value
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_database_url_and_echo_from_settings(self):
        ctx: dict = {}
        fake_settings = MagicMock()
        fake_settings.database_url = "postgresql+asyncpg://u:p@host/db"
        fake_settings.database_echo = True

        with (
            patch("app.workers.db.get_settings", return_value=fake_settings),
            patch("app.workers.db.create_async_engine") as mock_create,
        ):
            mock_create.return_value = MagicMock()
            await init_db(ctx)

        call_kwargs = mock_create.call_args
        assert str(fake_settings.database_url) in call_kwargs.args
        assert call_kwargs.kwargs["echo"] is True


class TestCloseDb:
    @pytest.mark.asyncio
    async def test_disposes_engine_and_removes_keys(self):
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        ctx = {"db_engine": mock_engine, "db_session_factory": MagicMock()}

        await close_db(ctx)

        mock_engine.dispose.assert_awaited_once()
        assert "db_engine" not in ctx
        assert "db_session_factory" not in ctx

    @pytest.mark.asyncio
    async def test_second_call_is_noop(self):
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        ctx = {"db_engine": mock_engine, "db_session_factory": MagicMock()}

        await close_db(ctx)
        await close_db(ctx)

        mock_engine.dispose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_on_empty_ctx(self):
        await close_db({})


class TestGetDbSession:
    def test_returns_session_from_factory(self):
        mock_session = MagicMock()
        ctx = {"db_session_factory": MagicMock(return_value=mock_session)}

        assert get_db_session(ctx) is mock_session

    def test_raises_runtime_error_before_init(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            get_db_session({})


class TestWorkerHooks:
    @pytest.mark.asyncio
    async def test_startup_calls_init_db_and_creates_ai_service(self):
        mock_ai = MagicMock()
        mock_ai.check_health = AsyncMock(return_value={"status": "ok"})
        ctx: dict = {}

        with (
            patch("app.workers.tagging.init_db", new_callable=AsyncMock) as mock_init,
            patch("app.workers.tagging.AIService", return_value=mock_ai),
        ):
            await startup(ctx)

        mock_init.assert_awaited_once_with(ctx)
        assert ctx["ai_service"] is mock_ai
        mock_ai.check_health.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_calls_close_db(self):
        ctx = {"db_engine": MagicMock(), "db_session_factory": MagicMock()}

        with patch("app.workers.tagging.close_db", new_callable=AsyncMock) as mock_close:
            await shutdown(ctx)

        mock_close.assert_awaited_once_with(ctx)


class TestDbLifecycleRoundTrip:
    @pytest.mark.asyncio
    async def test_init_then_get_session_then_close(self):
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        mock_session = MagicMock()
        mock_factory = MagicMock(return_value=mock_session)
        ctx: dict = {}

        with (
            patch("app.workers.db.create_async_engine", return_value=mock_engine),
            patch("app.workers.db.async_sessionmaker", return_value=mock_factory),
        ):
            await init_db(ctx)

        assert get_db_session(ctx) is mock_session

        await close_db(ctx)
        mock_engine.dispose.assert_awaited_once()

        with pytest.raises(RuntimeError, match="not initialized"):
            get_db_session(ctx)
