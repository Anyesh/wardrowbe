from urllib.parse import unquote

from arq.connections import RedisSettings

from app.config import get_settings

settings = get_settings()


def get_redis_settings() -> RedisSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    # redis-py decodes URL components; keep ARQ's connection in sync with it.
    if redis_settings.unix_socket_path is None:
        redis_settings.host = unquote(redis_settings.host)
    if redis_settings.username is not None:
        redis_settings.username = unquote(redis_settings.username)
    if redis_settings.password is not None:
        redis_settings.password = unquote(redis_settings.password)
    if redis_settings.unix_socket_path is not None:
        redis_settings.unix_socket_path = unquote(redis_settings.unix_socket_path)
    return redis_settings
