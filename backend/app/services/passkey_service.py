import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import parse_authentication_credential_json
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import Settings, get_settings
from app.models.user import User
from app.models.webauthn import WebAuthnCredential

logger = logging.getLogger(__name__)
T = TypeVar("T")

# Long enough to unlock a phone or touch a security key, short enough that a leaked challenge is
# useless soon after.
CHALLENGE_TTL_SECONDS = 300
CEREMONY_TIMEOUT_MS = 120_000
REGISTER_KEY = "webauthn:register:{}"
LOGIN_KEY = "webauthn:login:{}"
MAX_PASSKEYS_PER_USER = 20
_KNOWN_TRANSPORTS = {transport.value for transport in AuthenticatorTransport}


class PasskeyError(Exception):
    """A ceremony that cannot succeed; the message is safe to show."""


class ChallengeStoreUnavailableError(Exception):
    pass


class ChallengeStore:
    """Single-use challenges in Redis: GETDEL hands each one out exactly once."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def put(self, key: str, challenge: bytes) -> None:
        await self._run(lambda redis: redis.set(key, challenge, ex=CHALLENGE_TTL_SECONDS))

    async def pop(self, key: str) -> bytes | None:
        return await self._run(lambda redis: redis.getdel(key))

    async def _run(self, operation: Callable[[Redis], Awaitable[T]]) -> T:
        try:
            redis = Redis.from_url(self.settings.redis_url)
            try:
                return await operation(redis)
            finally:
                await redis.aclose()
        except Exception as e:
            logger.warning("Passkey challenge store unavailable: %s", e)
            raise ChallengeStoreUnavailableError from e


class PasskeyService:
    def __init__(self, db: AsyncSession, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.challenges = ChallengeStore(self.settings)

    async def list_for_user(self, user_id: UUID) -> list[WebAuthnCredential]:
        result = await self.db.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user_id)
            .order_by(WebAuthnCredential.created_at)
        )
        return list(result.scalars())

    async def get_for_user(self, user_id: UUID, passkey_id: UUID) -> WebAuthnCredential | None:
        return await self.db.scalar(
            select(WebAuthnCredential).where(
                WebAuthnCredential.id == passkey_id, WebAuthnCredential.user_id == user_id
            )
        )

    async def registration_options(self, user: User) -> dict[str, Any]:
        existing = await self.list_for_user(user.id)
        if len(existing) >= MAX_PASSKEYS_PER_USER:
            raise PasskeyError("This account already has the maximum number of passkeys.")
        options = generate_registration_options(
            rp_id=self.settings.effective_webauthn_rp_id,
            rp_name=self.settings.effective_webauthn_rp_name,
            # The user handle is the account id: stable, unique and free of personal data.
            user_id=user.id.bytes,
            user_name=user.email,
            user_display_name=user.display_name,
            timeout=CEREMONY_TIMEOUT_MS,
            # A discoverable credential lets the login page ask for a passkey without an email.
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=passkey.credential_id) for passkey in existing
            ],
        )
        await self.challenges.put(REGISTER_KEY.format(user.id), options.challenge)
        return json.loads(options_to_json(options))

    async def register(
        self, user: User, name: str, credential: dict[str, Any]
    ) -> WebAuthnCredential:
        challenge = await self.challenges.pop(REGISTER_KEY.format(user.id))
        if challenge is None:
            raise PasskeyError("The passkey request expired. Try again.")
        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=self.settings.effective_webauthn_rp_id,
                expected_origin=self.settings.webauthn_origins,
                require_user_verification=True,
            )
        except (WebAuthnException, ValueError, KeyError, TypeError) as e:
            logger.info("Passkey registration refused for user %s: %s", user.id, e)
            raise PasskeyError("The passkey could not be verified.") from None

        taken = await self.db.scalar(
            select(WebAuthnCredential.id).where(
                WebAuthnCredential.credential_id == verified.credential_id
            )
        )
        if taken is not None:
            raise PasskeyError("This passkey is already registered.")

        response = credential.get("response")
        raw_transports = response.get("transports") if isinstance(response, dict) else None
        transports = [
            transport
            for transport in (raw_transports if isinstance(raw_transports, list) else [])
            if transport in _KNOWN_TRANSPORTS
        ]
        passkey = WebAuthnCredential(
            user_id=user.id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports=transports,
            backed_up=verified.credential_backed_up,
            name=name,
        )
        self.db.add(passkey)
        await self.db.flush()
        await self.db.refresh(passkey)
        return passkey

    async def authentication_options(self) -> tuple[str, dict[str, Any]]:
        options = generate_authentication_options(
            rp_id=self.settings.effective_webauthn_rp_id,
            timeout=CEREMONY_TIMEOUT_MS,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        # The flow id, not the challenge, names the stored entry, so a client cannot pick which
        # challenge its response is checked against.
        flow_id = secrets.token_urlsafe(24)
        await self.challenges.put(LOGIN_KEY.format(flow_id), options.challenge)
        return flow_id, json.loads(options_to_json(options))

    async def authenticate(self, flow_id: str, credential: dict[str, Any]) -> User:
        challenge = await self.challenges.pop(LOGIN_KEY.format(flow_id))
        if challenge is None:
            raise PasskeyError("The passkey request expired. Try again.")
        try:
            parsed = parse_authentication_credential_json(credential)
        except (WebAuthnException, ValueError, KeyError, TypeError):
            raise PasskeyError("The passkey could not be verified.") from None

        passkey = await self.db.scalar(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.credential_id == parsed.raw_id)
            .with_for_update()
        )
        if passkey is None:
            raise PasskeyError("This passkey is not registered with Wardrowbe.")
        user_handle = parsed.response.user_handle
        if user_handle is not None and user_handle != passkey.user_id.bytes:
            raise PasskeyError("The passkey could not be verified.")

        try:
            verified = verify_authentication_response(
                credential=parsed,
                expected_challenge=challenge,
                expected_rp_id=self.settings.effective_webauthn_rp_id,
                expected_origin=self.settings.webauthn_origins,
                credential_public_key=passkey.public_key,
                # A counter that fails to advance means a cloned authenticator; py_webauthn
                # refuses it whenever either side reports a non-zero count.
                credential_current_sign_count=passkey.sign_count,
                require_user_verification=True,
            )
        except (WebAuthnException, ValueError, KeyError, TypeError) as e:
            logger.info("Passkey sign-in refused for credential %s: %s", passkey.id, e)
            raise PasskeyError("The passkey could not be verified.") from None

        passkey.sign_count = verified.new_sign_count
        passkey.backed_up = verified.credential_backed_up
        passkey.last_used_at = datetime.now(UTC)
        user = await self.db.get(User, passkey.user_id)
        if user is None or not user.is_active:
            raise PasskeyError("The passkey could not be verified.")
        await self.db.flush()
        return user
