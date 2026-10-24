from contextvars import ContextVar

from fastapi import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings
from app.schemas.auth import TokenPayload
from app.utils.auth import decode_token

# MCP tools never see the HTTP request, so the authenticated token reaches them this way.
current_token: ContextVar[TokenPayload | None] = ContextVar("mcp_current_token", default=None)

_NOT_FOUND = b'{"detail":"Not Found"}'
_NOT_AUTHENTICATED = b'{"detail":"Not authenticated"}'


class MCPAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not get_settings().mcp_enabled:
            await _respond(send, 404, _NOT_FOUND)
            return
        token = _bearer_token(scope)
        if token is None:
            await _respond(send, 401, _NOT_AUTHENTICATED, challenge=True)
            return
        try:
            payload = decode_token(token)
        except HTTPException:
            await _respond(send, 401, _NOT_AUTHENTICATED, challenge=True)
            return
        reset = current_token.set(payload)
        try:
            await self.app(scope, receive, send)
        finally:
            current_token.reset(reset)


def _bearer_token(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            scheme, _, param = value.decode("latin-1").partition(" ")
            if scheme.lower() == "bearer" and param.strip():
                return param.strip()
            return None
    return None


async def _respond(send: Send, status: int, body: bytes, challenge: bool = False) -> None:
    headers = [(b"content-type", b"application/json")]
    if challenge:
        headers.append((b"www-authenticate", b"Bearer"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
