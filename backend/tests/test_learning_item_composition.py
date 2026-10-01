from app.services.learning_service import slot_composition


def test_every_wearable_type_lands_in_its_slot():
    result = slot_composition(["polo", "jeans", "sneakers", "blazer", "socks", "tie"])
    assert result == {
        "top": "polo",
        "bottom": "jeans",
        "shoes": "sneakers",
        "outerwear": "blazer",
        "socks": "socks",
        "neckwear": "tie",
    }


def test_hoodie_and_tank_top_are_not_dropped():
    assert slot_composition(["Hoodie", "tank-top"]) == {"outerwear": "hoodie", "top": "tank-top"}


def test_layers_dresses_and_suits_are_recorded_under_their_role():
    result = slot_composition(["dress", "cardigan", "suit"])
    assert result == {"full_body": "dress", "mid_layer": "cardigan", "suit": "suit"}


def test_non_types_and_accessories_are_ignored():
    assert slot_composition(["heels", "unknown", None, "hat", "bag"]) == {}
