import re

import pytest

from app.schemas.item import DEFAULT_WASH_INTERVALS
from app.services.ai_service import VALID_FORMALITY, VALID_MATERIALS, VALID_TYPES
from app.services.item_scorer import (
    FORMALITY_ORDER,
    HEAVY_LAYER_MATERIALS,
    HEAVY_LAYER_TYPES,
    OCCASION_FORMALITY,
    RAIN_LAYER_TYPES,
    WARM_LAYER_TYPES,
)
from app.utils.clothing import ITEM_ROLE
from app.utils.prompts import load_prompt


def _prompt_options(heading: str) -> set[str]:
    match = re.search(
        rf"^{heading} \([^)]*\):\n(.+)\n", load_prompt("clothing_analysis"), re.MULTILINE
    )
    assert match, f"{heading} line not found in clothing_analysis prompt"
    return {term.strip() for term in match.group(1).split(",")}


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
