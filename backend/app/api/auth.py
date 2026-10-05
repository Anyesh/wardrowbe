from datetime import datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.config import NO_AUTH_CONFIGURED_MESSAGE, get_settings
from app.database import DbSession
from app.models.user import User
from app.schemas.email import normalise_email
from app.schemas.user import (
    AuthConfigOIDC,
    AuthConfigResponse,
    AuthStatusResponse,
    UserResponse,
    UserSyncRequest,
    UserSyncResponse,
)
from app.services.user_service import UserEmailConflictError, UserService
from app.utils.auth import get_current_user
from app.utils.forward_auth import (
    FORWARD_AUTH_SECRET_HEADER,
    forward_auth_secret_matches,
    proxy_header,
)
from app.utils.oidc import validate_oidc_id_token
from app.utils.rate_limit import rate_limit_by_ip

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


def create_access_token(external_id: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=7)
    to_encode = {
        "sub": external_id,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm="HS256")


MOBILE_APP_SCHEME = "wardrowbe"
FORWARD_AUTH_ONLY_MOBILE_NOTICE = (
    "Forward-auth signs in browsers only. The mobile app needs OIDC: "
    "set OIDC_ISSUER_URL and OIDC_CLIENT_ID alongside FORWARD_AUTH_SECRET."
)
SYNC_RATE_LIMIT = ("auth_sync", 10, 60)


@router.get("/mobile-callback")
async def mobile_oidc_callback(request: Request) -> RedirectResponse:
    params = dict(request.query_params)
    target = f"{MOBILE_APP_SCHEME}://auth/callback"
    if params:
        target = f"{target}?{urlencode(params)}"
    return RedirectResponse(url=target, status_code=302)


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config() -> AuthConfigResponse:
    oidc_enabled = settings.oidc_configured
    forward_auth = settings.forward_auth_configured
    return AuthConfigResponse(
        oidc=AuthConfigOIDC(
            enabled=oidc_enabled,
            issuer_url=settings.oidc_issuer_url if oidc_enabled else None,
            client_id=(settings.oidc_mobile_client_id or settings.oidc_client_id)
            if oidc_enabled
            else None,
        ),
        dev_mode=settings.dev_mode,
        forward_auth=forward_auth,
        mobile_notice=FORWARD_AUTH_ONLY_MOBILE_NOTICE
        if forward_auth and not oidc_enabled
        else None,
    )


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status() -> AuthStatusResponse:
    mode = settings.get_auth_mode()
    if mode == "unknown":
        return AuthStatusResponse(
            configured=False,
            mode=mode,
            error=NO_AUTH_CONFIGURED_MESSAGE,
        )
    return AuthStatusResponse(configured=True, mode=mode)


def _invalid_email_claim() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The OIDC provider sent an email claim that is not a valid email address",
    )


def _claims_email(oidc_claims: dict) -> str | None:
    raw_email = oidc_claims.get("email")
    if raw_email is None or (isinstance(raw_email, str) and not raw_email.strip()):
        return None
    if not isinstance(raw_email, str):
        raise _invalid_email_claim()
    try:
        return normalise_email(raw_email)
    except ValueError:
        raise _invalid_email_claim() from None


async def _forward_auth_identity(request: Request, presented_secret: str) -> UserSyncRequest:
    if not forward_auth_secret_matches(presented_secret, settings.forward_auth_secret):
        # Only failures count, because browser sign-ins can all arrive from the frontend
        # container's IP, and limiting successes would lock every user out together.
        await rate_limit_by_ip(request, *SYNC_RATE_LIMIT)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid forward-auth secret",
        )

    remote_user = proxy_header(request.headers, "Remote-User")
    remote_email = proxy_header(request.headers, "Remote-Email")
    if not remote_user or not remote_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The auth proxy must send Remote-User and Remote-Email headers",
        )

    display_name = proxy_header(request.headers, "Remote-Name") or remote_user
    try:
        return UserSyncRequest(
            external_id=remote_user,
            email=remote_email,
            display_name=display_name,
        )
    except ValidationError as e:
        if any(error["loc"] == ("external_id",) for error in e.errors()):
            detail = "The auth proxy sent a Remote-User longer than 255 characters"
        else:
            detail = "The auth proxy sent a Remote-Email that is not a valid email address"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from None


async def _oidc_identity(sync_data: UserSyncRequest) -> tuple[UserSyncRequest, bool]:
    if not sync_data.id_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC id_token is required for authentication",
        )

    valid_audiences = [settings.oidc_client_id]
    if settings.oidc_mobile_client_id and settings.oidc_mobile_client_id != settings.oidc_client_id:
        valid_audiences.append(settings.oidc_mobile_client_id)

    try:
        oidc_claims = await validate_oidc_id_token(
            sync_data.id_token,
            settings.oidc_issuer_url,
            valid_audiences,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from None

    if oidc_claims.get("sub") != sync_data.external_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject does not match external_id",
        )

    claims_email = _claims_email(oidc_claims)
    if sync_data.email:
        request_email = sync_data.email
        if claims_email and claims_email != request_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token email does not match request email",
            )
        effective_email = request_email
    elif claims_email:
        effective_email = claims_email
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email provided by OIDC provider. Configure your provider to include the email claim.",
        )

    # Validated again rather than copied so the blank-name fallback sees the token's email.
    sync_data = UserSyncRequest.model_validate({**sync_data.model_dump(), "email": effective_email})
    verified_claim = oidc_claims.get("email_verified")
    email_verified = (
        bool(claims_email)
        and claims_email == effective_email
        # Apple sends the claim as the string "true"; nothing else counts as verified.
        and (verified_claim is True or verified_claim == "true")
    )
    return sync_data, email_verified


async def _body_identity(sync_data: UserSyncRequest | None) -> tuple[UserSyncRequest, bool]:
    if sync_data is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request body is required",
        )
    if settings.dev_mode:
        if not sync_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="email is required",
            )
        return sync_data, True
    if settings.oidc_configured:
        return await _oidc_identity(sync_data)
    if settings.forward_auth_configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in through the forward-auth proxy",
        )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="No authentication method configured",
    )


@router.post("/sync", response_model=UserSyncResponse)
async def sync_user(
    request: Request,
    db: DbSession,
    sync_data: UserSyncRequest | None = None,
) -> UserSyncResponse:
    presented_secret = request.headers.get(FORWARD_AUTH_SECRET_HEADER)
    # The mobile app cannot pass the proxy's login, so a route that skips the auth check but
    # still adds the secret delivers an OIDC sync with no Remote-User; the token alone proves it.
    oidc_sync_through_proxy = (
        sync_data is not None
        and bool(sync_data.id_token)
        and settings.oidc_configured
        and not request.headers.get("Remote-User")
    )
    if presented_secret is not None and not oidc_sync_through_proxy:
        sync_data = await _forward_auth_identity(request, presented_secret)
        email_verified = True
    else:
        await rate_limit_by_ip(request, *SYNC_RATE_LIMIT)
        sync_data, email_verified = await _body_identity(sync_data)

    try:
        user, is_new = await UserService(db).sync_from_oidc(
            sync_data, email_verified=email_verified
        )
    except UserEmailConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from None

    return UserSyncResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_new_user=is_new,
        onboarding_completed=user.onboarding_completed,
        access_token=create_access_token(user.external_id),
    )


@router.get("/session", response_model=UserResponse)
async def get_session(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse.model_validate(current_user)
