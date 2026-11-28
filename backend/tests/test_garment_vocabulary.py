import json
import re
from pathlib import Path

import pytest

from app.schemas.item import DEFAULT_WASH_INTERVALS
from app.services.ai_service import (
    TAGGING_PROMPT,
    VALID_COLORS,
    VALID_FIT,
    VALID_FORMALITY,
    VALID_MATERIALS,
    VALID_PATTERNS,
    VALID_SEASONS,
    VALID_STYLES,
    VALID_TYPES,
)
from app.services.item_scorer import (
    COLD_EXPOSED_TYPES,
    FORMALITY_ORDER,
    HEAVY_LAYER_MATERIALS,
    HEAVY_LAYER_TYPES,
    HOT_PENALTY_TYPES,
    OCCASION_FORMALITY,
    RAIN_LAYER_TYPES,
    WARM_LAYER_TYPES,
)
from app.services.pairing_service import PAIRING_OCCASION
from app.utils.garment_vocabulary import (
    COLOR_ALIASES,
    COLOR_FAMILIES,
    COLOR_FAMILY,
    COLORS,
    FITS,
    FORMALITY,
    ITEM_ROLE,
    MATERIALS,
    OCCASIONS,
    PATTERNS,
    ROLES,
    SEASONS,
    STYLES,
    SUBTYPES,
    TYPES,
    canonical_color,
    canonical_colors,
    color_family,
    normalize_color,
    render_outfit_prompt,
    render_tagging_prompt,
    types_for_role,
)
from app.utils.prompts import load_prompt

COLOR_NAME_CASES = json.loads((Path(__file__).parent / "fixtures" / "color_names.json").read_text())


def _prompt_options(heading: str) -> set[str]:
    match = re.search(rf"^{heading} \([^)]*\):\n(.+)\n", TAGGING_PROMPT, re.MULTILINE)
    assert match, f"{heading} line not found in clothing_analysis prompt"
    return {term.strip() for term in match.group(1).split(",")}


def test_vocabulary_entries_are_unique():
    assert len(set(TYPES)) == len(TYPES)
    assert len(set(MATERIALS)) == len(MATERIALS)
    assert len(set(FORMALITY)) == len(FORMALITY)
    assert len(set(OCCASIONS)) == len(OCCASIONS)
    assert len(set(COLORS)) == len(COLORS)
    assert len(set(ROLES)) == len(ROLES)


def test_every_type_has_a_known_role_and_a_positive_wash_interval():
    assert set(ITEM_ROLE.values()) <= set(ROLES)
    assert all(interval > 0 for interval in DEFAULT_WASH_INTERVALS.values())


def test_prompt_template_tokens_are_all_rendered():
    template = load_prompt("clothing_analysis")
    for token in (
        "<<TYPES>>",
        "<<SUBTYPES>>",
        "<<MATERIALS>>",
        "<<FORMALITY>>",
        "<<COLORS>>",
        "<<PATTERNS>>",
        "<<STYLES>>",
        "<<SEASONS>>",
        "<<FITS>>",
    ):
        assert token in template
    assert "<<" not in render_tagging_prompt(template)


def test_prompt_suggests_exactly_the_vocabulary_subtypes():
    match = re.search(r"^SUBTYPE \([^)]*\):[^\n]*\n((?:- .+\n)+)", TAGGING_PROMPT, re.MULTILINE)
    assert match, "SUBTYPE examples not found in clothing_analysis prompt"
    rendered = {}
    for line in match.group(1).splitlines():
        type_, subtypes = line.removeprefix("- ").split(" → ")
        rendered[type_] = tuple(s.strip() for s in subtypes.split(","))
    assert rendered == SUBTYPES
    assert list(rendered) == [t for t in TYPES if t in SUBTYPES]


def test_subtypes_belong_to_real_types():
    assert set(SUBTYPES) <= set(TYPES)
    for type_, subtypes in SUBTYPES.items():
        assert subtypes, type_
        assert len(set(subtypes)) == len(subtypes), type_
        assert all(s == s.strip().lower() for s in subtypes), type_


# A subtype example that names a type steers the tagger to file that garment under the wrong
# type. Dress socks are the one homonym.
def test_no_subtype_names_a_type():
    clashes = [
        f"{type_} → {subtype}"
        for type_, subtypes in SUBTYPES.items()
        for subtype in subtypes
        if subtype in TYPES
    ]
    assert clashes == ["socks → dress"]


@pytest.mark.parametrize(
    ("heading", "values"),
    [("PATTERN", PATTERNS), ("STYLE", STYLES), ("SEASON", SEASONS), ("FIT", FITS)],
)
def test_tag_lists_in_the_prompt_come_from_the_vocabulary(heading, values):
    assert _prompt_options(heading) == set(values)
    assert len(set(values)) == len(values)
    assert all(value == value.strip().lower() for value in values)


def test_validators_use_the_vocabulary_lists():
    assert VALID_PATTERNS == set(PATTERNS)
    assert VALID_STYLES == set(STYLES)
    assert VALID_SEASONS == set(SEASONS)
    assert VALID_FIT == set(FITS)


def test_type_lists_agree():
    prompt_types = _prompt_options("TYPE")
    assert prompt_types == VALID_TYPES
    assert prompt_types == set(ITEM_ROLE)
    assert prompt_types == set(DEFAULT_WASH_INTERVALS)


@pytest.mark.parametrize(
    ("item_type", "role"),
    [
        ("leggings", "bottom"),
        ("camisole", "base_top"),
        ("bodysuit", "base_top"),
        ("sweatshirt", "base_top"),
        ("heels", "footwear"),
        ("flats", "footwear"),
        ("overalls", "bottom"),
        ("poncho", "outer_layer"),
        ("watch", "accessory"),
    ],
)
def test_type_has_its_outfit_role(item_type, role):
    assert ITEM_ROLE.get(item_type) == role
    assert item_type in VALID_TYPES


def test_types_for_role_is_derived_from_the_vocabulary():
    # Compared against ITEM_ROLE rather than fixed lists, so adding a garment to a role fails this
    # test unless types_for_role picks it up.
    for role in ROLES:
        assert types_for_role(role) == [t for t in TYPES if ITEM_ROLE[t] == role]

    # Every type belongs to exactly one role, so the per-role lists together cover the taxonomy.
    covered = [t for role in ROLES for t in types_for_role(role)]
    assert sorted(covered) == sorted(TYPES)


def test_outfit_prompt_template_tokens_are_all_rendered():
    for name in ("recommendation", "item_pairing"):
        assert "<<" not in render_outfit_prompt(load_prompt(name))


@pytest.mark.parametrize("prompt_name", ["recommendation", "item_pairing"])
def test_outfit_prompts_list_the_vocabulary_for_each_silhouette_role(prompt_name):
    prompt = render_outfit_prompt(load_prompt(prompt_name))
    for role in ("base_top", "bottom", "full_body", "suit", "footwear", "legwear"):
        assert f"({', '.join(types_for_role(role))})" in prompt, (
            f"{role} missing from {prompt_name}"
        )


@pytest.mark.parametrize(
    ("heading", "vocabulary"),
    [
        ("MATERIAL", VALID_MATERIALS),
        ("FORMALITY", VALID_FORMALITY),
        ("PRIMARY_COLOR", VALID_COLORS),
    ],
)
def test_prompt_offers_exactly_the_validated_vocabulary(heading, vocabulary):
    assert _prompt_options(heading) == vocabulary


def test_scorer_formality_scale_is_the_validated_vocabulary():
    assert set(FORMALITY_ORDER) == VALID_FORMALITY
    for occasion, formalities in OCCASION_FORMALITY.items():
        assert set(formalities) <= VALID_FORMALITY, occasion


def test_scorer_layer_types_are_real_types():
    scorer_types = (
        RAIN_LAYER_TYPES
        | WARM_LAYER_TYPES
        | HEAVY_LAYER_TYPES
        | COLD_EXPOSED_TYPES
        | HOT_PENALTY_TYPES
    )
    assert scorer_types <= VALID_TYPES


def test_scorer_heavy_materials_are_real_materials():
    assert HEAVY_LAYER_MATERIALS <= VALID_MATERIALS


# The union of the suggestion, studio, authoring and schedule validators before they shared one
# list; schedules accepted only the first eight.
PRE_VOCABULARY_OCCASIONS = {
    "casual", "office", "work", "formal", "smart-casual", "business-casual", "date", "party",
    "sporty", "sport", "outdoor", "travel", "lounge", "beach", "interview", "wedding", "dinner",
    "brunch", "gym", "running", "hiking", "weekend",
}  # fmt: skip


def test_occasions_are_the_union_every_validator_accepted():
    assert set(OCCASIONS) == PRE_VOCABULARY_OCCASIONS


def test_server_set_pairing_occasion_cannot_be_authored():
    assert PAIRING_OCCASION not in OCCASIONS


# Without a range the scorer treats an occasion as casual, which ranked jeans first for interviews.
def test_every_occasion_has_a_formality_range():
    assert set(OCCASION_FORMALITY) == PRE_VOCABULARY_OCCASIONS
    assert all(OCCASION_FORMALITY.values())


@pytest.mark.parametrize(
    ("occasion", "formalities"),
    [
        ("formal", ("business-casual", "formal", "very-formal")),
        ("interview", ("business-casual", "formal", "very-formal")),
        ("wedding", ("business-casual", "formal", "very-formal")),
        ("brunch", ("casual", "smart-casual")),
        ("gym", ("very-casual", "casual")),
    ],
)
def test_scorer_occasion_formality_comes_from_the_vocabulary(occasion, formalities):
    assert OCCASION_FORMALITY[occasion] == formalities


# The colours the tagger validated before the vocabulary owned them. Dropping one would orphan the
# items already stored with it, so a removal needs a data migration, not just a vocabulary edit.
# The shades added since sit beside them.
PRE_VOCABULARY_COLORS = {
    "black", "white", "gray", "navy", "blue", "light-blue", "red", "burgundy", "pink", "green",
    "olive", "yellow", "orange", "purple", "brown", "tan", "beige", "cream", "gold", "silver",
}  # fmt: skip


def test_stored_colors_keep_every_colour_the_tagger_validated():
    assert PRE_VOCABULARY_COLORS <= set(COLORS)


def test_every_shade_belongs_to_a_family_and_every_family_has_shades():
    assert set(COLOR_FAMILY) == set(COLORS)
    assert set(COLOR_FAMILY.values()) == set(COLOR_FAMILIES)
    assert len(set(COLOR_FAMILIES)) == len(COLOR_FAMILIES)
    assert not set(COLOR_FAMILIES) & set(COLORS)


@pytest.mark.parametrize(
    ("name", "family"),
    [
        ("navy", "blues"),
        ("Sapphire", "blues"),
        ("light blue", "blues"),
        ("dark grey", "blacks-grays"),
        ("blues", "blues"),
        ("Whites Creams", "whites-creams"),
        ("chartreuse", None),
        ("", None),
    ],
)
def test_color_family(name, family):
    assert color_family(name) == family


@pytest.mark.parametrize("alias", sorted(COLOR_ALIASES))
def test_color_alias_is_a_lowercase_name_for_a_stored_color(alias):
    assert alias == alias.strip().lower()
    assert alias not in COLORS
    assert normalize_color(alias) in COLORS


@pytest.mark.parametrize(
    ("name", "normalized", "canonical"),
    [(case["name"], case["normalized"], case["canonical"]) for case in COLOR_NAME_CASES],
)
def test_color_name_rule(name, normalized, canonical):
    assert normalize_color(name) == normalized
    assert canonical_color(name) == canonical


def test_canonical_colors_aliases_dedupes_and_keeps_unknowns_in_order():
    assert canonical_colors(
        [
            "Charcoal",
            "gray",
            " Chartreuse ",
            "",
            "khaki",
            "\u00a0\t",
            "tan",
            "dark\u00a0 blue",
            "navy",
        ]
    ) == ["charcoal", "gray", "chartreuse", "khaki", "tan", "navy"]
