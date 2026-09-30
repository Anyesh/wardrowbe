from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import AuthSession, TokenPayload
from app.services.api_key_service import API_KEY_PREFIX, ApiKeyService
from app.services.user_service import UserService

settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)


def decode_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        return TokenPayload(**payload)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def _required_api_key_scope(request: Request) -> str | None:
    path = request.url.path
    if request.method == "GET":
        if path == "/api/v1/items" or path.startswith("/api/v1/items/"):
            return "items:read"
        if path.startswith("/api/v1/images/"):
            return "images:read"
        return None
    if request.method == "PATCH" and path.startswith("/api/v1/items/"):
        parts = path.removeprefix("/api/v1/items/").split("/")
        if len(parts) != 1:
            return None
        try:
            UUID(parts[0])
        except ValueError:
            return None
        return "items:write"
    return None


async def _resolve_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    *,
    suppress_jwt_errors: bool,
) -> User | None:
    if not credentials:
        return None

    token = credentials.credentials
    if token.startswith(API_KEY_PREFIX):
        required_scope = _required_api_key_scope(request)
        if required_scope is None:
            return None
        authenticated = await ApiKeyService(db).authenticate_with_key(token, required_scope)
        if authenticated is None:
            return None
        user, api_key = authenticated
        request.state.api_key_scopes = frozenset(api_key.scopes)
        return user

    request.state.api_key_scopes = None
    try:
        token_data = decode_token(token)
    except HTTPException:
        if suppress_jwt_errors:
            return None
        raise
    return await UserService(db).get_by_external_id(token_data.sub)


def can_include_signed_image_urls(request: Request) -> bool:
    api_key_scopes = getattr(request.state, "api_key_scopes", None)
    return api_key_scopes is None or "images:read" in api_key_scopes


def require_api_key_scope(required_scope: str):
    async def dependency(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        if not credentials or not credentials.credentials.startswith(API_KEY_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Scoped API key required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = await ApiKeyService(db).authenticate(credentials.credentials, required_scope)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid API key or missing {required_scope} scope",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user

    return dependency


async def get_current_user_optional(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    return await _resolve_user(request, credentials, db, suppress_jwt_errors=True)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    user = await _resolve_user(request, credentials, db, suppress_jwt_errors=False)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


async def get_current_session(
    user: Annotated[User, Depends(get_current_user)],
) -> AuthSession:
    return AuthSession(
        user_id=user.id,
        external_id=user.external_id,
        email=user.email,
        display_name=user.display_name,
        family_id=user.family_id,
        role=user.role,
    )


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]
CurrentSession = Annotated[AuthSession, Depends(get_current_session)]
WriteUser = CurrentUser
