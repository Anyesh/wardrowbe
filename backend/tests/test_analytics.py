from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User

ANALYTICS_URL = "/api/v1/analytics"


def _item(user_id, *, status=ItemStatus.ready, wear_count=0) -> ClothingItem:
    return ClothingItem(
        user_id=user_id,
        type="shirt",
        image_path=f"t/{uuid4()}.jpg",
        status=status,
        wear_count=wear_count,
    )


def _never_worn_insights(body: dict) -> list[str]:
    return [i for i in body["insights"] if "never worn" in i]


class TestNeverWornInsight:
    @pytest.mark.asyncio
    async def test_counts_all_never_worn_items_beyond_list_cap(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers
    ):
        db_session.add_all([_item(test_user.id) for _ in range(7)])
        await db_session.commit()

        response = await client.get(ANALYTICS_URL, headers=auth_headers)

        assert response.status_code == 200
        assert _never_worn_insights(response.json()) == [
            "You have 7 items you've never worn. Consider styling them!"
        ]

    @pytest.mark.asyncio
    async def test_singular_wording_for_one_item(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers
    ):
        db_session.add(_item(test_user.id))
        await db_session.commit()

        response = await client.get(ANALYTICS_URL, headers=auth_headers)

        assert _never_worn_insights(response.json()) == [
            "You have 1 item you've never worn. Consider styling it!"
        ]

    @pytest.mark.asyncio
    async def test_no_insight_when_every_item_worn(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers
    ):
        db_session.add_all([_item(test_user.id, wear_count=2) for _ in range(3)])
        await db_session.commit()

        response = await client.get(ANALYTICS_URL, headers=auth_headers)

        assert _never_worn_insights(response.json()) == []

    @pytest.mark.asyncio
    async def test_ignores_worn_and_non_ready_items(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers
    ):
        db_session.add_all(
            [
                *[_item(test_user.id) for _ in range(6)],
                *[_item(test_user.id, wear_count=3) for _ in range(4)],
                _item(test_user.id, status=ItemStatus.processing),
                _item(test_user.id, status=ItemStatus.archived),
                _item(test_user.id, status=ItemStatus.error),
            ]
        )
        await db_session.commit()

        response = await client.get(ANALYTICS_URL, headers=auth_headers)

        assert _never_worn_insights(response.json()) == [
            "You have 6 items you've never worn. Consider styling them!"
        ]

    @pytest.mark.asyncio
    async def test_ignores_other_users_items(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers
    ):
        other_id = uuid4()
        db_session.add(
            User(
                id=other_id,
                external_id=f"test-user-{other_id}",
                email=f"other-{other_id}@example.com",
                display_name="Other User",
                timezone="UTC",
                is_active=True,
            )
        )
        await db_session.commit()
        db_session.add_all([_item(other_id) for _ in range(6)])
        db_session.add_all([_item(test_user.id) for _ in range(2)])
        await db_session.commit()

        response = await client.get(ANALYTICS_URL, headers=auth_headers)

        assert _never_worn_insights(response.json()) == [
            "You have 2 items you've never worn. Consider styling them!"
        ]

    @pytest.mark.asyncio
    async def test_never_worn_list_stays_capped_at_five(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers
    ):
        db_session.add_all([_item(test_user.id) for _ in range(7)])
        await db_session.commit()

        response = await client.get(ANALYTICS_URL, headers=auth_headers)

        assert len(response.json()["never_worn"]) == 5

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client: AsyncClient):
        response = await client.get(ANALYTICS_URL)

        assert response.status_code in (401, 403)
