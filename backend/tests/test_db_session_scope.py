import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as database
from app.api.auth import create_access_token
from app.main import app
from app.models import User
from app.services.preference_service import PreferenceService
from app.services.user_service import UserService

APP_DIR = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture
def real_get_db(session_maker, monkeypatch):
    monkeypatch.setattr(database, "async_session_maker", session_maker)
    monkeypatch.setattr(app, "dependency_overrides", {})
    return session_maker


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
    seen_by_auth: list[AsyncSession] = []
    seen_by_endpoint: list[AsyncSession] = []

    def counting_session_maker():
        session = real_get_db()
        opened.append(session)
        return session

    original_user_service_init = UserService.__init__
    original_preference_service_init = PreferenceService.__init__

    def recording_user_service_init(self, db):
        seen_by_auth.append(db)
        original_user_service_init(self, db)

    def recording_preference_service_init(self, db):
        seen_by_endpoint.append(db)
        original_preference_service_init(self, db)

    monkeypatch.setattr(database, "async_session_maker", counting_session_maker)
    monkeypatch.setattr(UserService, "__init__", recording_user_service_init)
    monkeypatch.setattr(PreferenceService, "__init__", recording_preference_service_init)

    status, _ = await _asgi_call(
        "GET",
        "/api/v1/users/me/preferences",
        headers={"Authorization": f"Bearer {create_access_token(test_user.external_id)}"},
    )

    assert status == 200
    assert len(opened) == 1
    assert seen_by_auth and seen_by_endpoint
    assert all(db is opened[0] for db in seen_by_auth + seen_by_endpoint)


def test_session_is_injected_only_through_db_session_alias():
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if path.name != "database.py" and re.search(r"Depends\(\s*get_db\b", path.read_text())
    ]
    assert offenders == []
