from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.workers.tagging import update_item_status_to_error


async def _get_item(db_session: AsyncSession, item_id) -> ClothingItem:
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return result.scalar_one()


class TestUpdateItemStatusToError:
    @pytest.mark.asyncio
    async def test_flips_processing_item_to_error(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/a.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        ctx: dict = {}
        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await update_item_status_to_error(ctx, str(item.id), "boom")

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.error
        assert refreshed.ai_raw_response == {"error": "boom"}

    @pytest.mark.asyncio
    async def test_noop_when_item_already_moved_past_processing(
        self, db_session: AsyncSession, test_user
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/b.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        ctx: dict = {}
        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await update_item_status_to_error(ctx, str(item.id), "boom")

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.ai_raw_response is None
