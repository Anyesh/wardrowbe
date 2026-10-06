import logging

from app.config import Settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(settings: Settings) -> None:
    # The handler goes on "app" rather than root because arq's CLI gives its own
    # logger a handler without disabling propagation, so a root handler would print
    # every arq line twice and would also surface INFO chatter from httpx and friends.
    app_logger = logging.getLogger("app")
    app_logger.setLevel(settings.log_level)
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        app_logger.addHandler(handler)
