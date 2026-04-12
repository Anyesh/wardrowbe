from uuid import uuid4

from app.utils.clothing import ITEM_ROLE, canonical_item_order, deduplicate_by_body_slot


def _ids(n):
    return [uuid4() for _ in range(n)]


def test_removes_duplicate_bottom():
    pants_id, shorts_id, shirt_id, shoes_id = _ids(4)
    item_type_map = {
        shirt_id: "shirt",
        pants_id: "pants",
        shorts_id: "shorts",
        shoes_id: "sneakers",
    }
    result = deduplicate_by_body_slot([shirt_id, pants_id, shorts_id, shoes_id], item_type_map)
    assert pants_id in result
    assert shorts_id not in result
    assert len(result) == 3


def test_removes_duplicate_base_top():
    tshirt_id, polo_id, pants_id = _ids(3)
    item_type_map = {
        tshirt_id: "t-shirt",
        polo_id: "polo",
        pants_id: "jeans",
    }
    result = deduplicate_by_body_slot([tshirt_id, polo_id, pants_id], item_type_map)
    assert tshirt_id in result
    assert polo_id not in result
    assert pants_id in result


def test_allows_layering_base_top_plus_mid_layer():
    tshirt_id, cardigan_id, pants_id = _ids(3)
    item_type_map = {
        tshirt_id: "t-shirt",
        cardigan_id: "cardigan",
        pants_id: "jeans",
    }
    result = deduplicate_by_body_slot([tshirt_id, cardigan_id, pants_id], item_type_map)
    assert tshirt_id in result
    assert cardigan_id in result
    assert pants_id in result
    assert len(result) == 3


def test_allows_layering_base_top_plus_outer_layer():
    shirt_id, jacket_id, pants_id = _ids(3)
    item_type_map = {
        shirt_id: "shirt",
        jacket_id: "jacket",
        pants_id: "pants",
    }
    result = deduplicate_by_body_slot([shirt_id, jacket_id, pants_id], item_type_map)
    assert len(result) == 3


def test_keeps_first_item_per_slot():
    jeans_id, skirt_id = _ids(2)
    item_type_map = {jeans_id: "jeans", skirt_id: "skirt"}
    result = deduplicate_by_body_slot([jeans_id, skirt_id], item_type_map)
    assert result == [jeans_id]


def test_full_body_removes_separate_top_and_bottom():
    dress_id, shirt_id, pants_id, shoes_id = _ids(4)
    item_type_map = {
        dress_id: "dress",
        shirt_id: "shirt",
        pants_id: "pants",
        shoes_id: "shoes",
    }
    result = deduplicate_by_body_slot([dress_id, shirt_id, pants_id, shoes_id], item_type_map)
    assert dress_id in result
    assert shoes_id in result
    assert shirt_id not in result
    assert pants_id not in result


def test_preserves_unknown_types():
    unknown_id, shirt_id, pants_id = _ids(3)
    item_type_map = {
        unknown_id: "something-new",
        shirt_id: "shirt",
        pants_id: "pants",
    }
    result = deduplicate_by_body_slot([unknown_id, shirt_id, pants_id], item_type_map)
    assert unknown_id in result
    assert shirt_id in result
    assert pants_id in result


def test_no_duplicates_passes_through():
    shirt_id, pants_id, shoes_id, jacket_id = _ids(4)
    item_type_map = {
        shirt_id: "shirt",
        pants_id: "pants",
        shoes_id: "sneakers",
        jacket_id: "jacket",
    }
    ids = [shirt_id, pants_id, shoes_id, jacket_id]
    result = deduplicate_by_body_slot(ids, item_type_map)
    assert result == ids


def test_socks_get_own_slot():
    socks_id, shoes_id, shirt_id = _ids(3)
    item_type_map = {socks_id: "socks", shoes_id: "sneakers", shirt_id: "shirt"}
    result = deduplicate_by_body_slot([socks_id, shoes_id, shirt_id], item_type_map)
    assert socks_id in result
    assert shoes_id in result
    assert len(result) == 3


def test_multiple_accessories_allowed():
    hat_id, scarf_id, belt_id, shirt_id = _ids(4)
    item_type_map = {
        hat_id: "hat",
        scarf_id: "scarf",
        belt_id: "belt",
        shirt_id: "shirt",
    }
    result = deduplicate_by_body_slot([hat_id, scarf_id, belt_id, shirt_id], item_type_map)
    assert len(result) == 4


def test_item_role_covers_all_clothing_analysis_types():
    expected_types = {
        "shirt",
        "t-shirt",
        "top",
        "pants",
        "jeans",
        "shorts",
        "dress",
        "jumpsuit",
        "skirt",
        "jacket",
        "coat",
        "sweater",
        "hoodie",
        "blazer",
        "vest",
        "cardigan",
        "polo",
        "blouse",
        "tank-top",
        "shoes",
        "sneakers",
        "boots",
        "sandals",
        "socks",
        "tie",
    }
    for t in expected_types:
        assert t in ITEM_ROLE, f"Missing type '{t}' in ITEM_ROLE"


def test_canonical_item_order_sorts_by_role():
    dress_id, shoes_id, hat_id = _ids(3)
    item_type_map = {
        hat_id: "hat",
        shoes_id: "sneakers",
        dress_id: "dress",
    }
    result = canonical_item_order([hat_id, shoes_id, dress_id], item_type_map)
    assert result[0] == dress_id
    assert result[1] == shoes_id
    assert result[2] == hat_id


def test_canonical_order_preserves_position_within_same_role():
    hat1, hat2, shirt_id = _ids(3)
    item_type_map = {hat1: "hat", hat2: "scarf", shirt_id: "shirt"}
    result = canonical_item_order([hat1, hat2, shirt_id], item_type_map)
    assert result[0] == shirt_id
    hat_indices = [i for i, x in enumerate(result) if x in (hat1, hat2)]
    assert hat_indices == [1, 2]


def test_canonical_order_full_outfit():
    shirt_id, pants_id, shoes_id, jacket_id, socks_id = _ids(5)
    item_type_map = {
        socks_id: "socks",
        shoes_id: "sneakers",
        jacket_id: "jacket",
        pants_id: "jeans",
        shirt_id: "t-shirt",
    }
    result = canonical_item_order(
        [socks_id, shoes_id, jacket_id, pants_id, shirt_id], item_type_map
    )
    role_order = [ITEM_ROLE.get(item_type_map[iid], "") for iid in result]
    expected_roles = ["base_top", "outer_layer", "bottom", "footwear", "socks"]
    assert role_order == expected_roles


def test_canonical_order_empty_list():
    result = canonical_item_order([], {})
    assert result == []
