from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.database import DbSession
from app.models.user import User
from app.schemas.auth import AuthSession, TokenPayload
from app.services.user_service import UserService
from app.utils.forward_auth import (
    FORWARD_AUTH_SECRET_HEADER,
    forward_auth_secret_matches,
    proxy_header,
)

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


async def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> User | None:
    if not credentials:
        return None

    try:
        token_data = decode_token(credentials.credentials)
        user_service = UserService(db)
        return await user_service.get_by_external_id(token_data.sub)
    except HTTPException:
        return None


# The browser reaches /api/v1 straight through nginx or the ingress, past the frontend middleware
# that ends a session when the proxy user changes, so a request the proxy vouched for is checked here.
def _reject_proxy_user_switch(request: Request, user: User) -> None:
    presented_secret = request.headers.get(FORWARD_AUTH_SECRET_HEADER)
    if not forward_auth_secret_matches(presented_secret, settings.forward_auth_secret):
        return
    remote_user = proxy_header(request.headers, "Remote-User")
    if remote_user and remote_user != user.external_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The signed-in user changed at the proxy. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
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
        user = await user_service.get_by_external_id(token_data.sub)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _reject_proxy_user_switch(request, user)

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
