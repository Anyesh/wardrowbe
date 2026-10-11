import logging
from datetime import date
from typing import Literal
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.api.outfits import (
    OutfitListResponse,
    feedback_to_response,
    fetch_wore_instead_items_map,
    outfit_to_response,
)
from app.mcp.runtime import READ_ONLY, ToolContext, present, tool_context, validated
from app.mcp.tools.items import clamp_page
from app.models.outfit import FamilyOutfitRating, Outfit, OutfitItem, OutfitStatus
from app.schemas.outfit import FeedbackRequest
from app.services.learning_service import LearningService
from app.services.outfit_service import OutfitListFilters, OutfitService
from app.services.suggestion_cache import clear_suggestions

logger = logging.getLogger(__name__)


async def load_owned_outfit(ctx: ToolContext, outfit_id: UUID) -> Outfit:
    query = (
        select(Outfit)
        .where(and_(Outfit.id == outfit_id, Outfit.user_id == ctx.user.id))
        .options(
            selectinload(Outfit.items).selectinload(OutfitItem.item),
            selectinload(Outfit.feedback),
            selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
        )
    )
    outfit = (await ctx.db.execute(query)).scalar_one_or_none()
    if not outfit:
        raise ToolError("Outfit not found")
    return outfit


async def outfit_dump(ctx: ToolContext, outfit: Outfit) -> dict:
    wore = await fetch_wore_instead_items_map(ctx.db, [outfit], user_id=ctx.user.id)
    return outfit_to_response(outfit, wore).model_dump(mode="json")


def register(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_outfits(
        page: int = 1,
        page_size: int = 10,
        status: str | None = None,
        occasion: str | None = None,
        source: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict:
        """List the user's outfits, newest first by creation. Filter by status
        (pending/sent/viewed/accepted/rejected/skipped/expired), occasion, source
        (scheduled/on_demand/manual/pairing/external), or scheduled date range.
        status and source accept several comma-separated values."""
        page, page_size = clamp_page(page, page_size)
        async with tool_context() as ctx:
            filters = OutfitListFilters(
                user_id=ctx.user.id,
                status_filter=status,
                occasion=occasion,
                source=source,
                date_from=date_from,
                date_to=date_to,
            )
            outfits, total = await OutfitService(ctx.db).list_with_filters(filters, page, page_size)
            wore = await fetch_wore_instead_items_map(ctx.db, outfits, user_id=ctx.user.id)
            return OutfitListResponse(
                outfits=[outfit_to_response(o, wore) for o in outfits],
                total=total,
                page=page,
                page_size=page_size,
                has_more=(page * page_size) < total,
            ).model_dump(mode="json")

    @mcp.tool(annotations=READ_ONLY)
    async def get_outfit(outfit_id: UUID) -> dict:
        """Fetch one outfit with its items, attributes, feedback, and image URLs."""
        async with tool_context() as ctx:
            outfit = await load_owned_outfit(ctx, outfit_id)
            return await outfit_dump(ctx, outfit)

    @mcp.tool()
    async def respond_to_outfit(
        outfit_id: UUID, response: Literal["accepted", "rejected", "skipped"]
    ) -> dict:
        """Record the user's answer to an outfit suggestion: accepted (they will
        wear it), rejected (they dislike it; trains future suggestions away from
        it), or skipped (not today; no preference recorded). rejected and skipped
        also discard the cached suggestions for that occasion. For ratings or a
        comment use submit_outfit_feedback."""
        async with tool_context() as ctx:
            outfit = await OutfitService(ctx.db).set_status(
                outfit_id, ctx.user.id, OutfitStatus(response)
            )
            if response in ("rejected", "skipped"):
                await clear_suggestions(ctx.user.id, outfit.occasion)
            return await outfit_dump(ctx, outfit)

    @mcp.tool()
    async def submit_outfit_feedback(
        outfit_id: UUID,
        accepted: bool | None = None,
        rating: int | None = None,
        comfort_rating: int | None = None,
        style_rating: int | None = None,
        comment: str | None = None,
        worn: bool | None = None,
    ) -> dict:
        """Record feedback on an outfit: ratings 1-5, a comment, and worn=true
        (logs a wear for every item). accepted=true/false also sets the status,
        like respond_to_outfit but without clearing cached suggestions; for a
        plain yes/no answer prefer respond_to_outfit."""
        payload = present(
            accepted=accepted,
            rating=rating,
            comfort_rating=comfort_rating,
            style_rating=style_rating,
            comment=comment,
            worn=worn,
        )
        request = validated(FeedbackRequest, payload)
        async with tool_context() as ctx:
            outfit = await load_owned_outfit(ctx, outfit_id)
            feedback, _ = await OutfitService(ctx.db).apply_feedback(ctx.user, outfit, request)
            await ctx.db.commit()
            await ctx.db.refresh(feedback)
            response = feedback_to_response(feedback).model_dump(mode="json")
            try:
                await LearningService(ctx.db).process_feedback(outfit.id, ctx.user.id)
            except Exception:
                logger.exception("learning process_feedback failed for outfit %s", outfit_id)
                await ctx.db.rollback()
            return response
