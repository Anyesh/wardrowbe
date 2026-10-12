from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, field_validator

from app.schemas.color import ColorList
from app.utils.garment_vocabulary import OCCASIONS
from app.utils.preference_defaults import DEFAULT_OCCASION

MAX_AUTHORING_TEXT_LENGTH = 2000
VALID_OCCASIONS = frozenset(OCCASIONS)


def _normalize_occasion(value: str) -> str:
    occasion = value.strip().lower()
    if occasion not in VALID_OCCASIONS:
        raise ValueError(
            f"Invalid occasion '{occasion}'. Must be one of: {', '.join(sorted(VALID_OCCASIONS))}"
        )
    return occasion


Occasion = Annotated[str, Field(max_length=50), AfterValidator(_normalize_occasion)]


# Default occasions saved before they were validated can hold any string, and reading them back
# must not fail, so an unlisted one reads as the default.
def stored_occasion_or_default(value: str | None) -> str:
    try:
        return _normalize_occasion(value) if value else DEFAULT_OCCASION
    except ValueError:
        return DEFAULT_OCCASION


class OutfitAttributeFields(BaseModel):
    """Optional descriptive outfit attributes shared by the authoring and studio
    request schemas. Free-form, but canonically match the item tag vocabulary
    (season: spring/summer/fall/winter/all-season; formality: very-casual
    through very-formal).
    """

    season: Annotated[str | None, Field(max_length=20)] = None
    formality: Annotated[str | None, Field(max_length=50)] = None
    palette: ColorList | None = Field(
        default=None,
        max_length=10,
        description="Dominant outfit colors, most prominent first",
    )
    notes: Annotated[str | None, Field(max_length=MAX_AUTHORING_TEXT_LENGTH)] = None

    @field_validator("season", "formality")
    @classmethod
    def normalize_label(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip().lower() or None

    @field_validator("palette", mode="before")
    @classmethod
    def validate_palette_lengths(cls, v: object) -> object:
        if isinstance(v, list) and any(
            isinstance(c, str) and not 1 <= len(c.strip()) <= 50 for c in v
        ):
            raise ValueError("Palette colors must be 1-50 characters")
        return v

    @field_validator("palette")
    @classmethod
    def collapse_empty_palette(cls, v: list[str] | None) -> list[str] | None:
        # [] collapses to None so "no palette" has a single representation
        return v or None
