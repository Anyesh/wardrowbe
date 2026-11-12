import pytest
from httpx import AsyncClient
from sqlalchemy.orm.attributes import set_committed_value

from app.models import UserPreference
from app.models.learning import ItemPairScore
from app.services.learning_service import LearningService
from app.services.pairing_service import PairingService
from app.services.recommendation_service import RecommendationService
from tests.test_pairings import _make_item


async def _wardrobe(db_session, user_id, types):
    items = [_make_item(user_id, t) for t in types]
    db_session.add_all(items)
    await db_session.commit()
    return items


async def _exclude(db_session, user, item_ids):
    prefs = UserPreference(user_id=user.id, excluded_item_ids=list(item_ids))
    db_session.add(prefs)
    await db_session.commit()
    # Mirror the request path, where the user is loaded with preferences attached.
    set_committed_value(user, "preferences", prefs)
    return prefs


class TestExcludedItemsEndpoints:
    @pytest.mark.asyncio
    async def test_preferences_expose_excluded_items(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        (socks,) = await _wardrobe(db_session, test_user.id, ["socks"])

        added = await client.post(
            f"/api/v1/users/me/preferences/excluded-items/{socks.id}", headers=auth_headers
        )
        assert added.status_code == 200

        prefs = await client.get("/api/v1/users/me/preferences", headers=auth_headers)
        assert prefs.json()["excluded_item_ids"] == [str(socks.id)]

        removed = await client.delete(
            f"/api/v1/users/me/preferences/excluded-items/{socks.id}", headers=auth_headers
        )
        assert removed.status_code == 200
        prefs = await client.get("/api/v1/users/me/preferences", headers=auth_headers)
        assert prefs.json()["excluded_item_ids"] == []


class TestExcludedItemsSkippedByAI:
    @pytest.mark.asyncio
    async def test_pairing_skips_excluded_items(self, db_session, test_user):
        source, shirt, socks = await _wardrobe(
            db_session, test_user.id, ["jacket", "shirt", "socks"]
        )
        await _exclude(db_session, test_user, [socks.id])

        available = await PairingService(db_session).get_available_items(test_user, source.id)

        assert [i.id for i in available] == [shirt.id]

    @pytest.mark.asyncio
    async def test_pairing_allows_excluded_source_item(self, db_session, test_user):
        source, shirt, pants = await _wardrobe(
            db_session, test_user.id, ["socks", "shirt", "pants"]
        )
        await _exclude(db_session, test_user, [source.id])

        service = PairingService(db_session)
        assert (await service.get_source_item(test_user.id, source.id)).id == source.id
        available = await service.get_available_items(test_user, source.id)
        assert {i.id for i in available} == {shirt.id, pants.id}

    @pytest.mark.asyncio
    async def test_recommendation_candidates_skip_excluded_items(self, db_session, test_user):
        shirt, socks = await _wardrobe(db_session, test_user.id, ["shirt", "socks"])
        prefs = await _exclude(db_session, test_user, [socks.id])

        candidates = await RecommendationService(db_session).get_candidate_items(
            test_user, None, "casual", prefs, []
        )

        assert [i.id for i in candidates] == [shirt.id]

    @pytest.mark.asyncio
    async def test_learned_pair_suggestions_skip_excluded_items(self, db_session, test_user):
        source, shirt, socks = await _wardrobe(
            db_session, test_user.id, ["jacket", "shirt", "socks"]
        )
        for other in (shirt, socks):
            a, b = sorted([source.id, other.id])
            db_session.add(
                ItemPairScore(user_id=test_user.id, item1_id=a, item2_id=b, compatibility_score=0.8)
            )
        await db_session.commit()
        await _exclude(db_session, test_user, [socks.id])

        suggestions = await LearningService(db_session).get_item_pair_suggestions(
            test_user.id, source.id
        )

        assert [item.id for item, _ in suggestions] == [shirt.id]
