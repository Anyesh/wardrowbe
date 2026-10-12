from pydantic import BaseModel, Field

from app.schemas.color import ColorList
from app.schemas.outfit import Occasion
from app.utils.preference_defaults import (
    DEFAULT_LAYERING_PREFERENCE,
    DEFAULT_OCCASION,
    DEFAULT_PREFER_UNDERUSED_ITEMS,
    DEFAULT_TEMPERATURE_SENSITIVITY,
    DEFAULT_TEMPERATURE_UNIT,
    DEFAULT_VARIETY_LEVEL,
)
from app.utils.scales import (
    AVOID_REPEAT_DAYS_MAX,
    AVOID_REPEAT_DAYS_MIN,
    COLD_THRESHOLD_MAX,
    COLD_THRESHOLD_MIN,
    DEFAULT_AVOID_REPEAT_DAYS,
    DEFAULT_COLD_THRESHOLD,
    DEFAULT_HOT_THRESHOLD,
    DEFAULT_STYLE_SCORE,
    HOT_THRESHOLD_MAX,
    HOT_THRESHOLD_MIN,
    STYLE_SCORE_MAX,
    STYLE_SCORE_MIN,
)


class AIEndpoint(BaseModel):
    name: str = Field(description="Display name for this endpoint")
    url: str = Field(description="Base URL for the AI API (e.g., http://localhost:11434/v1)")
    vision_model: str = Field(default="moondream", description="Model for image analysis")
    text_model: str = Field(default="phi3:mini", description="Model for text generation")
    enabled: bool = Field(default=True, description="Whether this endpoint is active")


class StyleProfile(BaseModel):
    casual: int = Field(
        default=DEFAULT_STYLE_SCORE,
        ge=STYLE_SCORE_MIN,
        le=STYLE_SCORE_MAX,
        description="Casual style preference 0-100",
    )
    formal: int = Field(
        default=DEFAULT_STYLE_SCORE,
        ge=STYLE_SCORE_MIN,
        le=STYLE_SCORE_MAX,
        description="Formal style preference 0-100",
    )
    sporty: int = Field(
        default=DEFAULT_STYLE_SCORE,
        ge=STYLE_SCORE_MIN,
        le=STYLE_SCORE_MAX,
        description="Sporty style preference 0-100",
    )
    minimalist: int = Field(
        default=DEFAULT_STYLE_SCORE,
        ge=STYLE_SCORE_MIN,
        le=STYLE_SCORE_MAX,
        description="Minimalist style preference 0-100",
    )
    bold: int = Field(
        default=DEFAULT_STYLE_SCORE,
        ge=STYLE_SCORE_MIN,
        le=STYLE_SCORE_MAX,
        description="Bold/statement style preference 0-100",
    )


class PreferenceBase(BaseModel):
    # Color preferences
    color_favorites: list[str] = Field(default_factory=list, description="Favorite colors")
    color_avoid: list[str] = Field(default_factory=list, description="Colors to avoid")

    # Style preferences
    style_profile: StyleProfile = Field(default_factory=StyleProfile)

    # Occasion settings
    default_occasion: str = Field(
        default=DEFAULT_OCCASION, description="Default occasion for recommendations"
    )

    # Temperature/comfort
    temperature_unit: str = Field(
        default=DEFAULT_TEMPERATURE_UNIT,
        pattern="^(celsius|fahrenheit)$",
        description="Preferred temperature display unit",
    )
    temperature_sensitivity: str = Field(
        default=DEFAULT_TEMPERATURE_SENSITIVITY,
        pattern="^(low|normal|high)$",
        description="Temperature sensitivity level",
    )
    cold_threshold: int = Field(
        default=DEFAULT_COLD_THRESHOLD,
        ge=COLD_THRESHOLD_MIN,
        le=COLD_THRESHOLD_MAX,
        description="Temperature (C) considered cold",
    )
    hot_threshold: int = Field(
        default=DEFAULT_HOT_THRESHOLD,
        ge=HOT_THRESHOLD_MIN,
        le=HOT_THRESHOLD_MAX,
        description="Temperature (C) considered hot",
    )
    layering_preference: str = Field(
        default=DEFAULT_LAYERING_PREFERENCE,
        pattern="^(minimal|moderate|heavy)$",
        description="Layering preference",
    )

    # Recommendation settings
    avoid_repeat_days: int = Field(
        default=DEFAULT_AVOID_REPEAT_DAYS,
        ge=AVOID_REPEAT_DAYS_MIN,
        le=AVOID_REPEAT_DAYS_MAX,
        description="Days before repeating items",
    )
    prefer_underused_items: bool = Field(
        default=DEFAULT_PREFER_UNDERUSED_ITEMS, description="Prioritize less worn items"
    )
    variety_level: str = Field(
        default=DEFAULT_VARIETY_LEVEL,
        pattern="^(low|moderate|high)$",
        description="Outfit variety preference",
    )

    # AI Settings
    ai_endpoints: list[AIEndpoint] = Field(
        default_factory=list,
        description="AI endpoints in priority order (first available is used)",
    )


class PreferenceCreate(PreferenceBase):
    pass


class PreferenceUpdate(BaseModel):
    color_favorites: ColorList | None = None
    color_avoid: ColorList | None = None
    style_profile: StyleProfile | None = None
    default_occasion: Occasion | None = None
    temperature_unit: str | None = Field(default=None, pattern="^(celsius|fahrenheit)$")
    temperature_sensitivity: str | None = Field(default=None, pattern="^(low|normal|high)$")
    cold_threshold: int | None = Field(default=None, ge=COLD_THRESHOLD_MIN, le=COLD_THRESHOLD_MAX)
    hot_threshold: int | None = Field(default=None, ge=HOT_THRESHOLD_MIN, le=HOT_THRESHOLD_MAX)
    layering_preference: str | None = Field(default=None, pattern="^(minimal|moderate|heavy)$")
    avoid_repeat_days: int | None = Field(
        default=None, ge=AVOID_REPEAT_DAYS_MIN, le=AVOID_REPEAT_DAYS_MAX
    )
    prefer_underused_items: bool | None = None
    variety_level: str | None = Field(default=None, pattern="^(low|moderate|high)$")
    ai_endpoints: list[AIEndpoint] | None = None


class PreferenceResponse(PreferenceBase):
    class Config:
        from_attributes = True
