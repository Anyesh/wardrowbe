import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.database as database
from app.api.auth import create_access_token
from app.main import app
from app.models import User

APP_DIR = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture
def real_get_db(async_engine, monkeypatch):
    test_session_maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    monkeypatch.setattr(database, "async_session_maker", test_session_maker)
    app.dependency_overrides.clear()
    return test_session_maker


async def _asgi_call(method, path, body=None, headers=None, on_response_start=None):
    raw_body = json.dumps(body).encode() if body is not None else b""
    raw_headers = [(b"content-type", b"application/json")]
    for name, value in (headers or {}).items():
        raw_headers.append((name.lower().encode(), value.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": raw_headers,
        "client": ("127.0.0.1", 5000),
        "server": ("test", 80),
    }
    request_sent = False
    status: list[int] = []
    chunks: list[bytes] = []

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": raw_body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status.append(message["status"])
            if on_response_start is not None:
                await on_response_start()
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return status[0], b"".join(chunks)


@pytest.mark.asyncio
async def test_sync_commits_new_user_before_response_starts(real_get_db, monkeypatch):
    external_id = f"scope-{uuid4()}"
    events: list[str] = []
    visible_at_response_start: list[bool] = []
    original_commit = AsyncSession.commit

    async def recording_commit(self):
        events.append("commit")
        await original_commit(self)

    async def on_response_start():
        events.append("response.start")
        async with real_get_db() as other:
            found = await other.execute(select(User.id).where(User.external_id == external_id))
            visible_at_response_start.append(found.scalar_one_or_none() is not None)

    monkeypatch.setattr(AsyncSession, "commit", recording_commit)
    try:
        status, _ = await _asgi_call(
            "POST",
            "/api/v1/auth/sync",
            body={
                "external_id": external_id,
                "email": f"{external_id}@example.com",
                "display_name": "Scope Test",
            },
            on_response_start=on_response_start,
        )
    finally:
        async with real_get_db() as cleanup:
            await cleanup.execute(delete(User).where(User.external_id == external_id))
            await original_commit(cleanup)

    assert status == 200
    assert events == ["commit", "response.start"]
    assert visible_at_response_start == [True]


@pytest.mark.asyncio
async def test_authenticated_request_shares_one_session(real_get_db, monkeypatch, test_user):
    opened: list[AsyncSession] = []

    def counting_session_maker():
        session = real_get_db()
        opened.append(session)
        return session

    monkeypatch.setattr(database, "async_session_maker", counting_session_maker)

    status, _ = await _asgi_call(
        "GET",
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {create_access_token(test_user.external_id)}"},
    )

    assert status == 200
    assert len(opened) == 1


def test_session_is_injected_only_through_db_session_alias():
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if path.name != "database.py" and re.search(r"Depends\(\s*get_db\b", path.read_text())
    ]
    assert offenders == []
