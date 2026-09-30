from app.api.analytics import composition_insights
from app.utils.clothing import count_composition

LAYERS = (
    "Most of your tops are layers like cardigans and vests. Add a few basics to wear under them!"
)
MORE_TOPS = "You have many more tops than bottoms. Consider adding pants or skirts!"
MORE_BOTTOMS = "You have more bottoms than tops. Consider adding some shirts!"


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
