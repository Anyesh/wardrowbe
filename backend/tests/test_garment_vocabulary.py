import re

import pytest

from app.schemas.item import DEFAULT_WASH_INTERVALS
from app.services.ai_service import TAGGING_PROMPT, VALID_FORMALITY, VALID_MATERIALS, VALID_TYPES
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
    FORMALITY,
    MATERIALS,
    OCCASIONS,
    TYPES,
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


def test_every_type_has_a_known_role_and_a_positive_wash_interval():
    assert set(ITEM_ROLE.values()) <= set(_CANONICAL_ROLE_ORDER)
    assert all(interval > 0 for interval in DEFAULT_WASH_INTERVALS.values())


def test_prompt_template_tokens_are_all_rendered():
    template = load_prompt("clothing_analysis")
    for token in ("<<TYPES>>", "<<MATERIALS>>", "<<FORMALITY>>"):
        assert token in template
    assert "<<" not in render_tagging_prompt(template)


def test_type_lists_agree():
    prompt_types = _prompt_options("TYPE")
    assert prompt_types == VALID_TYPES
    assert prompt_types == set(ITEM_ROLE)
    assert prompt_types == set(DEFAULT_WASH_INTERVALS)


@pytest.mark.parametrize(
    ("heading", "vocabulary"),
    [("MATERIAL", VALID_MATERIALS), ("FORMALITY", VALID_FORMALITY)],
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
