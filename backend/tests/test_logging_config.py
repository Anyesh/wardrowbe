import logging

import pytest
from pydantic import ValidationError

from app import main
from app.config import Settings
from app.logging_config import configure_logging
from app.workers import image_worker, worker

# Captured at collection, before any test has run startup code in this process.
_PRISTINE_APP_LOGGER = (logging.getLogger("app").level, list(logging.getLogger("app").handlers))


@pytest.fixture
def app_logger():
    logger = logging.getLogger("app")
    logger.handlers = []
    return logger


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


async def _noop(ctx):
    return None


async def _start_tagging_worker(monkeypatch, settings):
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "init_db", _noop)
    monkeypatch.setattr(worker, "recover_stale_processing_items", _noop)
    await worker.startup({})


async def _start_image_worker(monkeypatch, settings):
    monkeypatch.setattr(image_worker, "get_settings", lambda: settings)
    monkeypatch.setattr(image_worker, "init_db", _noop)
    await image_worker.startup({})


async def _start_api(monkeypatch, settings):
    monkeypatch.setattr(main, "settings", settings)
    async with main.lifespan(main.app):
        pass


@pytest.mark.parametrize(
    "start",
    [_start_tagging_worker, _start_image_worker, _start_api],
    ids=["tagging-worker", "image-worker", "api"],
)
@pytest.mark.asyncio
async def test_every_entrypoint_configures_app_logging(app_logger, monkeypatch, start):
    await start(monkeypatch, Settings(log_level="WARNING", ai_internal_enabled=False))

    assert app_logger.level == logging.WARNING
    assert len(app_logger.handlers) == 1


# These two run in file order: the first configures logging the way worker startup does,
# without the app_logger fixture, and the second checks nothing of it survived.
def test_unisolated_configure_logging_changes_the_app_logger():
    configure_logging(Settings(log_level="DEBUG"))

    assert logging.getLogger("app").handlers


def test_app_logger_is_restored_between_tests():
    logger = logging.getLogger("app")
    assert (logger.level, logger.handlers) == _PRISTINE_APP_LOGGER
