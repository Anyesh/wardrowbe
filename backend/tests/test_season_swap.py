from datetime import date, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.season_swap import plan_swap

OCTOBER = date(2026, 10, 15)


def _item(item_type: str, seasons: list[str] | None = None, **fields) -> ClothingItem:
    return ClothingItem(
        id=uuid4(),
        type=item_type,
        image_path=f"{item_type}.jpg",
        status=ItemStatus.ready,
        season=seasons or [],
        **fields,
    )


class TestSeasonSwap:
    def test_october_in_the_north(self):
        coat = _item("coat", ["winter"])
        shorts = _item("shorts", ["summer"])
        jeans = _item("jeans", ["all-season"])
        jumper = _item("sweater", ["fall", "winter"])
        plan = plan_swap([coat, shorts, jeans, jumper], OCTOBER, 45.7, set())
        assert (plan.current, plan.upcoming) == ("fall", "winter")
        assert [i for i, _ in plan.bring_out] == [coat]
        assert [i for i, _ in plan.put_away] == [shorts]
        assert plan.stays == 2

    def test_southern_hemisphere_is_reversed(self):
        shorts = _item("shorts", ["summer"])
        plan = plan_swap([shorts], OCTOBER, -33.9, set())
        assert (plan.current, plan.upcoming) == ("spring", "summer")
        assert [i for i, _ in plan.bring_out] == [shorts]

    def test_recently_worn_items_stay_out(self):
        shorts = _item("shorts", ["summer"], last_worn_at=OCTOBER - timedelta(days=3))
        assert plan_swap([shorts], OCTOBER, 45.7, set()).put_away == []

    def test_untagged_items_follow_last_year(self):
        scarf = _item("scarf")
        plan = plan_swap([scarf], OCTOBER, 45.7, {scarf.id})
        assert plan.bring_out == [(scarf, "last_year")]

    @pytest.mark.asyncio
    async def test_endpoint(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        db_session.add(
            ClothingItem(
                user_id=test_user.id,
                type="sandals",
                image_path="s.jpg",
                status=ItemStatus.ready,
                season=["summer"],
            )
        )
        await db_session.commit()
        response = await client.get("/api/v1/season-swap", headers=auth_headers)
        assert response.status_code == 200, response.json()
        data = response.json()
        assert {"current_season", "upcoming_season", "put_away", "bring_out", "stays"} <= set(data)
