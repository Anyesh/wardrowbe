import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.auth import create_access_token
from app.config import get_settings
from app.database import DbSession
from app.models.user import User
from app.schemas.auth import TokenPayload
from app.schemas.email import normalise_email
from app.schemas.local_auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    CreateLocalUserRequest,
    LocalUserResponse,
    LoginRequest,
    PasskeyLoginOptionsResponse,
    PasskeyLoginVerifyRequest,
    PasskeyRegistrationVerifyRequest,
    PasskeyRenameRequest,
    PasskeyResponse,
    ReauthRequest,
    SecurityOverviewResponse,
    SetupRequest,
    SetupStatusResponse,
)
from app.schemas.user import UserSyncResponse
from app.services.local_auth_service import (
    LocalAuthService,
    LocalEmailInUseError,
    SetupAlreadyDoneError,
)
from app.services.passkey_service import (
    ChallengeStoreUnavailableError,
    PasskeyError,
    PasskeyService,
)
from app.utils.auth import CurrentToken, CurrentUser
from app.utils.passwords import verify_password
from app.utils.rate_limit import (
    check_rate_limit,
    clear_failures,
    failures_exceeded,
    rate_limit_by_ip,
    record_failure,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()

INVALID_CREDENTIALS = "Invalid email or password."
LOGIN_RATE_LIMIT = ("local_login", 20, 60)
SETUP_RATE_LIMIT = ("local_setup", 5, 60)
PASSKEY_OPTIONS_RATE_LIMIT = ("passkey_options", 30, 60)
PASSKEY_LOGIN_RATE_LIMIT = ("passkey_login", 20, 60)
ACCOUNT_FAILURE_LIMIT = 10
ACCOUNT_FAILURE_WINDOW_SECONDS = 15 * 60
REAUTH_LIMIT = 10
REAUTH_WINDOW_SECONDS = 15 * 60
# An account without a password (signed in through OIDC) proves a sensitive change by having
# signed in this recently instead.
RECENT_SIGN_IN = timedelta(minutes=10)


def require_local_auth() -> None:
    if not settings.local_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Built-in sign-in is disabled on this server (LOCAL_AUTH_ENABLED=false).",
        )


LocalAuth = Depends(require_local_auth)


def _session_token(user_id: UUID, identity_id: UUID) -> str:
    return create_access_token(
        user_id, identity_id, expires_delta=timedelta(hours=settings.session_lifetime_hours)
    )


def _signed_in(user: User, identity_id: UUID, *, is_new: bool = False) -> UserSyncResponse:
    return UserSyncResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_new_user=is_new,
        onboarding_completed=user.onboarding_completed,
        access_token=_session_token(user.id, identity_id),
    )


def _account_failure_key(email: str) -> str:
    # Hashed so that Redis never holds the addresses people tried.
    try:
        normalised = normalise_email(email)
    except ValueError:
        normalised = email.strip().lower()
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
    return f"rate_limit:local_login_fail:email:{digest}"


async def _require_reauth(user: User, token: TokenPayload, current_password: str | None) -> None:
    await check_rate_limit(f"rate_limit:reauth:user:{user.id}", REAUTH_LIMIT, REAUTH_WINDOW_SECONDS)
    if user.password_hash is not None:
        if current_password is None or not await verify_password(
            user.password_hash, current_password
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Current password is incorrect.",
            )
        return
    issued = datetime.fromtimestamp(token.iat, UTC) if token.iat else None
    if issued is None or datetime.now(UTC) - issued > RECENT_SIGN_IN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sign out and sign in again to make this change.",
        )


def _passkey_failure(error: Exception) -> HTTPException:
    if isinstance(error, ChallengeStoreUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Passkeys are temporarily unavailable. Try again shortly.",
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


# --- First run -------------------------------------------------------------------------------


@router.get("/setup", response_model=SetupStatusResponse, dependencies=[LocalAuth])
async def setup_status(db: DbSession) -> SetupStatusResponse:
    return SetupStatusResponse(required=await LocalAuthService(db).setup_required())


@router.post(
    "/setup",
    response_model=UserSyncResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[LocalAuth],
)
async def complete_setup(request: Request, data: SetupRequest, db: DbSession) -> UserSyncResponse:
    await rate_limit_by_ip(request, *SETUP_RATE_LIMIT)
    try:
        user, identity_id = await LocalAuthService(db).create_first_admin(
            data.email, data.password, data.display_name
        )
    except SetupAlreadyDoneError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Setup is already complete. Sign in instead.",
        ) from None
    return _signed_in(user, identity_id, is_new=True)


# --- Email + password ------------------------------------------------------------------------


@router.post("/login", response_model=UserSyncResponse, dependencies=[LocalAuth])
async def login(request: Request, data: LoginRequest, db: DbSession) -> UserSyncResponse:
    await rate_limit_by_ip(request, *LOGIN_RATE_LIMIT)
    failure_key = _account_failure_key(data.email)
    if await failures_exceeded(failure_key, ACCOUNT_FAILURE_LIMIT):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again in a few minutes.",
        )
    service = LocalAuthService(db)
    user = await service.authenticate(data.email, data.password)
    if user is None:
        await record_failure(failure_key, ACCOUNT_FAILURE_WINDOW_SECONDS)
        # One message for an unknown address, a wrong password and a disabled account, so the
        # response says nothing about which accounts exist.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)
    await clear_failures(failure_key)
    identity_id = await service.sign_in(user)
    return _signed_in(user, identity_id)


@router.post("/password", response_model=AccessTokenResponse, dependencies=[LocalAuth])
async def change_password(
    data: ChangePasswordRequest, user: CurrentUser, token: CurrentToken, db: DbSession
) -> AccessTokenResponse:
    await _require_reauth(user, token, data.current_password)
    identity_id = await LocalAuthService(db).set_password(user, data.new_password)
    # Every other local session ended with the old identity; this one carries on with a new token.
    return AccessTokenResponse(access_token=_session_token(user.id, identity_id))


# --- Account overview ------------------------------------------------------------------------


@router.get("/security", response_model=SecurityOverviewResponse)
async def security_overview(user: CurrentUser, db: DbSession) -> SecurityOverviewResponse:
    passkeys = await PasskeyService(db).list_for_user(user.id)
    return SecurityOverviewResponse(
        email=user.email,
        local_auth_enabled=settings.local_auth_enabled,
        has_password=user.password_hash is not None,
        is_admin=user.is_admin,
        passkeys=[PasskeyResponse.model_validate(passkey) for passkey in passkeys],
    )


# --- Passkeys --------------------------------------------------------------------------------


@router.post("/passkeys/register/options", dependencies=[LocalAuth])
async def passkey_registration_options(
    data: ReauthRequest, user: CurrentUser, token: CurrentToken, db: DbSession
) -> dict:
    # Re-authenticated, because a passkey added from a stolen session would outlive it.
    await _require_reauth(user, token, data.current_password)
    try:
        return await PasskeyService(db).registration_options(user)
    except (PasskeyError, ChallengeStoreUnavailableError) as e:
        raise _passkey_failure(e) from None


@router.post(
    "/passkeys/register/verify",
    response_model=PasskeyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[LocalAuth],
)
async def passkey_registration_verify(
    data: PasskeyRegistrationVerifyRequest, user: CurrentUser, db: DbSession
) -> PasskeyResponse:
    try:
        passkey = await PasskeyService(db).register(user, data.name, data.credential)
    except (PasskeyError, ChallengeStoreUnavailableError) as e:
        raise _passkey_failure(e) from None
    return PasskeyResponse.model_validate(passkey)


@router.patch("/passkeys/{passkey_id}", response_model=PasskeyResponse)
async def rename_passkey(
    passkey_id: UUID, data: PasskeyRenameRequest, user: CurrentUser, db: DbSession
) -> PasskeyResponse:
    passkey = await PasskeyService(db).get_for_user(user.id, passkey_id)
    if passkey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")
    passkey.name = data.name
    await db.flush()
    return PasskeyResponse.model_validate(passkey)


@router.delete("/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_passkey(
    passkey_id: UUID, data: ReauthRequest, user: CurrentUser, token: CurrentToken, db: DbSession
) -> Response:
    passkey = await PasskeyService(db).get_for_user(user.id, passkey_id)
    if passkey is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Passkey not found")
    await _require_reauth(user, token, data.current_password)
    await db.delete(passkey)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/passkeys/login/options", response_model=PasskeyLoginOptionsResponse, dependencies=[LocalAuth]
)
async def passkey_login_options(request: Request, db: DbSession) -> PasskeyLoginOptionsResponse:
    await rate_limit_by_ip(request, *PASSKEY_OPTIONS_RATE_LIMIT)
    try:
        flow_id, options = await PasskeyService(db).authentication_options()
    except ChallengeStoreUnavailableError as e:
        raise _passkey_failure(e) from None
    return PasskeyLoginOptionsResponse(flow_id=flow_id, options=options)


@router.post("/passkeys/login/verify", response_model=UserSyncResponse, dependencies=[LocalAuth])
async def passkey_login_verify(
    request: Request, data: PasskeyLoginVerifyRequest, db: DbSession
) -> UserSyncResponse:
    await rate_limit_by_ip(request, *PASSKEY_LOGIN_RATE_LIMIT)
    try:
        user = await PasskeyService(db).authenticate(data.flow_id, data.credential)
    except PasskeyError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from None
    except ChallengeStoreUnavailableError as e:
        raise _passkey_failure(e) from None
    identity_id = await LocalAuthService(db).sign_in(user)
    return _signed_in(user, identity_id)


# --- Accounts (administrators) ---------------------------------------------------------------


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an administrator can manage accounts.",
        )


def _local_user(user: User) -> LocalUserResponse:
    return LocalUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=bool(user.is_active),
        has_password=user.password_hash is not None,
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[LocalUserResponse], dependencies=[LocalAuth])
async def list_accounts(user: CurrentUser, db: DbSession) -> list[LocalUserResponse]:
    _require_admin(user)
    return [_local_user(account) for account in await LocalAuthService(db).list_users()]


@router.post(
    "/users",
    response_model=LocalUserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[LocalAuth],
)
async def create_account(
    data: CreateLocalUserRequest,
    user: CurrentUser,
    token: CurrentToken,
    db: DbSession,
) -> LocalUserResponse:
    _require_admin(user)
    await _require_reauth(user, token, data.current_password)
    try:
        account, _ = await LocalAuthService(db).create_user(
            data.email, data.password, data.display_name, is_admin=data.is_admin
        )
    except LocalEmailInUseError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from None
    await db.refresh(account)
    return _local_user(account)
