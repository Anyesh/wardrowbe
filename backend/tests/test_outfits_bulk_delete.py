from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import Outfit, OutfitItem, OutfitSource, OutfitStatus
from app.models.user import User


def _make_item(user_id, item_type="shirt", **kwargs) -> ClothingItem:
    return ClothingItem(
        user_id=user_id,
        type=item_type,
        image_path=f"test/{uuid4()}.jpg",
        status=ItemStatus.ready,
        **kwargs,
    )


def _make_outfit(
    user_id,
    items: list[ClothingItem] | None = None,
    is_lookbook: bool = False,
    status: OutfitStatus = OutfitStatus.pending,
    occasion: str = "casual",
) -> Outfit:
    outfit = Outfit(
        user_id=user_id,
        occasion=occasion,
        scheduled_for=None if is_lookbook else date.today(),
        status=status,
        source=OutfitSource.manual,
    )
    for i, item in enumerate(items or []):
        outfit.items.append(OutfitItem(item_id=item.id, position=i))
    return outfit


@pytest.fixture
def second_user_factory():
    def _make():
        uid = uuid4()
        return User(
            id=uid,
            external_id=f"test-user-{uid}",
            email=f"test-{uid}@example.com",
            display_name="Second User",
            timezone="UTC",
            is_active=True,
            onboarding_completed=False,
        )

    return _make


class TestBulkDeleteExplicitIds:
    @pytest.mark.asyncio
    async def test_deletes_selected_outfits(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        o1 = _make_outfit(test_user.id, [item])
        o2 = _make_outfit(test_user.id, [item])
        o3 = _make_outfit(test_user.id, [item])
        db_session.add_all([o1, o2, o3])
        await db_session.commit()
        await db_session.refresh(o1)
        await db_session.refresh(o2)
        await db_session.refresh(o3)

        response = await client.post(
            "/api/v1/outfits/bulk/delete",
            json={"outfit_ids": [str(o1.id), str(o2.id)]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == 2
        assert data["failed"] == 0

        remaining = await db_session.execute(select(Outfit).where(Outfit.user_id == test_user.id))
        remaining_ids = {o.id for o in remaining.scalars().all()}
        assert remaining_ids == {o3.id}


class TestBulkDeleteSelectAll:
    @pytest.mark.asyncio
    async def test_deletes_all_matching_filters(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        lookbook = _make_outfit(test_user.id, [item], is_lookbook=True)
        worn = _make_outfit(test_user.id, [item], is_lookbook=False)
        db_session.add_all([lookbook, worn])
        await db_session.commit()
        await db_session.refresh(lookbook)
        await db_session.refresh(worn)

        response = await client.post(
            "/api/v1/outfits/bulk/delete",
            json={"select_all": True, "filters": {"is_lookbook": True}},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == 1
        assert data["failed"] == 0

        remaining = await db_session.execute(select(Outfit).where(Outfit.user_id == test_user.id))
        remaining_ids = {o.id for o in remaining.scalars().all()}
        assert remaining_ids == {worn.id}

    @pytest.mark.asyncio
    async def test_select_all_respects_excluded_ids(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        o1 = _make_outfit(test_user.id, [item], is_lookbook=True)
        o2 = _make_outfit(test_user.id, [item], is_lookbook=True)
        db_session.add_all([o1, o2])
        await db_session.commit()
        await db_session.refresh(o1)
        await db_session.refresh(o2)

        response = await client.post(
            "/api/v1/outfits/bulk/delete",
            json={
                "select_all": True,
                "excluded_ids": [str(o2.id)],
                "filters": {"is_lookbook": True},
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == 1

        remaining = await db_session.execute(select(Outfit).where(Outfit.user_id == test_user.id))
        remaining_ids = {o.id for o in remaining.scalars().all()}
        assert remaining_ids == {o2.id}


class TestBulkDeleteOwnershipBoundary:
    @pytest.mark.asyncio
    async def test_cannot_delete_another_users_outfit(
        self,
        client: AsyncClient,
        test_user,
        auth_headers,
        db_session: AsyncSession,
        second_user_factory,
    ):
        other_user = second_user_factory()
        db_session.add(other_user)
        await db_session.flush()

        other_item = _make_item(other_user.id)
        db_session.add(other_item)
        await db_session.flush()

        other_outfit = _make_outfit(other_user.id, [other_item])
        db_session.add(other_outfit)
        await db_session.commit()
        await db_session.refresh(other_outfit)

        response = await client.post(
            "/api/v1/outfits/bulk/delete",
            json={"outfit_ids": [str(other_outfit.id)]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == 0
        assert data["failed"] == 1
        assert "not found" in data["errors"][0].lower()

        still_there = await db_session.execute(select(Outfit).where(Outfit.id == other_outfit.id))
        assert still_there.scalar_one_or_none() is not None


class TestBulkDeletePartialFailure:
    @pytest.mark.asyncio
    async def test_nonexistent_id_reports_failure_others_succeed(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        outfit = _make_outfit(test_user.id, [item])
        db_session.add(outfit)
        await db_session.commit()
        await db_session.refresh(outfit)

        missing_id = uuid4()

        response = await client.post(
            "/api/v1/outfits/bulk/delete",
            json={"outfit_ids": [str(outfit.id), str(missing_id)]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] == 1
        assert data["failed"] == 1
        assert any(str(missing_id) in e for e in data["errors"])

        remaining = await db_session.execute(select(Outfit).where(Outfit.user_id == test_user.id))
        assert remaining.scalar_one_or_none() is None


class TestBulkDeleteRequestValidation:
    @pytest.mark.asyncio
    async def test_requires_outfit_ids_or_select_all(
        self, client: AsyncClient, test_user, auth_headers
    ):
        response = await client.post(
            "/api/v1/outfits/bulk/delete",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_both_outfit_ids_and_select_all(
        self, client: AsyncClient, test_user, auth_headers
    ):
        response = await client.post(
            "/api/v1/outfits/bulk/delete",
            json={"outfit_ids": [str(uuid4())], "select_all": True},
            headers=auth_headers,
        )
        assert response.status_code == 422
