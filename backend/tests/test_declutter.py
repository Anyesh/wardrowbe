from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.declutter_service import find_candidates, idle_value
from app.utils.timezone import get_user_today

TODAY = date(2026, 10, 15)


def _item(created_days_ago: int, last_worn_days_ago: int | None = None, **fields) -> ClothingItem:
    return ClothingItem(
        id=uuid4(),
        type="shirt",
        image_path="test/item.jpg",
        status=ItemStatus.ready,
        created_at=datetime.combine(
            TODAY - timedelta(days=created_days_ago), datetime.min.time(), UTC
        ),
        last_worn_at=TODAY - timedelta(days=last_worn_days_ago)
        if last_worn_days_ago is not None
        else None,
        **fields,
    )


class TestFindCandidates:
    def test_picks_never_worn_and_long_idle_items(self):
        never = _item(created_days_ago=400)
        idle = _item(created_days_ago=500, last_worn_days_ago=300)
        recent = _item(created_days_ago=500, last_worn_days_ago=10)
        new = _item(created_days_ago=20)
        result = find_candidates([recent, idle, new, never], TODAY, months=6)
        assert [c.item for c in result] == [never, idle]
        assert result[0].reason == "never_worn"
        assert result[1].reason == "not_worn_recently"
        assert result[1].idle_days == 300

    def test_kept_items_wait_until_their_date(self):
        kept = _item(created_days_ago=400)
        expired = _item(created_days_ago=400)
        until = {kept.id: TODAY + timedelta(days=30), expired.id: TODAY - timedelta(days=1)}
        assert [c.item for c in find_candidates([kept, expired], TODAY, 6, until)] == [expired]

    def test_shorter_window_finds_more(self):
        item = _item(created_days_ago=400, last_worn_days_ago=100)
        assert find_candidates([item], TODAY, months=6) == []
        assert len(find_candidates([item], TODAY, months=3)) == 1

    def test_idle_value_sums_known_prices(self):
        priced = _item(created_days_ago=400, purchase_price=Decimal("49.90"))
        unpriced = _item(created_days_ago=400)
        assert idle_value(find_candidates([priced, unpriced], TODAY, 6)) == Decimal("49.90")


class TestDeclutterApi:
    @pytest.mark.asyncio
    async def test_review_and_keep(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        today = get_user_today(test_user)
        old = ClothingItem(
            user_id=test_user.id,
            type="sweater",
            image_path="test/old.jpg",
            status=ItemStatus.ready,
            last_worn_at=today - timedelta(days=400),
        )
        worn = ClothingItem(
            user_id=test_user.id,
            type="jeans",
            image_path="test/worn.jpg",
            status=ItemStatus.ready,
            last_worn_at=today - timedelta(days=3),
        )
        db_session.add_all([old, worn])
        await db_session.commit()

        response = await client.get("/api/v1/declutter?months=6", headers=auth_headers)
        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["total_items"] == 2
        assert [c["item"]["id"] for c in data["candidates"]] == [str(old.id)]
        assert data["candidates"][0]["reason"] == "not_worn_recently"

        keep = await client.post(
            f"/api/v1/declutter/{old.id}/keep", json={"months": 6}, headers=auth_headers
        )
        assert keep.status_code == 200, keep.json()
        assert date.fromisoformat(keep.json()["kept_until"]) > today

        again = await client.get("/api/v1/declutter?months=6", headers=auth_headers)
        assert again.json()["candidates"] == []

        # Keeping twice moves the date instead of failing on the existing row.
        twice = await client.post(
            f"/api/v1/declutter/{old.id}/keep", json={"months": 12}, headers=auth_headers
        )
        assert twice.status_code == 200, twice.json()
        assert twice.json()["kept_until"] > keep.json()["kept_until"]

    @pytest.mark.asyncio
    async def test_cannot_keep_someone_elses_item(self, client: AsyncClient, auth_headers):
        response = await client.post(
            f"/api/v1/declutter/{uuid4()}/keep", json={"months": 6}, headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_months_out_of_range(self, client: AsyncClient, auth_headers):
        response = await client.get("/api/v1/declutter?months=0", headers=auth_headers)
        assert response.status_code == 422
