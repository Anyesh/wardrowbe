import re
from urllib.parse import parse_qs, urlsplit

from redis.asyncio.connection import ConnectKwargs, parse_url

_NUMBER = re.compile(r"[0-9]+")
_MALFORMED = (
    "Redis URL is malformed; check the port and percent-encode reserved characters in credentials"
)


def parse_redis_url(url: str) -> ConnectKwargs:
    # The API hands REDIS_URL to redis-py while the arq workers get settings built from
    # this result, so a URL is refused when redis-py would silently reinterpret it
    # (port 0, a db path like /1/2) or when it carries options the workers cannot be given.
    # urllib quotes the offending text in its errors, which for an unencoded "/" or "#"
    # in a password is the password itself, so its message must not reach the startup log.
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise ValueError(_MALFORMED) from None
    if parts.fragment:
        raise ValueError(_MALFORMED)
    if parts.scheme in ("redis", "rediss"):
        if not parts.hostname:
            raise ValueError("Redis URL must include a host")
        if port == 0:
            raise ValueError("Redis URL port must be between 1 and 65535")
        path_db = parts.path.strip("/")
        if path_db and not _NUMBER.fullmatch(path_db):
            raise ValueError("Redis URL path must be a non-negative database number")
    elif parts.scheme == "unix":
        if parts.hostname or not parts.path.startswith("/") or parts.path == "/":
            raise ValueError("Redis unix URL must be unix://[:password@]/absolute/socket/path")
    else:
        raise ValueError("Redis URL must use the redis, rediss or unix scheme")

    query = parse_qs(parts.query, keep_blank_values=True)
    if set(query) - {"db"}:
        raise ValueError("Redis URL only supports the db query parameter")
    if "db" in query and (len(query["db"]) != 1 or not _NUMBER.fullmatch(query["db"][0])):
        raise ValueError("Redis URL db must be a single non-negative integer")

    return parse_url(url)
