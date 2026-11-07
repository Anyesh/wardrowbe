from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from app.mcp.auth import MCPAuthMiddleware
from app.mcp.tools import authoring, items, lifecycle, outfits, overview, tagging

SERVER_NAME = "wardrowbe"
SERVER_INSTRUCTIONS = (
    "Built-in Wardrowbe MCP server. Manage the authenticated user's wardrobe: "
    "browse and tag items, log wear and wash, review and author outfits."
)

MCP_PATH = "/api/v1/mcp"

_TOOL_MODULES = (overview, items, tagging, lifecycle, outfits, authoring)


# A Starlette mount answers the exact mount path with a 307 slash redirect, which strict MCP
# clients don't follow on POST, so the endpoint is dispatched here ahead of the router.
class MCPDispatchMiddleware:
    def __init__(self, app: ASGIApp, mcp_app: ASGIApp) -> None:
        self.app = app
        self.mcp_app = mcp_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            root_path = scope.get("root_path", "")
            path = scope["path"]
            route_path = path[len(root_path) :] if path.startswith(root_path) else path
            if route_path == MCP_PATH or route_path.startswith(MCP_PATH + "/"):
                mount = root_path + MCP_PATH
                rest = route_path[len(MCP_PATH) :] or "/"
                await self.mcp_app(
                    {**scope, "root_path": mount, "path": mount + rest}, receive, send
                )
                return
        await self.app(scope, receive, send)


def build_mcp_server() -> MCPServer:
    mcp = MCPServer(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    for module in _TOOL_MODULES:
        module.register(mcp)
    return mcp


def build_mcp_asgi(server: MCPServer) -> MCPAuthMiddleware:
    # Host validation is left to the deployment's reverse proxy: the endpoint is
    # bearer-authenticated, so browser DNS-rebinding is not a usable vector, and
    # self-hosted instances serve under arbitrary hostnames.
    return MCPAuthMiddleware(
        server.streamable_http_app(
            streamable_http_path="/",
            json_response=True,
            stateless_http=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
    )
