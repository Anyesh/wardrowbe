from datetime import datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DEFAULT_SECRET_KEY, get_settings
from app.database import get_db
from app.models.user import User
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


def _is_dev_mode() -> bool:
    return settings.debug and settings.secret_key == DEFAULT_SECRET_KEY


def _oidc_configured() -> bool:
    return bool(settings.oidc_issuer_url and settings.oidc_client_id)


MOBILE_APP_SCHEME = "wardrowbe"


@router.get("/mobile-callback")
async def mobile_oidc_callback(request: Request) -> RedirectResponse:
    params = dict(request.query_params)
    target = f"{MOBILE_APP_SCHEME}://auth/callback"
    if params:
        target = f"{target}?{urlencode(params)}"
    return RedirectResponse(url=target, status_code=302)


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config() -> AuthConfigResponse:
    oidc_enabled = _oidc_configured()
    return AuthConfigResponse(
        oidc=AuthConfigOIDC(
            enabled=oidc_enabled,
            issuer_url=settings.oidc_issuer_url if oidc_enabled else None,
            client_id=(settings.oidc_mobile_client_id or settings.oidc_client_id)
            if oidc_enabled
            else None,
        ),
        dev_mode=_is_dev_mode(),
    )


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status() -> AuthStatusResponse:
    mode = settings.get_auth_mode()
    if mode == "unknown":
        return AuthStatusResponse(
            configured=False,
            mode=mode,
            error=(
                "No authentication method configured. "
                "Set OIDC_ISSUER_URL + OIDC_CLIENT_ID, or enable DEBUG mode."
            ),
        )
    return AuthStatusResponse(configured=True, mode=mode)


@router.post("/sync", response_model=UserSyncResponse)
async def sync_user(
    request: Request,
    sync_data: UserSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSyncResponse:
    await rate_limit_by_ip(request, "auth_sync", 10, 60)
    if _is_dev_mode():
        if not sync_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="email is required",
            )
    elif _oidc_configured():
        if not sync_data.id_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OIDC id_token is required for authentication",
            )

        valid_audiences = [settings.oidc_client_id]
        if (
            settings.oidc_mobile_client_id
            and settings.oidc_mobile_client_id != settings.oidc_client_id
        ):
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

        claims_email = oidc_claims.get("email", "").lower().strip()
        if sync_data.email:
            request_email = sync_data.email.lower().strip()
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

        sync_data = sync_data.model_copy(update={"email": effective_email})

        # Check provider migration: different external_id, same email requires verified email
        user_service_check = UserService(db)
        existing_user = await user_service_check.get_by_email(effective_email)
        if existing_user and existing_user.external_id != sync_data.external_id:
            if oidc_claims.get("email_verified") is not True:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already associated with another account. Verified email required for migration.",
                )
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No authentication method configured",
        )

    user_service = UserService(db)

    try:
        user, is_new = await user_service.sync_from_oidc(sync_data)
    except UserEmailConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from None

    access_token = create_access_token(user.external_id)

    return UserSyncResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_new_user=is_new,
        onboarding_completed=user.onboarding_completed,
        access_token=access_token,
    )


@router.get("/session", response_model=UserResponse)
async def get_session(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse.model_validate(current_user)
