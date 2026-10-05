import logging

import pytest
from pydantic import ValidationError

from app import main
from app.config import Settings
from app.logging_config import configure_logging
from app.workers import image_worker, worker


@pytest.fixture
def app_logger():
    logger = logging.getLogger("app")
    saved_level, saved_handlers = logger.level, list(logger.handlers)
    logger.handlers = []
    yield logger
    logger.setLevel(saved_level)
    logger.handlers = saved_handlers


def test_log_level_is_case_insensitive():
    assert Settings(log_level="debug").log_level == "DEBUG"


def test_unknown_log_level_is_rejected():
    with pytest.raises(ValidationError):
        Settings(log_level="loud")


def test_configure_logging_applies_the_level_to_app_loggers(app_logger):
    configure_logging(Settings(log_level="WARNING"))

    child = logging.getLogger("app.workers.notifications")
    assert not child.isEnabledFor(logging.INFO)
    assert child.isEnabledFor(logging.WARNING)


def test_configure_logging_emits_app_info_records(app_logger):
    configure_logging(Settings(log_level="INFO"))

    assert logging.getLogger("app.workers.worker").isEnabledFor(logging.INFO)
    assert len(app_logger.handlers) == 1


def test_configure_logging_twice_keeps_one_handler(app_logger):
    configure_logging(Settings(log_level="INFO"))
    configure_logging(Settings(log_level="DEBUG"))

    assert len(app_logger.handlers) == 1
    assert app_logger.level == logging.DEBUG


def _record_calls(monkeypatch, module):
    calls = []
    monkeypatch.setattr(module, "configure_logging", calls.append)
    return calls


async def _noop(ctx):
    return None


@pytest.mark.asyncio
async def test_tagging_worker_startup_configures_logging(monkeypatch):
    calls = _record_calls(monkeypatch, worker)
    monkeypatch.setattr(worker, "get_settings", lambda: Settings(ai_internal_enabled=False))
    monkeypatch.setattr(worker, "init_db", _noop)
    monkeypatch.setattr(worker, "recover_stale_processing_items", _noop)

    await worker.startup({})

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_image_worker_startup_configures_logging(monkeypatch):
    calls = _record_calls(monkeypatch, image_worker)
    monkeypatch.setattr(image_worker, "init_db", _noop)

    await image_worker.startup({})

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_api_lifespan_configures_logging(monkeypatch):
    calls = _record_calls(monkeypatch, main)

    async with main.lifespan(main.app):
        pass

    assert calls == [main.settings]
