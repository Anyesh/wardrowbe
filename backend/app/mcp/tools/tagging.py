from typing import Any, Literal
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app.mcp.runtime import present, tool_context, validated
from app.mcp.tools.items import get_owned_item, item_dump
from app.schemas.item import ItemUpdate
from app.services.item_service import (
    ItemService,
    TagVocabularyError,
    stamp_manual_tag_writeback,
)
from app.utils.garment_vocabulary import (
    FITS,
    FORMALITY,
    MATERIALS,
    PATTERNS,
    SEASONS,
    STYLES,
    TYPES,
)

ItemType = Literal[TYPES]  # type: ignore[valid-type]
Pattern = Literal[PATTERNS]  # type: ignore[valid-type]
Material = Literal[MATERIALS]  # type: ignore[valid-type]
Style = Literal[STYLES]  # type: ignore[valid-type]
Season = Literal[SEASONS]  # type: ignore[valid-type]
Formality = Literal[FORMALITY]  # type: ignore[valid-type]
Fit = Literal[FITS]  # type: ignore[valid-type]


async def _apply_update(item_id: UUID, payload: dict[str, Any]) -> dict:
    update = validated(ItemUpdate, payload)
    update_data = update.model_dump(exclude_unset=True)
    async with tool_context() as ctx:
        item = await get_owned_item(ctx, item_id)
        stamp_manual_tag_writeback(item, update_data)
        try:
            item = await ItemService(ctx.db).update(item, update)
        except TagVocabularyError as exc:
            raise ToolError(str(exc)) from exc
        return item_dump(item)


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    async def set_item_tags(
        item_id: UUID,
        type: ItemType | None = None,
        subtype: str | None = None,
        colors: list[str] | None = None,
        primary_color: str | None = None,
        pattern: Pattern | None = None,
        material: Material | None = None,
        style: list[Style] | None = None,
        season: list[Season] | None = None,
        formality: Formality | None = None,
        fit: Fit | None = None,
    ) -> dict:
        """Write tags back to an item (external tagging). Sent fields replace
        their stored values and omitted fields keep theirs; a tag cannot be
        cleared here. Tag values must come from the closed vocabularies in this
        schema; colors and subtype are free text. Non-empty content marks the
        item tagged (tagged_by=manual)."""
        tags = present(
            colors=colors,
            primary_color=primary_color,
            pattern=pattern,
            material=material,
            style=style,
            season=season,
            formality=formality,
            fit=fit,
        )
        payload = present(type=type, subtype=subtype)
        if tags:
            payload["tags"] = tags
        if not payload:
            raise ToolError("Provide at least one tag field")
        return await _apply_update(item_id, payload)

    @mcp.tool()
    async def update_item(
        item_id: UUID,
        name: str | None = None,
        brand: str | None = None,
        notes: str | None = None,
        favorite: bool | None = None,
        wash_interval: int | None = None,
    ) -> dict:
        """Update non-tag item fields (name, brand, notes, favorite, wash_interval).
        Omitted fields are left unchanged; a field cannot be cleared here."""
        payload = present(
            name=name, brand=brand, notes=notes, favorite=favorite, wash_interval=wash_interval
        )
        if not payload:
            raise ToolError("Provide at least one field to update")
        return await _apply_update(item_id, payload)
