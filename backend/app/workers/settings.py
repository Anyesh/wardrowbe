from arq.connections import RedisSettings
from redis.asyncio.connection import SSLConnection

from app.config import get_settings
from app.utils.redis_url import parse_redis_url

settings = get_settings()


def get_redis_settings() -> RedisSettings:
    options = parse_redis_url(settings.redis_url)
    return RedisSettings(
        host=options.get("host", "localhost"),
        port=options.get("port", 6379),
        unix_socket_path=options.get("path"),
        database=options.get("db", 0),
        username=options.get("username"),
        password=options.get("password"),
        ssl=options.get("connection_class") is SSLConnection,
    )
