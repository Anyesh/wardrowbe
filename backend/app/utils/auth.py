from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.database import DbSession
from app.models.user import User
from app.schemas.auth import AuthSession, TokenPayload
from app.services.user_service import FORWARD_AUTH, UserService
from app.utils.errors import CodedHTTPException
from app.utils.forward_auth import (
    FORWARD_AUTH_SECRET_HEADER,
    forward_auth_secret_matches,
    proxy_header,
    single_header,
)

settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)
BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


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
        raise CodedHTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "AUTH_TOKEN_INVALID",
            "Invalid or expired token",
            headers=BEARER_CHALLENGE,
        ) from None
    except Exception:
        raise CodedHTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "AUTH_TOKEN_INVALID",
            "Invalid or expired token",
            headers=BEARER_CHALLENGE,
        ) from None


async def get_current_user_optional(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> User | None:
    if not credentials:
        return None

    try:
        token_data = decode_token(credentials.credentials)
        user_service = UserService(db)
        user = await user_service.get_by_token(token_data)
    except HTTPException:
        return None
    # A deactivated account or a switched proxy user is treated as anonymous, as
    # get_current_user refuses both.
    if user is None or not user.is_active:
        return None
    if await _proxy_user_switched(request, user, user_service):
        return None
    return user


# The browser reaches /api/v1 straight through nginx or the ingress, past the frontend middleware
# that ends a session when the proxy user changes, so a request the proxy vouched for is checked here.
async def _proxy_user_switched(request: Request, user: User, user_service: UserService) -> bool:
    presented_secret = single_header(request.headers, FORWARD_AUTH_SECRET_HEADER)
    if not forward_auth_secret_matches(presented_secret, settings.forward_auth_secret):
        return False
    remote_user = proxy_header(request.headers, "Remote-User")
    return bool(remote_user) and not await user_service.holds_identity(
        user.id, FORWARD_AUTH, remote_user
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> User:
    user_service = UserService(db)
    user = None

    if credentials:
        token_data = decode_token(credentials.credentials)
        user = await user_service.get_by_token(token_data)

    if not user:
        raise CodedHTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "NOT_AUTHENTICATED",
            "Not authenticated",
            headers=BEARER_CHALLENGE,
        )

    if await _proxy_user_switched(request, user, user_service):
        raise CodedHTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "PROXY_USER_CHANGED",
            "The signed-in user changed at the proxy. Sign in again.",
            headers=BEARER_CHALLENGE,
        )

    if not user.is_active:
        raise CodedHTTPException(
            status.HTTP_403_FORBIDDEN, "ACCOUNT_INACTIVE", "User account is inactive"
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
