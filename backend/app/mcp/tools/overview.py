from mcp.server import MCPServer

from app.config import get_settings
from app.mcp.runtime import READ_ONLY, tool_context
from app.services.item_service import ItemService


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def session_info() -> dict:
        """Describe the authenticated user and the backend's AI capability flags."""
        async with tool_context() as ctx:
            settings = get_settings()
            return {
                "user": {
                    "id": str(ctx.user.id),
                    "email": ctx.user.email,
                    "display_name": ctx.user.display_name,
                    "timezone": ctx.user.timezone,
                    "locale": ctx.user.locale,
                },
                "ai": {
                    "vision": settings.effective_ai_vision_enabled,
                    "text": settings.effective_ai_text_enabled,
                },
            }

    @mcp.tool(annotations=READ_ONLY)
    async def get_wardrobe_summary() -> dict:
        """Aggregate wardrobe stats: totals, tagging queue size, wash queue size,
        type and color distributions."""
        async with tool_context() as ctx:
            service = ItemService(ctx.db)
            counts = await service.get_queue_counts(ctx.user.id)
            return {
                "total_items": counts["total"],
                "items_pending_tagging": counts["pending_tagging"],
                "items_needing_wash": counts["needs_wash"],
                "types": await service.get_item_types(ctx.user.id),
                "colors": await service.get_color_distribution(ctx.user.id),
            }
