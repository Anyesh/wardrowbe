from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_access_token
from app.models.family import Family
from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import (
    FamilyOutfitRating,
    Outfit,
    OutfitItem,
    OutfitSource,
    OutfitStatus,
)
from app.models.user import User


def _make_item(user_id, item_type="shirt", **kwargs) -> ClothingItem:
    return ClothingItem(
        user_id=user_id,
        type=item_type,
        image_path=f"test/{uuid4()}.jpg",
        status=ItemStatus.ready,
        **kwargs,
    )


def _make_pairing(user_id, items: list[ClothingItem], source_item=None) -> Outfit:
    outfit = Outfit(
        user_id=user_id,
        occasion="casual",
        scheduled_for=date.today(),
        status=OutfitStatus.pending,
        source=OutfitSource.pairing,
        source_item_id=source_item.id if source_item else None,
        reasoning="Test pairing",
    )
    for i, item in enumerate(items):
        outfit_item = OutfitItem(
            item_id=item.id,
            position=i,
        )
        outfit.items.append(outfit_item)
    return outfit


@pytest.fixture
def second_user_factory():
    def _make(family_id=None):
        uid = uuid4()
        return User(
            id=uid,
            external_id=f"test-user-{uid}",
            email=f"test-{uid}@example.com",
            display_name="Second User",
            timezone="UTC",
            is_active=True,
            onboarding_completed=False,
            family_id=family_id,
        )

    return _make


class TestListPairings:
    @pytest.mark.asyncio
    async def test_list_pairings_empty(self, client: AsyncClient, test_user, auth_headers):
        response = await client.get("/api/v1/pairings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["pairings"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_pairings_returns_data(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item1 = _make_item(test_user.id, "shirt")
        item2 = _make_item(test_user.id, "pants")
        db_session.add_all([item1, item2])
        await db_session.flush()

        pairing = _make_pairing(test_user.id, [item1, item2], source_item=item1)
        db_session.add(pairing)
        await db_session.commit()

        response = await client.get("/api/v1/pairings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["pairings"]) == 1
        assert data["pairings"][0]["source"] == "pairing"
        assert len(data["pairings"][0]["items"]) == 2


class TestPairingResponseIncludesFamilyRatings:
    @pytest.mark.asyncio
    async def test_pairing_response_has_family_rating_fields(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        pairing = _make_pairing(test_user.id, [item])
        db_session.add(pairing)
        await db_session.commit()

        response = await client.get("/api/v1/pairings", headers=auth_headers)
        data = response.json()
        p = data["pairings"][0]
        assert "family_ratings" in p
        assert "family_rating_average" in p
        assert "family_rating_count" in p

    @pytest.mark.asyncio
    async def test_pairing_with_family_rating_returns_data(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        family = Family(
            name="Test Family", invite_code=f"TST{uuid4().hex[:6]}", created_by=test_user.id
        )
        db_session.add(family)
        await db_session.flush()

        test_user.family_id = family.id
        await db_session.flush()

        rater = User(
            id=uuid4(),
            external_id=f"rater-{uuid4()}",
            email=f"rater-{uuid4()}@example.com",
            display_name="Rater",
            timezone="UTC",
            is_active=True,
            family_id=family.id,
        )
        db_session.add(rater)
        await db_session.flush()

        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        pairing = _make_pairing(test_user.id, [item])
        db_session.add(pairing)
        await db_session.flush()

        rating = FamilyOutfitRating(
            outfit_id=pairing.id,
            user_id=rater.id,
            rating=4,
            comment="Nice combo!",
        )
        db_session.add(rating)
        await db_session.commit()

        response = await client.get("/api/v1/pairings", headers=auth_headers)
        data = response.json()
        p = data["pairings"][0]
        assert p["family_rating_count"] == 1
        assert p["family_rating_average"] == 4.0
        assert len(p["family_ratings"]) == 1
        assert p["family_ratings"][0]["rating"] == 4
        assert p["family_ratings"][0]["comment"] == "Nice combo!"
        assert p["family_ratings"][0]["user_display_name"] == "Rater"

    @pytest.mark.asyncio
    async def test_pairing_without_ratings_returns_null(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        pairing = _make_pairing(test_user.id, [item])
        db_session.add(pairing)
        await db_session.commit()

        response = await client.get("/api/v1/pairings", headers=auth_headers)
        data = response.json()
        p = data["pairings"][0]
        assert p["family_ratings"] is None
        assert p["family_rating_average"] is None
        assert p["family_rating_count"] is None


class TestFamilyRatingEndpoint:
    @pytest.mark.asyncio
    async def test_cannot_rate_own_outfit(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        family = Family(
            name="Test Family", invite_code=f"FAM{uuid4().hex[:6]}", created_by=test_user.id
        )
        db_session.add(family)
        await db_session.flush()

        test_user.family_id = family.id
        await db_session.flush()

        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        pairing = _make_pairing(test_user.id, [item])
        db_session.add(pairing)
        await db_session.commit()

        response = await client.post(
            f"/api/v1/outfits/{pairing.id}/family-rating",
            json={"rating": 5},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Cannot rate your own" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_family_member_can_rate(
        self, client: AsyncClient, test_user, db_session: AsyncSession
    ):
        family = Family(
            name="Test Family", invite_code=f"FAM{uuid4().hex[:6]}", created_by=test_user.id
        )
        db_session.add(family)
        await db_session.flush()

        test_user.family_id = family.id

        rater = User(
            id=uuid4(),
            external_id=f"rater-{uuid4()}",
            email=f"rater-{uuid4()}@example.com",
            display_name="Family Rater",
            timezone="UTC",
            is_active=True,
            family_id=family.id,
        )
        db_session.add(rater)
        await db_session.flush()

        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        pairing = _make_pairing(test_user.id, [item])
        db_session.add(pairing)
        await db_session.commit()

        rater_token = create_access_token(rater.external_id)
        rater_headers = {"Authorization": f"Bearer {rater_token}"}

        response = await client.post(
            f"/api/v1/outfits/{pairing.id}/family-rating",
            json={"rating": 4, "comment": "Looks great!"},
            headers=rater_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rating"] == 4
        assert data["comment"] == "Looks great!"

    @pytest.mark.asyncio
    async def test_non_family_member_cannot_rate(
        self, client: AsyncClient, test_user, db_session: AsyncSession
    ):
        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        pairing = _make_pairing(test_user.id, [item])
        db_session.add(pairing)

        outsider = User(
            id=uuid4(),
            external_id=f"outsider-{uuid4()}",
            email=f"outsider-{uuid4()}@example.com",
            display_name="Outsider",
            timezone="UTC",
            is_active=True,
        )
        db_session.add(outsider)
        await db_session.commit()

        outsider_token = create_access_token(outsider.external_id)
        outsider_headers = {"Authorization": f"Bearer {outsider_token}"}

        response = await client.post(
            f"/api/v1/outfits/{pairing.id}/family-rating",
            json={"rating": 3},
            headers=outsider_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_rating_upsert(self, client: AsyncClient, test_user, db_session: AsyncSession):
        family = Family(
            name="Test Family", invite_code=f"FAM{uuid4().hex[:6]}", created_by=test_user.id
        )
        db_session.add(family)
        await db_session.flush()

        test_user.family_id = family.id

        rater = User(
            id=uuid4(),
            external_id=f"rater-{uuid4()}",
            email=f"rater-{uuid4()}@example.com",
            display_name="Rater",
            timezone="UTC",
            is_active=True,
            family_id=family.id,
        )
        db_session.add(rater)
        await db_session.flush()

        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        pairing = _make_pairing(test_user.id, [item])
        db_session.add(pairing)
        await db_session.commit()

        rater_token = create_access_token(rater.external_id)
        rater_headers = {"Authorization": f"Bearer {rater_token}"}

        # First rating
        response = await client.post(
            f"/api/v1/outfits/{pairing.id}/family-rating",
            json={"rating": 3},
            headers=rater_headers,
        )
        assert response.status_code == 200
        assert response.json()["rating"] == 3

        # Update (upsert)
        response = await client.post(
            f"/api/v1/outfits/{pairing.id}/family-rating",
            json={"rating": 5, "comment": "Changed my mind!"},
            headers=rater_headers,
        )
        assert response.status_code == 200
        assert response.json()["rating"] == 5
        assert response.json()["comment"] == "Changed my mind!"


class TestDeletePairing:
    @pytest.mark.asyncio
    async def test_delete_own_pairing(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        item = _make_item(test_user.id)
        db_session.add(item)
        await db_session.flush()

        pairing = _make_pairing(test_user.id, [item])
        db_session.add(pairing)
        await db_session.commit()

        response = await client.delete(f"/api/v1/pairings/{pairing.id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deleted
        response = await client.get("/api/v1/pairings", headers=auth_headers)
        assert response.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_cannot_delete_other_users_pairing(
        self, client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
    ):
        other_user = User(
            id=uuid4(),
            external_id=f"other-{uuid4()}",
            email=f"other-{uuid4()}@example.com",
            display_name="Other",
            timezone="UTC",
            is_active=True,
        )
        db_session.add(other_user)
        await db_session.flush()

        item = _make_item(other_user.id)
        db_session.add(item)
        await db_session.flush()

        pairing = _make_pairing(other_user.id, [item])
        db_session.add(pairing)
        await db_session.commit()

        response = await client.delete(f"/api/v1/pairings/{pairing.id}", headers=auth_headers)
        assert response.status_code == 404
