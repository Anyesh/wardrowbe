import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, text

from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import Outfit, OutfitItem, OutfitSource
from app.services.recommendation_service import (
    RECOMMENDATION_PROMPT,
    RecommendationService,
    resolve_layer_extras,
)
from tests.migration_helpers import migration_downgrade
from tests.test_item_scorer import _weather

PREVIOUS = "a7d3c9e1f5b2"


class TestExtrasPrompt:
    def test_extras_in_prompt_and_json_shape(self):
        assert '"if_cooler"' in RECOMMENDATION_PROMPT
        assert '"if_warmer"' in RECOMMENDATION_PROMPT
        assert "cardigan" in RECOMMENDATION_PROMPT.split("WEATHER EXTRAS")[1]


class TestResolveLayerExtras:
    def setup_method(self):
        kinds = {
            "top": "t-shirt",
            "bottom": "jeans",
            "shoes": "sneakers",
            "cardigan": "cardigan",
            "jacket": "jacket",
            "coat": "coat",
            "hat": "hat",
            "shirt2": "shirt",
        }
        self.ids = {name: uuid4() for name in kinds}
        self.types = {self.ids[name]: kind for name, kind in kinds.items()}
        self.numbers = {i: self.ids[name] for i, name in enumerate(kinds, start=1)}
        self.n = {name: i for i, name in enumerate(kinds, start=1)}
        self.outfit = [self.ids[n] for n in ("top", "bottom", "shoes", "jacket")]

    def _resolve(self, cooler=None, warmer=None, outfit=None, types=None):
        data = {"items": [], "if_cooler": cooler, "if_warmer": warmer}
        return resolve_layer_extras(data, self.numbers, types or self.types, outfit or self.outfit)

    def test_valid_pair(self):
        cooler, warmer = self._resolve(self.n["cardigan"], self.n["jacket"])
        assert cooler == self.ids["cardigan"]
        assert warmer == self.ids["jacket"]

    def test_null_and_missing(self):
        assert self._resolve(None, None) == (None, None)
        assert resolve_layer_extras({"items": []}, self.numbers, self.types, self.outfit) == (
            None,
            None,
        )

    def test_numbers_as_strings_are_accepted(self):
        cooler, _ = self._resolve(str(self.n["coat"]))
        assert cooler == self.ids["coat"]

    @pytest.mark.parametrize("bad", [99, 0, -1, "abc", True, [1, 2], {"a": 1}, 4.5e20])
    def test_out_of_range_or_malformed_is_dropped(self, bad):
        assert self._resolve(bad, bad) == (None, None)

    def test_cooler_must_be_a_layer(self):
        assert self._resolve(self.n["hat"]) == (None, None)
        assert self._resolve(self.n["shirt2"]) == (None, None)
        assert self._resolve(self.n["shoes"]) == (None, None)

    def test_cooler_must_not_duplicate_an_outfit_item(self):
        assert self._resolve(self.n["jacket"]) == (None, None)

    def test_warmer_must_be_in_the_outfit(self):
        assert self._resolve(None, self.n["coat"]) == (None, None)

    def test_warmer_must_be_removable(self):
        assert self._resolve(None, self.n["top"]) == (None, None)
        assert self._resolve(None, self.n["shoes"]) == (None, None)

    def test_warmer_must_leave_a_complete_outfit(self):
        hoodie = uuid4()
        types = {**self.types, hoodie: "hoodie"}
        numbers = {**self.numbers, 50: hoodie}
        # The hoodie is the only top, so taking it off would leave the outfit incomplete.
        outfit = [hoodie, self.ids["bottom"], self.ids["shoes"]]
        data = {"items": [], "if_warmer": 50}
        assert resolve_layer_extras(data, numbers, types, outfit) == (None, None)

    def test_excluded_or_archived_items_are_not_candidates(self):
        # Excluded and archived items never reach the candidates, so they are absent from
        # item_type_map (and the number map built from it).
        types = {k: v for k, v in self.types.items() if k != self.ids["cardigan"]}
        assert self._resolve(self.n["cardigan"], types=types) == (None, None)

    def test_one_invalid_does_not_drop_the_other(self):
        cooler, warmer = self._resolve(self.n["jacket"], self.n["jacket"])
        assert cooler is None
        assert warmer == self.ids["jacket"]

    def test_survives_a_redis_round_trip(self):
        data = json.loads(json.dumps({"items": [], "if_cooler": 4, "if_warmer": 5}))
        numbers = {int(k): v for k, v in {str(k): v for k, v in self.numbers.items()}.items()}
        cooler, warmer = resolve_layer_extras(data, numbers, self.types, self.outfit)
        assert cooler == self.ids["cardigan"]
        assert warmer == self.ids["jacket"]


async def _wardrobe(db_session, user_id):
    items = {}
    for name, kind in (
        ("top", "t-shirt"),
        ("bottom", "jeans"),
        ("shoes", "sneakers"),
        ("jacket", "jacket"),
        ("cardigan", "cardigan"),
    ):
        items[name] = ClothingItem(
            id=uuid4(),
            user_id=user_id,
            type=kind,
            name=f"My {name}",
            image_path=f"test/{name}.jpg",
            thumbnail_path=f"test/{name}_thumb.jpg",
            status=ItemStatus.ready,
        )
    db_session.add_all(items.values())
    await db_session.commit()
    return items


class TestPersistenceAndApi:
    async def _save(self, db_session, test_user, items, extras):
        service = RecommendationService(db_session)
        types = {i.id: i.type for i in items.values()}
        numbers = dict(enumerate((i.id for i in items.values()), start=1))
        ids = [items[n].id for n in ("top", "bottom", "shoes", "jacket")]
        weather = _weather(temp=15)
        return await service._save_outfit(
            {"items": [1, 2, 3, 4], "headline": "Layered", **extras},
            ids,
            types,
            test_user,
            weather,
            "casual",
            OutfitSource.on_demand,
            number_map=numbers,
        )

    async def test_saved_and_returned_by_the_api(self, client, db_session, test_user, auth_headers):
        items = await _wardrobe(db_session, test_user.id)
        outfit = await self._save(db_session, test_user, items, {"if_cooler": 5, "if_warmer": 4})
        assert outfit.if_cooler_item_id == items["cardigan"].id
        assert outfit.if_warmer_item_id == items["jacket"].id

        response = await client.get(f"/api/v1/outfits/{outfit.id}", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["if_cooler"]["id"] == str(items["cardigan"].id)
        assert body["if_cooler"]["type"] == "cardigan"
        assert body["if_cooler"]["thumbnail_url"]
        assert body["if_warmer"]["id"] == str(items["jacket"].id)

    async def test_invalid_extras_are_not_saved(self, client, db_session, test_user, auth_headers):
        items = await _wardrobe(db_session, test_user.id)
        outfit = await self._save(db_session, test_user, items, {"if_cooler": 4, "if_warmer": 1})
        assert outfit.if_cooler_item_id is None
        assert outfit.if_warmer_item_id is None
        body = (await client.get(f"/api/v1/outfits/{outfit.id}", headers=auth_headers)).json()
        assert body["if_cooler"] is None
        assert body["if_warmer"] is None

    async def test_list_endpoint_includes_extras(self, client, db_session, test_user, auth_headers):
        items = await _wardrobe(db_session, test_user.id)
        await self._save(db_session, test_user, items, {"if_cooler": 5})
        response = await client.get("/api/v1/outfits", headers=auth_headers)
        assert response.status_code == 200
        [entry] = response.json()["outfits"]
        assert entry["if_cooler"]["type"] == "cardigan"
        assert entry["if_warmer"] is None

    async def test_deleting_the_item_clears_the_extra(
        self, client, db_session, test_user, auth_headers
    ):
        items = await _wardrobe(db_session, test_user.id)
        outfit = await self._save(db_session, test_user, items, {"if_cooler": 5})
        outfit_id = outfit.id
        await db_session.execute(
            delete(ClothingItem).where(ClothingItem.id == items["cardigan"].id)
        )
        await db_session.commit()
        db_session.expire_all()
        body = (await client.get(f"/api/v1/outfits/{outfit_id}", headers=auth_headers)).json()
        assert body["if_cooler"] is None
        assert (await db_session.get(Outfit, outfit_id)) is not None

    async def test_extra_that_no_longer_fits_the_outfit_is_hidden(
        self, client, db_session, test_user, auth_headers
    ):
        items = await _wardrobe(db_session, test_user.id)
        outfit = await self._save(db_session, test_user, items, {"if_cooler": 5, "if_warmer": 4})
        jacket_id, cardigan_id, outfit_id = items["jacket"].id, items["cardigan"].id, outfit.id
        # An edit removes the jacket and puts the cardigan in the outfit.
        await db_session.execute(
            delete(OutfitItem).where(
                OutfitItem.outfit_id == outfit_id, OutfitItem.item_id == jacket_id
            )
        )
        db_session.add(OutfitItem(outfit_id=outfit_id, item_id=cardigan_id, position=9))
        await db_session.commit()
        db_session.expire_all()
        body = (await client.get(f"/api/v1/outfits/{outfit_id}", headers=auth_headers)).json()
        assert body["if_cooler"] is None
        assert body["if_warmer"] is None


class TestMigration:
    async def _columns(self, db_session):
        rows = await db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'outfits' AND column_name LIKE 'if\\_%'"
            )
        )
        return {row[0] for row in rows}

    async def test_up_and_down(self, db_session):
        assert await self._columns(db_session) == {"if_cooler_item_id", "if_warmer_item_id"}
        async with migration_downgrade(db_session, PREVIOUS):
            assert await self._columns(db_session) == set()
        await db_session.rollback()
        assert await self._columns(db_session) == {"if_cooler_item_id", "if_warmer_item_id"}
