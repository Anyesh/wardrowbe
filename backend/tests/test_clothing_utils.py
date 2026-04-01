from uuid import uuid4

from app.utils.clothing import BODY_SLOT_MAP, deduplicate_by_body_slot


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


def test_removes_duplicate_top():
    tshirt_id, sweater_id, pants_id = _ids(3)
    item_type_map = {
        tshirt_id: "t-shirt",
        sweater_id: "sweater",
        pants_id: "jeans",
    }
    result = deduplicate_by_body_slot([tshirt_id, sweater_id, pants_id], item_type_map)
    assert tshirt_id in result
    assert sweater_id not in result
    assert pants_id in result


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


def test_body_slot_map_covers_all_clothing_analysis_types():
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
        assert t in BODY_SLOT_MAP, f"Missing type '{t}' in BODY_SLOT_MAP"
