from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.workers.worker import recover_stale_processing_items


class TestRecoverStaleProcessingItems:
    @pytest.mark.asyncio
    async def test_marks_stale_items_as_error(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/stale.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        # Pretend it's 3 hours in the future so the item looks stale
        future = datetime.now(UTC) + timedelta(hours=3)
        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch("app.workers.worker.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = future
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await recover_stale_processing_items({})

        db_session.expire_all()
        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.error
        assert updated.ai_raw_response == {"error": "Processing timed out"}

    @pytest.mark.asyncio
    async def test_does_not_touch_recent_processing(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/recent.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await recover_stale_processing_items({})

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.processing

    @pytest.mark.asyncio
    async def test_does_not_touch_ready_items(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/ready.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()
        item_id = item.id

        # Even if we pretend it's the future, ready items should not be touched
        future = datetime.now(UTC) + timedelta(hours=3)
        with (
            patch("app.workers.worker.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
            patch("app.workers.worker.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = future
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await recover_stale_processing_items({})

        result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
        updated = result.scalar_one()
        assert updated.status == ItemStatus.ready
