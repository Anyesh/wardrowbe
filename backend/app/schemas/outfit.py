from typing import Annotated

from pydantic import BaseModel, Field, field_validator

MAX_AUTHORING_TEXT_LENGTH = 2000


class OutfitAttributeFields(BaseModel):
    """Optional descriptive outfit attributes shared by the authoring and studio
    request schemas. Free-form, but canonically match the item tag vocabulary
    (season: spring/summer/fall/winter/all-season; formality: very-casual
    through very-formal).
    """

    season: Annotated[str | None, Field(max_length=20)] = None
    formality: Annotated[str | None, Field(max_length=50)] = None
    palette: list[str] | None = Field(
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

    @field_validator("palette")
    @classmethod
    def validate_palette(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        colors = [c.strip().lower() for c in v]
        if any(not c or len(c) > 50 for c in colors):
            raise ValueError("Palette colors must be 1-50 characters")
        # [] collapses to None so "no palette" has a single representation
        return colors or None
