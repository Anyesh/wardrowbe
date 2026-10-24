import asyncio
import base64
import mimetypes
from typing import Literal
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ImageContent

from app.config import get_settings
from app.mcp.runtime import READ_ONLY, ToolContext, present, tool_context, validated
from app.models.item import ClothingItem
from app.schemas.item import ItemCreate, ItemFilter, ItemListResponse, ItemResponse
from app.services.image_service import ImageService
from app.services.item_service import ItemService
from app.utils.rate_limit import rate_limit_by_user
from app.utils.upload_tokens import UPLOAD_TOKEN_TTL_SECONDS, issue_upload_token

MAX_PAGE_SIZE = 100


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    return max(page, 1), min(max(page_size, 1), MAX_PAGE_SIZE)


async def get_owned_item(ctx: ToolContext, item_id: UUID) -> ClothingItem:
    item = await ItemService(ctx.db).get_by_id(item_id, ctx.user.id)
    if not item:
        raise ToolError("Item not found")
    return item


def item_dump(item: ClothingItem) -> dict:
    return ItemResponse.model_validate(item).model_dump(mode="json")


def item_list_dump(items: list[ClothingItem], total: int, page: int, page_size: int) -> dict:
    return ItemListResponse(
        items=[ItemResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    ).model_dump(mode="json")


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_items(
        page: int = 1,
        page_size: int = 20,
        type: str | None = None,
        status: str | None = None,
        tagging_status: str | None = None,
        favorite: bool | None = None,
        needs_wash: bool | None = None,
        is_archived: bool = False,
        search: str | None = None,
    ) -> dict:
        """List the user's clothing items with filters. tagging_status='pending'
        is the external-tagging work queue; needs_wash=true is the wash queue
        (wears since last wash reached the item's wash interval, or the default
        for its type). type matches any stored type, including ones outside the
        tagging vocabulary."""
        page, page_size = clamp_page(page, page_size)
        filters = ItemFilter(
            type=type,
            status=status,
            tagging_status=tagging_status,
            favorite=favorite,
            needs_wash=needs_wash,
            is_archived=is_archived,
            search=search,
        )
        async with tool_context() as ctx:
            items, total = await ItemService(ctx.db).get_list(
                ctx.user.id, filters, page=page, page_size=page_size
            )
            return item_list_dump(items, total, page, page_size)

    @mcp.tool(annotations=READ_ONLY)
    async def get_item(item_id: UUID) -> dict:
        """Fetch one clothing item: tags, lifecycle state, wear/wash counters, image URLs."""
        async with tool_context() as ctx:
            return item_dump(await get_owned_item(ctx, item_id))

    @mcp.tool(annotations=READ_ONLY)
    async def get_item_image(
        item_id: UUID, variant: Literal["thumbnail", "medium", "full"] = "medium"
    ) -> ImageContent:
        """Return the item's photo. thumbnail=400px, medium=800px, full=original, up to 2400px."""
        async with tool_context() as ctx:
            item = await get_owned_item(ctx, item_id)
            relative = {
                "thumbnail": item.thumbnail_path,
                "medium": item.medium_path,
                "full": item.image_path,
            }[variant] or item.image_path
            path = ImageService().get_image_path(relative)
            if not path.is_file():
                raise ToolError("Image file missing from storage")
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            data = base64.b64encode(await asyncio.to_thread(path.read_bytes)).decode("ascii")
            return ImageContent(type="image", data=data, mimeType=mime)

    @mcp.tool()
    async def create_item_upload(
        name: str | None = None,
        type: str | None = None,
        brand: str | None = None,
        notes: str | None = None,
        favorite: bool = False,
        skip_ai: bool = False,
    ) -> dict:
        """Get a one-time link for adding an item with a photo. POST the photo to
        upload_url as multipart field "image" within expires_in_seconds, e.g.
        curl -F image=@photo.jpg <upload_url>; the response is the created item.
        A failed upload uses the link up, so ask for a new one to retry. skip_ai
        leaves the item pending for external tagging even when vision is on."""
        if not get_settings().app_url:
            raise ToolError("Upload links need APP_URL set to the public app URL")
        item = validated(
            ItemCreate,
            present(name=name, type=type or None, brand=brand, notes=notes, favorite=favorite),
        )
        async with tool_context() as ctx:
            await rate_limit_by_user(
                str(ctx.user.id), "item_upload", max_requests=30, window_seconds=60
            )
            token = await issue_upload_token(
                ctx.user.id, item.model_dump(mode="json", exclude_unset=True), skip_ai
            )
        return {
            "upload_url": get_settings().app_link(f"/api/v1/items/uploads/{token}"),
            "field": "image",
            "expires_in_seconds": UPLOAD_TOKEN_TTL_SECONDS,
        }
