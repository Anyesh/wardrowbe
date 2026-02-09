from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DEFAULT_SECRET_KEY, get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserSyncRequest, UserSyncResponse
from app.services.user_service import UserEmailConflictError, UserService
from app.utils.auth import get_current_user
from app.utils.oidc import validate_oidc_id_token

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


@router.post("/sync", response_model=UserSyncResponse)
async def sync_user(
    sync_data: UserSyncRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSyncResponse:
    if _is_dev_mode():
        pass
    elif _oidc_configured():
        if not sync_data.id_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OIDC id_token is required for authentication",
            )

        try:
            oidc_claims = await validate_oidc_id_token(
                sync_data.id_token,
                settings.oidc_issuer_url,
                settings.oidc_client_id,
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
    elif settings.auth_trust_header:
        pass
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
