import pytest
from pydantic import ValidationError

from app.config import Settings
from app.workers import settings as worker_settings

PASSWORD = "p@ss:w/rd#1"
ENCODED_PASSWORD = "p%40ss%3Aw%2Frd%231"
UNENCODED_SECRET = "hunter2"

DEFAULTS = {
    "host": "localhost",
    "port": 6379,
    "unix_socket_path": None,
    "database": 0,
    "username": None,
    "password": None,
    "ssl": False,
}


@pytest.mark.parametrize(
    "url, expected",
    [
        ("redis://redis:6379", {"host": "redis"}),
        ("redis://redis:6379/", {"host": "redis"}),
        (" redis://cache:6380/4/\n", {"host": "cache", "port": 6380, "database": 4}),
        ("redis://cache:6379/1?db=2", {"host": "cache", "database": 2}),
        (
            f"redis://:{ENCODED_PASSWORD}@redis:6379/2",
            {"host": "redis", "database": 2, "password": PASSWORD},
        ),
        ("redis://user@cache:6379/3", {"host": "cache", "database": 3, "username": "user"}),
        (
            "redis://us%65r:p%40ssword@%63ache:6380/4",
            {
                "host": "cache",
                "port": 6380,
                "database": 4,
                "username": "user",
                "password": "p@ssword",
            },
        ),
        (
            f"redis://user:{ENCODED_PASSWORD}@[::1]:6380/1",
            {"host": "::1", "port": 6380, "database": 1, "username": "user", "password": PASSWORD},
        ),
        ("rediss://cache:6380?db=5", {"host": "cache", "port": 6380, "database": 5, "ssl": True}),
        (
            "unix:///run/redis/my%20socket.sock?db=2",
            {"unix_socket_path": "/run/redis/my socket.sock", "database": 2},
        ),
        (
            f"unix://:{ENCODED_PASSWORD}@/run/redis/redis.sock",
            {"unix_socket_path": "/run/redis/redis.sock", "password": PASSWORD},
        ),
    ],
)
def test_workers_get_the_decoded_redis_url(monkeypatch, url, expected):
    configured = Settings(_env_file=None, redis_url=url)
    assert configured.redis_url == url.strip()
    monkeypatch.setattr(worker_settings, "settings", configured)

    worker = worker_settings.get_redis_settings()
    assert {key: getattr(worker, key) for key in DEFAULTS} == {**DEFAULTS, **expected}


@pytest.mark.parametrize(
    "url",
    [
        f"http://:{ENCODED_PASSWORD}@cache:6379/0",
        "redis://",
        f"redis://:{ENCODED_PASSWORD}@:6379/0",
        f"redis://:{ENCODED_PASSWORD}@cache:not-a-port/0",
        f"redis://:{ENCODED_PASSWORD}@cache:65536/0",
        f"redis://:{ENCODED_PASSWORD}@cache:0/0",
        f"redis://default:4821#{UNENCODED_SECRET}@cache:6379/0",
        f"redis://default:{UNENCODED_SECRET}/x@cache:6379/0",
        f"redis://default:p\uff03{UNENCODED_SECRET}@cache:6379/0",
        f"redis://:{ENCODED_PASSWORD}@cache:6379/not-a-db",
        f"redis://:{ENCODED_PASSWORD}@cache:6379/-1",
        f"redis://:{ENCODED_PASSWORD}@cache:6379/1/2",
        f"unix://:{ENCODED_PASSWORD}@host/run/redis.sock",
        "unix:///",
        "unix://",
        f"unix:///run/redis.sock?password={ENCODED_PASSWORD}",
        f"redis://:{ENCODED_PASSWORD}@cache:6379/0?username=user",
        f"redis://:{ENCODED_PASSWORD}@cache:6379/0?socket_timeout=5",
        f"redis://:{ENCODED_PASSWORD}@cache:6379/0?db=",
        f"redis://:{ENCODED_PASSWORD}@cache:6379/0?db=-1",
        f"redis://:{ENCODED_PASSWORD}@cache:6379/0?db=1&db=2",
    ],
)
def test_invalid_redis_urls_fail_configuration_without_echoing_secrets(url):
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, redis_url=url)
    for secret in (PASSWORD, ENCODED_PASSWORD, UNENCODED_SECRET):
        assert secret not in str(exc_info.value)
