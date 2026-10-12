import json
import re
from pathlib import Path

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
from app.utils.garment_vocabulary import (
    COLOR_ALIASES,
    COLORS,
    FORMALITY,
    ITEM_ROLE,
    MATERIALS,
    OCCASIONS,
    ROLES,
    TYPES,
    canonical_color,
    canonical_colors,
    normalize_color,
    render_tagging_prompt,
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
PRE_VOCABULARY_COLORS = {
    "black", "white", "gray", "navy", "blue", "light-blue", "red", "burgundy", "pink", "green",
    "olive", "yellow", "orange", "purple", "brown", "tan", "beige", "cream", "gold", "silver",
}  # fmt: skip


def test_stored_colors_are_the_set_the_tagger_validated():
    assert set(COLORS) == PRE_VOCABULARY_COLORS


@pytest.mark.parametrize("alias", sorted(COLOR_ALIASES))
def test_color_alias_is_a_lowercase_name_for_a_stored_color(alias):
    assert alias == alias.strip().lower()
    assert alias not in PRE_VOCABULARY_COLORS
    assert normalize_color(alias) in PRE_VOCABULARY_COLORS


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
    ) == ["gray", "chartreuse", "tan", "navy"]
