from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import User, UserIdentity, WebAuthnCredential
from app.services.local_auth_service import LOCAL, LocalAuthService
from tests.migration_helpers import migration_downgrade
from tests.webauthn_helpers import SoftAuthenticator

PASSWORD = "correct horse battery"
API = "/api/v1/auth"


@pytest.fixture
def local_auth(monkeypatch: pytest.MonkeyPatch) -> Settings:
    # Every module holds the same cached Settings, so switching it here switches it everywhere.
    settings = get_settings()
    monkeypatch.setattr(settings, "local_auth_enabled", True)
    monkeypatch.setattr(settings, "app_url", "http://localhost:3000")
    monkeypatch.setattr(settings, "webauthn_rp_id", None)
    monkeypatch.setattr(settings, "webauthn_origin", None)
    return settings


async def _create_local_user(
    db_session: AsyncSession, *, is_admin: bool = False, password: str = PASSWORD
) -> User:
    email = f"local-{uuid4()}@example.com"
    user, _ = await LocalAuthService(db_session).create_user(
        email, password, "Local User", is_admin=is_admin
    )
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def local_user(db_session: AsyncSession, local_auth: Settings) -> User:
    return await _create_local_user(db_session)


async def _login(client: AsyncClient, email: str, password: str = PASSWORD):
    return await client.post(f"{API}/login", json={"email": email, "password": password})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _session(client: AsyncClient, user: User) -> dict[str, str]:
    response = await _login(client, user.email)
    assert response.status_code == 200, response.text
    return _bearer(response.json()["access_token"])


# --- First run -------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def empty_instance(db_session: AsyncSession, local_auth: Settings) -> AsyncGenerator[None]:
    # Inside the test's own transaction, which the client shares and which is rolled back at the
    # end, so the other tests' accounts come back untouched.
    await db_session.execute(text("TRUNCATE users CASCADE"))
    yield


async def test_setup_creates_the_first_administrator_once(
    client: AsyncClient, db_session: AsyncSession, empty_instance: None
):
    assert (await client.get(f"{API}/setup")).json() == {"required": True}

    response = await client.post(
        f"{API}/setup",
        json={"email": "Admin@Example.com", "password": PASSWORD, "display_name": "Admin"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "admin@example.com"
    assert body["is_new_user"] is True
    me = await client.get("/api/v1/users/me", headers=_bearer(body["access_token"]))
    assert me.status_code == 200
    admin = await db_session.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin.is_admin is True
    assert admin.password_hash.startswith("$argon2id$")
    assert PASSWORD not in admin.password_hash

    assert (await client.get(f"{API}/setup")).json() == {"required": False}
    again = await client.post(
        f"{API}/setup", json={"email": "intruder@example.com", "password": PASSWORD}
    )
    assert again.status_code == 409
    assert await db_session.scalar(select(User).where(User.email == "intruder@example.com")) is None


async def test_setup_refuses_a_short_password(client: AsyncClient, empty_instance: None):
    response = await client.post(
        f"{API}/setup", json={"email": "admin@example.com", "password": "short"}
    )
    assert response.status_code == 422


async def test_setup_is_closed_when_accounts_exist(client: AsyncClient, local_user: User):
    assert (await client.get(f"{API}/setup")).json() == {"required": False}
    response = await client.post(
        f"{API}/setup", json={"email": "second@example.com", "password": PASSWORD}
    )
    assert response.status_code == 409


# --- Email + password ------------------------------------------------------------------------


async def test_login_with_the_right_password_opens_a_session(
    client: AsyncClient, db_session: AsyncSession, local_user: User
):
    response = await _login(client, local_user.email.upper())

    assert response.status_code == 200
    token = response.json()["access_token"]
    claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    identity = await db_session.get(UserIdentity, UUID(claims["iid"]))
    assert (identity.provider, identity.subject) == (LOCAL, str(local_user.id))
    me = await client.get("/api/v1/users/me", headers=_bearer(token))
    assert me.status_code == 200
    assert me.json()["email"] == local_user.email


async def test_session_lasts_the_configured_lifetime(
    client: AsyncClient, local_user: User, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(get_settings(), "session_lifetime_hours", 2)
    token = (await _login(client, local_user.email)).json()["access_token"]
    claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 2 * 3600


async def test_expired_session_is_refused(client: AsyncClient, local_user: User):
    token = (await _login(client, local_user.email)).json()["access_token"]
    claims = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    claims["exp"] = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
    expired = jwt.encode(claims, get_settings().secret_key, algorithm="HS256")

    assert (await client.get("/api/v1/users/me", headers=_bearer(expired))).status_code == 401


async def test_wrong_password_and_unknown_email_get_the_same_answer(
    client: AsyncClient, local_user: User
):
    wrong = await _login(client, local_user.email, "not the password")
    unknown = await _login(client, f"nobody-{uuid4()}@example.com")
    malformed = await _login(client, "not-an-email")

    assert wrong.status_code == unknown.status_code == malformed.status_code == 401
    assert wrong.json() == unknown.json() == malformed.json()


async def test_account_without_password_cannot_sign_in_locally(
    client: AsyncClient, test_user: User, local_auth: Settings
):
    response = await _login(client, test_user.email, "")
    assert response.status_code == 422
    response = await _login(client, test_user.email, "anything at all")
    assert response.status_code == 401


async def test_inactive_account_cannot_sign_in(
    client: AsyncClient, db_session: AsyncSession, local_user: User
):
    local_user.is_active = False
    await db_session.flush()
    assert (await _login(client, local_user.email)).status_code == 401


async def test_repeated_failures_lock_the_account_for_a_while(
    client: AsyncClient, local_user: User
):
    for _ in range(10):
        assert (await _login(client, local_user.email, "wrong password")).status_code == 401

    # Even the right password is refused until the window passes, so guessing stops here.
    locked = await _login(client, local_user.email)
    assert locked.status_code == 429


async def test_protected_routes_need_a_session(client: AsyncClient, local_user: User):
    for path in ("/api/v1/users/me", "/api/v1/items", "/api/v1/outfits", f"{API}/security"):
        assert (await client.get(path)).status_code == 401, path
    assert (await client.get("/api/v1/users/me", headers=_bearer("garbage"))).status_code == 401

    headers = await _session(client, local_user)
    for path in ("/api/v1/users/me", "/api/v1/items", f"{API}/security"):
        assert (await client.get(path, headers=headers)).status_code == 200, path


async def test_password_change_signs_out_other_sessions(
    client: AsyncClient, db_session: AsyncSession, local_user: User
):
    old = await _session(client, local_user)
    other_device = await _session(client, local_user)

    refused = await client.post(
        f"{API}/password",
        json={"current_password": "wrong password", "new_password": "a brand new password"},
        headers=old,
    )
    assert refused.status_code == 403

    response = await client.post(
        f"{API}/password",
        json={"current_password": PASSWORD, "new_password": "a brand new password"},
        headers=old,
    )

    assert response.status_code == 200
    new = _bearer(response.json()["access_token"])
    assert (await client.get("/api/v1/users/me", headers=old)).status_code == 401
    assert (await client.get("/api/v1/users/me", headers=other_device)).status_code == 401
    assert (await client.get("/api/v1/users/me", headers=new)).status_code == 200
    assert (await _login(client, local_user.email)).status_code == 401
    assert (await _login(client, local_user.email, "a brand new password")).status_code == 200


async def test_local_endpoints_are_off_when_disabled(
    client: AsyncClient, local_user: User, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(get_settings(), "local_auth_enabled", False)
    assert (await _login(client, local_user.email)).status_code == 404
    assert (await client.get(f"{API}/setup")).status_code == 404
    assert (await client.post(f"{API}/passkeys/login/options")).status_code == 404


async def test_auth_config_reports_local_sign_in(client: AsyncClient, local_auth: Settings):
    config = (await client.get(f"{API}/config")).json()
    assert config["local_auth"] is True
    assert config["dev_mode"] is False
    assert (await client.get(f"{API}/status")).json()["mode"] == "local"


async def test_local_sign_in_turns_off_the_open_dev_login(local_auth: Settings):
    assert local_auth.debug is True
    assert local_auth.dev_mode is False


# --- Passkeys --------------------------------------------------------------------------------


async def _register_passkey(
    client: AsyncClient, headers: dict[str, str], authenticator: SoftAuthenticator, name="iPhone"
):
    options = await client.post(
        f"{API}/passkeys/register/options", json={"current_password": PASSWORD}, headers=headers
    )
    assert options.status_code == 200, options.text
    credential = authenticator.register(options.json())
    return await client.post(
        f"{API}/passkeys/register/verify",
        json={"name": name, "credential": credential},
        headers=headers,
    )


async def _passkey_login(client: AsyncClient, authenticator: SoftAuthenticator, **assertion_args):
    options = (await client.post(f"{API}/passkeys/login/options")).json()
    assertion = authenticator.assertion(options["options"], **assertion_args)
    return await client.post(
        f"{API}/passkeys/login/verify",
        json={"flow_id": options["flow_id"], "credential": assertion},
    )


async def test_passkey_registration_stores_only_public_data(
    client: AsyncClient, db_session: AsyncSession, local_user: User
):
    headers = await _session(client, local_user)
    authenticator = SoftAuthenticator()

    response = await _register_passkey(client, headers, authenticator, name="Windows Hello")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Windows Hello"
    assert body["transports"] == ["internal", "hybrid"]
    stored = await db_session.scalar(
        select(WebAuthnCredential).where(WebAuthnCredential.id == UUID(body["id"]))
    )
    assert stored.user_id == local_user.id
    assert stored.credential_id == authenticator.credential_id
    assert stored.sign_count == 0
    # A COSE public key, nothing the authenticator keeps private.
    assert stored.public_key.startswith(b"\xa5")
    overview = (await client.get(f"{API}/security", headers=headers)).json()
    assert [passkey["name"] for passkey in overview["passkeys"]] == ["Windows Hello"]
    assert overview["has_password"] is True


async def test_passkey_registration_options_require_the_password(
    client: AsyncClient, local_user: User
):
    headers = await _session(client, local_user)
    for body in ({}, {"current_password": "wrong password"}):
        response = await client.post(f"{API}/passkeys/register/options", json=body, headers=headers)
        assert response.status_code == 403
    assert (
        await client.post(f"{API}/passkeys/register/options", json={"current_password": PASSWORD})
    ).status_code == 401


async def test_passkey_options_follow_the_relying_party_settings(
    client: AsyncClient, local_user: User, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(get_settings(), "app_url", "https://wardrobe.example.com")
    monkeypatch.setattr(get_settings(), "webauthn_rp_name", "My Wardrobe")
    headers = await _session(client, local_user)

    options = (
        await client.post(
            f"{API}/passkeys/register/options",
            json={"current_password": PASSWORD},
            headers=headers,
        )
    ).json()

    assert options["rp"] == {"name": "My Wardrobe", "id": "wardrobe.example.com"}
    assert options["user"]["name"] == local_user.email
    assert options["authenticatorSelection"]["residentKey"] == "required"
    assert options["authenticatorSelection"]["userVerification"] == "required"
    login = (await client.post(f"{API}/passkeys/login/options")).json()
    assert login["options"]["rpId"] == "wardrobe.example.com"
    assert login["options"]["allowCredentials"] == []


async def test_registration_without_a_pending_challenge_is_refused(
    client: AsyncClient, local_user: User
):
    headers = await _session(client, local_user)
    authenticator = SoftAuthenticator()
    first = await _register_passkey(client, headers, authenticator)
    assert first.status_code == 201

    # The challenge was single-use, so replaying the same response finds nothing to match.
    replay = await client.post(
        f"{API}/passkeys/register/verify",
        json={
            "name": "Again",
            "credential": authenticator.register({"challenge": "x", "user": {"id": "AA"}}),
        },
        headers=headers,
    )
    assert replay.status_code == 400


@pytest.mark.parametrize(
    "tamper",
    [
        {"challenge": "bm90LXRoZS1jaGFsbGVuZ2U"},
        {"origin": "https://evil.example.com"},
        {"rp_id": "evil.example.com"},
    ],
    ids=["wrong-challenge", "wrong-origin", "wrong-rp-id"],
)
async def test_registration_with_a_forged_response_is_refused(
    client: AsyncClient, db_session: AsyncSession, local_user: User, tamper: dict
):
    headers = await _session(client, local_user)
    options = await client.post(
        f"{API}/passkeys/register/options", json={"current_password": PASSWORD}, headers=headers
    )
    credential = SoftAuthenticator().register(options.json(), **tamper)

    response = await client.post(
        f"{API}/passkeys/register/verify",
        json={"name": "Forged", "credential": credential},
        headers=headers,
    )

    assert response.status_code == 400
    assert await _passkey_count(db_session, local_user.id) == 0


async def _passkey_count(db_session: AsyncSession, user_id: UUID) -> int:
    rows = await db_session.execute(
        select(WebAuthnCredential.id).where(WebAuthnCredential.user_id == user_id)
    )
    return len(rows.all())


async def test_passkey_signs_in_and_advances_the_counter(
    client: AsyncClient, db_session: AsyncSession, local_user: User
):
    headers = await _session(client, local_user)
    authenticator = SoftAuthenticator()
    passkey_id = UUID((await _register_passkey(client, headers, authenticator)).json()["id"])

    response = await _passkey_login(client, authenticator)

    assert response.status_code == 200, response.text
    assert response.json()["email"] == local_user.email
    me = await client.get("/api/v1/users/me", headers=_bearer(response.json()["access_token"]))
    assert me.status_code == 200
    stored = await db_session.get(WebAuthnCredential, passkey_id)
    await db_session.refresh(stored)
    assert stored.sign_count == 1
    assert stored.last_used_at is not None


async def test_passkey_login_challenge_is_single_use(client: AsyncClient, local_user: User):
    headers = await _session(client, local_user)
    authenticator = SoftAuthenticator()
    await _register_passkey(client, headers, authenticator)
    options = (await client.post(f"{API}/passkeys/login/options")).json()
    body = {
        "flow_id": options["flow_id"],
        "credential": authenticator.assertion(options["options"]),
    }

    assert (await client.post(f"{API}/passkeys/login/verify", json=body)).status_code == 200
    replay = await client.post(f"{API}/passkeys/login/verify", json=body)
    assert replay.status_code == 401


async def test_passkey_login_with_an_unknown_flow_is_refused(client: AsyncClient, local_user: User):
    headers = await _session(client, local_user)
    authenticator = SoftAuthenticator()
    await _register_passkey(client, headers, authenticator)
    options = (await client.post(f"{API}/passkeys/login/options")).json()

    response = await client.post(
        f"{API}/passkeys/login/verify",
        json={"flow_id": "made-up", "credential": authenticator.assertion(options["options"])},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "assertion_args",
    [
        {"challenge": "bm90LXRoZS1jaGFsbGVuZ2U"},
        {"origin": "https://evil.example.com"},
        {"user_verified": False},
        {"advance_counter": False},
    ],
    ids=["wrong-challenge", "wrong-origin", "no-user-verification", "counter-not-advanced"],
)
async def test_invalid_passkey_assertions_are_refused(
    client: AsyncClient, local_user: User, assertion_args: dict
):
    headers = await _session(client, local_user)
    authenticator = SoftAuthenticator()
    await _register_passkey(client, headers, authenticator)
    # One good sign-in first, so the counter is non-zero and a cloned key's replay shows.
    assert (await _passkey_login(client, authenticator)).status_code == 200

    response = await _passkey_login(client, authenticator, **assertion_args)

    assert response.status_code == 401


async def test_assertion_signed_by_another_key_is_refused(client: AsyncClient, local_user: User):
    headers = await _session(client, local_user)
    authenticator = SoftAuthenticator()
    await _register_passkey(client, headers, authenticator)

    impostor = SoftAuthenticator()
    response = await _passkey_login(client, authenticator, signing_key=impostor.key)

    assert response.status_code == 401


async def test_unregistered_passkey_is_refused(client: AsyncClient, local_auth: Settings):
    stranger = SoftAuthenticator()
    stranger.user_handle = uuid4().bytes
    response = await _passkey_login(client, stranger)
    assert response.status_code == 401


async def test_malformed_passkey_response_is_refused(client: AsyncClient, local_auth: Settings):
    options = (await client.post(f"{API}/passkeys/login/options")).json()
    response = await client.post(
        f"{API}/passkeys/login/verify",
        json={"flow_id": options["flow_id"], "credential": {"id": "x", "response": {}}},
    )
    assert response.status_code == 401


async def test_passkeys_can_be_renamed_and_removed(
    client: AsyncClient, db_session: AsyncSession, local_user: User
):
    headers = await _session(client, local_user)
    phone, laptop = SoftAuthenticator(), SoftAuthenticator()
    phone_id = (await _register_passkey(client, headers, phone, name="iPhone")).json()["id"]
    await _register_passkey(client, headers, laptop, name="MacBook")

    renamed = await client.patch(
        f"{API}/passkeys/{phone_id}", json={"name": "Old iPhone"}, headers=headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Old iPhone"

    refused = await client.request(
        "DELETE",
        f"{API}/passkeys/{phone_id}",
        json={"current_password": "wrong password"},
        headers=headers,
    )
    assert refused.status_code == 403

    removed = await client.request(
        "DELETE", f"{API}/passkeys/{phone_id}", json={"current_password": PASSWORD}, headers=headers
    )
    assert removed.status_code == 204

    names = [
        p["name"] for p in (await client.get(f"{API}/security", headers=headers)).json()["passkeys"]
    ]
    assert names == ["MacBook"]
    assert (await _passkey_login(client, phone)).status_code == 401
    assert (await _passkey_login(client, laptop)).status_code == 200


async def test_another_users_passkey_cannot_be_touched(
    client: AsyncClient, db_session: AsyncSession, local_user: User
):
    owner_headers = await _session(client, local_user)
    passkey_id = (await _register_passkey(client, owner_headers, SoftAuthenticator())).json()["id"]
    other = await _create_local_user(db_session)
    other_headers = await _session(client, other)

    renamed = await client.patch(
        f"{API}/passkeys/{passkey_id}", json={"name": "Mine now"}, headers=other_headers
    )
    removed = await client.request(
        "DELETE",
        f"{API}/passkeys/{passkey_id}",
        json={"current_password": PASSWORD},
        headers=other_headers,
    )

    assert renamed.status_code == removed.status_code == 404


# --- Accounts --------------------------------------------------------------------------------


async def test_administrator_creates_accounts_and_members_cannot(
    client: AsyncClient, db_session: AsyncSession, local_auth: Settings
):
    admin = await _create_local_user(db_session, is_admin=True)
    member = await _create_local_user(db_session)
    admin_headers = await _session(client, admin)
    member_headers = await _session(client, member)
    new_email = f"family-{uuid4()}@example.com"
    body = {"email": new_email, "password": PASSWORD, "current_password": PASSWORD}

    assert (await client.post(f"{API}/users", json=body, headers=member_headers)).status_code == 403
    created = await client.post(f"{API}/users", json=body, headers=admin_headers)
    assert created.status_code == 201, created.text
    assert created.json()["has_password"] is True
    assert (await _login(client, new_email)).status_code == 200
    assert (await client.post(f"{API}/users", json=body, headers=admin_headers)).status_code == 409


async def test_root_health_endpoint(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_webauthn_settings_default_to_app_url():
    settings = Settings(local_auth_enabled=True, app_url="https://wardrobe.example.com/")
    assert settings.webauthn_origins == ["https://wardrobe.example.com"]
    assert settings.effective_webauthn_rp_id == "wardrobe.example.com"
    assert settings.webauthn_problem() is None


def test_webauthn_settings_report_problems():
    assert (
        "HTTPS"
        in Settings(local_auth_enabled=True, app_url="http://192.168.1.10:30300").webauthn_problem()
    )
    mismatch = Settings(
        local_auth_enabled=True,
        webauthn_origin="https://wardrobe.example.com",
        webauthn_rp_id="other.example.com",
    )
    assert "WEBAUTHN_RP_ID" in mismatch.webauthn_problem()
    parent = Settings(
        local_auth_enabled=True,
        webauthn_origin="https://wardrobe.example.com,https://closet.example.com",
        webauthn_rp_id="example.com",
    )
    assert parent.webauthn_problem() is None


async def _column_exists(db_session: AsyncSession, table: str, column: str) -> bool:
    return bool(
        await db_session.scalar(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        )
    )


async def test_migration_is_reversible_and_keeps_accounts(db_session: AsyncSession):
    user = User(email=f"keep-{uuid4()}@example.com", display_name="Keep", email_verified=True)
    db_session.add(user)
    await db_session.commit()

    async with migration_downgrade(db_session, "a7d3c9e1f5b2"):
        assert not await _column_exists(db_session, "users", "password_hash")
        assert not await _column_exists(db_session, "webauthn_credentials", "public_key")
        kept = await db_session.scalar(
            text("SELECT email FROM users WHERE id = :id"), {"id": user.id}
        )
        assert kept == user.email

    assert await _column_exists(db_session, "users", "password_hash")
    assert await _column_exists(db_session, "webauthn_credentials", "public_key")
