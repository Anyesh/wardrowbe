import re

import pytest

from app.schemas.item import DEFAULT_WASH_INTERVALS
from app.services.ai_service import (
    TAGGING_PROMPT,
    VALID_COLORS,
    VALID_FORMALITY,
    VALID_MATERIALS,
    VALID_TYPES,
)
from app.services.item_scorer import (
    FORMALITY_ORDER,
    HEAVY_LAYER_MATERIALS,
    HEAVY_LAYER_TYPES,
    OCCASION_FORMALITY,
    RAIN_LAYER_TYPES,
    WARM_LAYER_TYPES,
)
from app.services.pairing_service import PAIRING_OCCASION
from app.utils.clothing import _CANONICAL_ROLE_ORDER, ITEM_ROLE
from app.utils.garment_vocabulary import (
    COLOR_ALIASES,
    COLORS,
    FORMALITY,
    MATERIALS,
    OCCASIONS,
    TYPES,
    canonical_colors,
    normalize_color,
    render_tagging_prompt,
)
from app.utils.prompts import load_prompt


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


def test_every_type_has_a_known_role_and_a_positive_wash_interval():
    assert set(ITEM_ROLE.values()) <= set(_CANONICAL_ROLE_ORDER)
    assert all(interval > 0 for interval in DEFAULT_WASH_INTERVALS.values())


def test_prompt_template_tokens_are_all_rendered():
    template = load_prompt("clothing_analysis")
    for token in ("<<TYPES>>", "<<MATERIALS>>", "<<FORMALITY>>", "<<COLORS>>"):
        assert token in template
    assert "<<" not in render_tagging_prompt(template)


def test_type_lists_agree():
    prompt_types = _prompt_options("TYPE")
    assert prompt_types == VALID_TYPES
    assert prompt_types == set(ITEM_ROLE)
    assert prompt_types == set(DEFAULT_WASH_INTERVALS)


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
    scorer_types = RAIN_LAYER_TYPES | WARM_LAYER_TYPES | HEAVY_LAYER_TYPES
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


def test_scorer_occasion_formality_comes_from_the_vocabulary():
    assert set(OCCASION_FORMALITY) == {
        "casual", "work", "office", "formal", "sporty", "outdoor", "date", "party",
    }  # fmt: skip
    assert set(OCCASION_FORMALITY) <= set(OCCASIONS)
    assert OCCASION_FORMALITY["formal"] == ("business-casual", "formal", "very-formal")


# The colours the tagger validated before the vocabulary owned them. Dropping one would orphan the
# items already stored with it, so a removal needs a data migration, not just a vocabulary edit.
PRE_VOCABULARY_COLORS = {
    "black", "white", "gray", "navy", "blue", "light-blue", "red", "burgundy", "pink", "green",
    "olive", "yellow", "orange", "purple", "brown", "tan", "beige", "cream", "gold", "silver",
}  # fmt: skip


def test_stored_colors_are_the_set_the_tagger_validated():
    assert set(COLORS) == PRE_VOCABULARY_COLORS
    assert set(COLORS) == VALID_COLORS


def test_color_aliases_resolve_to_stored_colors():
    assert set(COLOR_ALIASES.values()) <= set(COLORS)
    assert not set(COLOR_ALIASES) & set(COLORS)
    assert all(alias == alias.lower().strip() for alias in COLOR_ALIASES)


@pytest.mark.parametrize(
    ("name", "stored"),
    [
        ("charcoal", "gray"),
        ("khaki", "tan"),
        ("teal", "blue"),
        ("army-green", "olive"),
        ("dark-brown", "brown"),
        (" Grey ", "gray"),
        ("light-blue", "light-blue"),
        ("gold", "gold"),
        ("chartreuse", None),
        ("", None),
    ],
)
def test_normalize_color(name, stored):
    assert normalize_color(name) == stored


def test_canonical_colors_aliases_dedupes_and_keeps_unknowns_in_order():
    assert canonical_colors(["Charcoal", "gray", " Chartreuse ", "", "khaki", "tan"]) == [
        "gray",
        "chartreuse",
        "tan",
    ]
