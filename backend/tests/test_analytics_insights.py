import pytest
from httpx import AsyncClient

from app.api.analytics import Insight, composition_insights, insight_text_en
from app.models.item import ClothingItem, ItemStatus
from app.utils.clothing import count_composition

LAYERS = Insight(key="insightMostlyLayers")
MORE_TOPS = Insight(key="insightMoreTopsThanBottoms")
MORE_BOTTOMS = Insight(key="insightMoreBottomsThanTops")


def _insights(counts):
    return composition_insights(count_composition(counts))


def test_cardigan_heavy_wardrobe_asks_for_basics_not_shirts():
    # Issue #209: 8 cardigans, 1 shirt, 4 skirts.
    assert _insights([("cardigan", 8), ("shirt", 1), ("skirt", 4)]) == [LAYERS]


def test_layers_with_enough_basics_are_fine():
    assert _insights([("cardigan", 4), ("t-shirt", 3), ("sweater", 1), ("jeans", 3)]) == []


def test_sweaters_and_polos_count_as_tops():
    assert _insights([("sweater", 4), ("polo", 3), ("tank-top", 3), ("pants", 2)]) == [MORE_TOPS]


def test_more_bottoms_than_tops():
    assert _insights([("shirt", 1), ("jeans", 3)]) == [MORE_BOTTOMS]


def test_balanced_wardrobe_has_no_composition_insight():
    assert _insights([("shirt", 4), ("blouse", 2), ("pants", 3)]) == []


def test_dress_first_wardrobe_is_not_told_to_buy_pants():
    assert _insights([("dress", 10), ("top", 4), ("skirt", 1)]) == []


def test_outer_layers_do_not_count_as_tops():
    assert _insights([("jacket", 6), ("hoodie", 4), ("shirt", 1), ("jeans", 3)]) == [MORE_BOTTOMS]


def test_empty_or_unknown_types_have_no_insight():
    assert _insights([]) == []
    assert _insights([("mystery", 5), (None, 2)]) == []


def test_layers_worn_over_dresses_are_not_flagged():
    assert _insights([("dress", 10), ("cardigan", 4), ("shirt", 1)]) == []


def test_layers_without_dresses_or_basics_are_still_flagged():
    assert _insights([("cardigan", 8), ("shirt", 1), ("skirt", 4)]) == [LAYERS]


def test_dresses_and_base_tops_are_summed_for_the_layers_check():
    assert _insights([("cardigan", 8), ("shirt", 2), ("dress", 2), ("skirt", 2)]) == []
    assert _insights([("cardigan", 9), ("shirt", 2), ("dress", 2), ("skirt", 2)]) == [LAYERS]


@pytest.mark.parametrize(
    ("insight", "text"),
    [
        (Insight(key="insightStartAdding"), "Start by adding some items to your wardrobe!"),
        (
            Insight(key="insightNeverWorn", params={"count": 1}),
            "You have 1 item you've never worn. Consider styling it!",
        ),
        (
            Insight(key="insightNeverWorn", params={"count": 4}),
            "You have 4 items you've never worn. Consider styling them!",
        ),
        (
            Insight(key="insightColorHeavy", params={"color": "navy", "percent": 45.5}),
            "Your wardrobe is heavy on navy (45.5%). Consider adding variety!",
        ),
        (
            Insight(key="insightGreatTaste", params={"percent": 85}),
            "Great taste! You accept 85% of suggestions.",
        ),
        (
            LAYERS,
            "Most of your tops are layers like cardigans and vests. "
            "Add a few basics to wear under them!",
        ),
        (MORE_TOPS, "You have many more tops than bottoms. Consider adding pants or skirts!"),
        (MORE_BOTTOMS, "You have more bottoms than tops. Consider adding some shirts!"),
    ],
)
def test_legacy_english_strings_are_unchanged(insight, text):
    assert insight_text_en(insight) == text


@pytest.mark.asyncio
async def test_api_sends_insight_keys_alongside_the_english_text(
    client: AsyncClient, db_session, test_user, auth_headers
):
    for item_type, count in (("cardigan", 8), ("shirt", 1), ("skirt", 4)):
        for i in range(count):
            db_session.add(
                ClothingItem(
                    user_id=test_user.id,
                    type=item_type,
                    status=ItemStatus.ready,
                    image_path=f"test/{item_type}-{i}.jpg",
                    primary_color="black",
                )
            )
    await db_session.commit()

    response = await client.get("/api/v1/analytics", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert {"key": "insightMostlyLayers", "params": {}} in body["insight_items"]
    assert "insightNeverWorn" in [item["key"] for item in body["insight_items"]]
    assert body["insights"] == [insight_text_en(Insight(**item)) for item in body["insight_items"]]


@pytest.mark.asyncio
async def test_empty_wardrobe_gets_the_start_adding_key(
    client: AsyncClient, test_user, auth_headers
):
    response = await client.get("/api/v1/analytics", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["insight_items"] == [{"key": "insightStartAdding", "params": {}}]
    assert body["insights"] == ["Start by adding some items to your wardrobe!"]
