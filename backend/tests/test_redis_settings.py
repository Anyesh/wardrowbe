"""Redis URL settings shared by the API and background workers."""

import pytest
from pydantic import ValidationError
from redis.asyncio.connection import parse_url

from app.config import Settings
from app.workers import settings as worker_settings


@pytest.mark.parametrize(
    "url, expected",
    [
        ("redis://localhost:6379/0", {"host": "localhost", "port": 6379, "database": 0}),
        ("redis://cache:6380/4", {"host": "cache", "port": 6380, "database": 4}),
        ("redis://%63ache:6380/4", {"host": "cache", "port": 6380, "database": 4}),
        (
            "redis://user:p%40ssword@cache:6380/4",
            {
                "host": "cache",
                "port": 6380,
                "database": 4,
                "username": "user",
                "password": "p@ssword",
            },
        ),
        (
            "rediss://cache:6380?db=5",
            {"host": "cache", "port": 6380, "database": 5, "ssl": True},
        ),
        (
            "unix:///run/redis/redis.sock?db=2",
            {"unix_socket_path": "/run/redis/redis.sock", "database": 2},
        ),
        (
            "unix:///run/redis/my%20socket.sock?db=2",
            {"unix_socket_path": "/run/redis/my socket.sock", "database": 2},
        ),
    ],
)
def test_redis_url_is_preserved_for_workers(monkeypatch, url, expected):
    configured = Settings(_env_file=None, redis_url=url)
    assert configured.redis_url == url
    monkeypatch.setattr(worker_settings, "settings", configured)

    redis_settings = worker_settings.get_redis_settings()
    for key, value in expected.items():
        assert getattr(redis_settings, key) == value


def test_encoded_tcp_url_uses_same_connection_as_api(monkeypatch):
    url = "redis://us%65r:p%40ssword@%63ache:6380/4"
    monkeypatch.setattr(worker_settings, "settings", Settings(_env_file=None, redis_url=url))

    api_settings = parse_url(url)
    worker = worker_settings.get_redis_settings()
    assert worker.host == api_settings["host"]
    assert worker.port == api_settings["port"]
    assert worker.database == api_settings["db"]
    assert worker.username == api_settings["username"]
    assert worker.password == api_settings["password"]


@pytest.mark.parametrize(
    "url",
    [
        "http://cache:6379/0",
        "redis://",
        "redis://cache:not-a-port/0",
        "redis://cache:6379/not-a-db",
        "unix://host/run/redis.sock",
        "unix:///",
        "unix:///run/redis.sock?password=secret",
        "redis://cache:6379/0?username=user",
        "redis://cache:6379/0?db=",
        "redis://cache:6379/0?db=1&db=2",
    ],
)
def test_invalid_redis_urls_fail_configuration(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, redis_url=url)
