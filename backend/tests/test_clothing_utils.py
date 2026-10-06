from uuid import uuid4

from app.utils.clothing import (
    _CANONICAL_ROLE_ORDER,
    ITEM_ROLE,
    WardrobeComposition,
    canonical_item_order,
    count_composition,
    deduplicate_by_body_slot,
)


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


def test_tights_coexist_with_skirt_and_socks_but_only_one_legwear_item():
    skirt, tights, other_tights, socks, shoes = _ids(5)
    item_type_map = {
        skirt: "skirt",
        tights: "tights",
        other_tights: "tights",
        socks: "socks",
        shoes: "shoes",
    }
    result = deduplicate_by_body_slot([skirt, tights, other_tights, socks, shoes], item_type_map)
    assert result == [skirt, tights, socks, shoes]


def test_tights_coexist_with_dress():
    dress, tights, shoes = _ids(3)
    item_type_map = {dress: "dress", tights: "tights", shoes: "shoes"}
    assert deduplicate_by_body_slot([dress, tights, shoes], item_type_map) == [dress, tights, shoes]


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


def test_suit_replaces_trousers_but_keeps_shirt_and_overcoat():
    suit, other_suit, shirt, pants, coat, tie, shoes = _ids(7)
    item_type_map = {
        suit: "suit",
        other_suit: "suit",
        shirt: "shirt",
        pants: "pants",
        coat: "coat",
        tie: "tie",
        shoes: "shoes",
    }
    result = deduplicate_by_body_slot(
        [shirt, pants, suit, other_suit, coat, tie, shoes], item_type_map
    )
    assert result == [shirt, suit, coat, tie, shoes]


def test_suit_allows_a_mid_layer_under_it():
    suit, shirt, vest = _ids(3)
    item_type_map = {suit: "suit", shirt: "shirt", vest: "vest"}
    assert deduplicate_by_body_slot([shirt, vest, suit], item_type_map) == [shirt, vest, suit]


def test_first_multi_slot_item_wins_when_they_overlap():
    dress, suit = _ids(2)
    item_type_map = {dress: "dress", suit: "suit"}
    assert deduplicate_by_body_slot([dress, suit], item_type_map) == [dress]
    assert deduplicate_by_body_slot([suit, dress], item_type_map) == [suit]


def test_two_dresses_keep_only_the_first():
    first, second = _ids(2)
    item_type_map = {first: "dress", second: "jumpsuit"}
    assert deduplicate_by_body_slot([first, second], item_type_map) == [first]


def test_mandatory_suit_beats_later_trousers_and_keeps_shirt():
    suit, shirt, pants = _ids(3)
    item_type_map = {suit: "suit", shirt: "shirt", pants: "pants"}
    result = deduplicate_by_body_slot(
        [pants, shirt, suit], item_type_map, mandatory_item_ids={suit}
    )
    assert result == [shirt, suit]


def test_mandatory_trousers_beat_a_suit():
    suit, pants = _ids(2)
    item_type_map = {suit: "suit", pants: "pants"}
    result = deduplicate_by_body_slot([suit, pants], item_type_map, mandatory_item_ids={pants})
    assert result == [pants]


def test_canonical_order_puts_suit_with_the_outer_layers():
    shirt, suit, shoes = _ids(3)
    item_type_map = {shirt: "shirt", suit: "suit", shoes: "shoes"}
    assert canonical_item_order([shoes, suit, shirt], item_type_map) == [shirt, suit, shoes]


def test_canonical_order_covers_every_item_role():
    assert set(ITEM_ROLE.values()) <= set(_CANONICAL_ROLE_ORDER)


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


def test_mandatory_item_overrides_earlier_duplicate():
    ai_shirt_id, mandatory_shirt_id, pants_id = _ids(3)
    item_type_map = {
        ai_shirt_id: "t-shirt",
        mandatory_shirt_id: "polo",
        pants_id: "jeans",
    }
    result = deduplicate_by_body_slot(
        [ai_shirt_id, mandatory_shirt_id, pants_id],
        item_type_map,
        mandatory_item_ids={mandatory_shirt_id},
    )
    assert mandatory_shirt_id in result
    assert ai_shirt_id not in result
    assert pants_id in result


def test_mandatory_separate_drops_non_mandatory_full_body():
    dress_id, mandatory_pants_id, shoes_id = _ids(3)
    item_type_map = {
        dress_id: "dress",
        mandatory_pants_id: "pants",
        shoes_id: "sneakers",
    }
    result = deduplicate_by_body_slot(
        [dress_id, mandatory_pants_id, shoes_id],
        item_type_map,
        mandatory_item_ids={mandatory_pants_id},
    )
    assert mandatory_pants_id in result
    assert dress_id not in result
    assert shoes_id in result


def test_mandatory_full_body_drops_non_mandatory_separates():
    mandatory_dress_id, shirt_id, pants_id, shoes_id = _ids(4)
    item_type_map = {
        mandatory_dress_id: "dress",
        shirt_id: "shirt",
        pants_id: "jeans",
        shoes_id: "boots",
    }
    result = deduplicate_by_body_slot(
        [shirt_id, mandatory_dress_id, pants_id, shoes_id],
        item_type_map,
        mandatory_item_ids={mandatory_dress_id},
    )
    assert mandatory_dress_id in result
    assert shirt_id not in result
    assert pants_id not in result
    assert shoes_id in result


def test_two_mandatory_items_in_one_role_do_not_both_survive():
    shirt_a, shirt_b, pants_id = _ids(3)
    item_type_map = {shirt_a: "shirt", shirt_b: "polo", pants_id: "jeans"}
    result = deduplicate_by_body_slot(
        [shirt_a, shirt_b, pants_id],
        item_type_map,
        mandatory_item_ids={shirt_a, shirt_b},
    )
    assert result == [shirt_a, pants_id]


def test_mandatory_full_body_and_mandatory_separates_do_not_coexist():
    dress_id, pants_id, shoes_id = _ids(3)
    item_type_map = {dress_id: "dress", pants_id: "jeans", shoes_id: "boots"}
    result = deduplicate_by_body_slot(
        [dress_id, pants_id, shoes_id],
        item_type_map,
        mandatory_item_ids={dress_id, pants_id},
    )
    assert result == [dress_id, shoes_id]


def test_mandatory_item_absent_from_candidates_does_not_empty_its_role():
    absent_shirt, shirt_id, pants_id = _ids(3)
    item_type_map = {shirt_id: "shirt", pants_id: "jeans"}
    result = deduplicate_by_body_slot(
        [shirt_id, pants_id],
        item_type_map,
        mandatory_item_ids={absent_shirt},
    )
    assert result == [shirt_id, pants_id]


def test_count_composition_buckets_by_role():
    c = count_composition(
        [
            ("cardigan", 8),
            ("shirt", 1),
            ("Sweater", 2),
            ("skirt", 4),
            ("dress", 3),
            ("jacket", 5),
            ("mystery", 7),
            (None, 1),
        ]
    )
    assert c == WardrobeComposition(base_tops=3, layers=8, bottoms=4, full_body=3)


def test_count_composition_covers_every_role_in_item_role():
    c = count_composition([(t, 1) for t in ITEM_ROLE])
    roles = list(ITEM_ROLE.values())
    assert c.base_tops == roles.count("base_top")
    assert c.layers == roles.count("mid_layer")
    assert c.bottoms == roles.count("bottom")
    assert c.full_body == roles.count("full_body")
