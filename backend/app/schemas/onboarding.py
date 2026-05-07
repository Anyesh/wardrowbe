from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.preference import PreferenceResponse


class OnboardingStepState(BaseModel):
    step_key: str
    status: Literal["pending", "completed", "skipped"]


class OnboardingStateResponse(BaseModel):
    is_blocking: bool
    current_version: str
    current_step: str | None
    active_steps: list[OnboardingStepState]
    completed_steps: list[OnboardingStepState]


class StyleQuizQuestion(BaseModel):
    id: str
    title: str
    description: str | None = None
    type: Literal["single", "multi"]
    required: bool = True
    options: list[str]


class StyleQuizDefinitionResponse(BaseModel):
    step_key: Literal["style_quiz"] = "style_quiz"
    quiz_version: str = "v1"
    questions: list[StyleQuizQuestion]


class StyleQuizAnswers(BaseModel):
    primary_occasion: Literal["casual", "office", "formal", "date", "sporty", "outdoor"]
    style_focus: Literal["casual", "formal", "sporty", "minimalist", "bold"]
    color_palette: Literal["neutral", "low_saturation", "bright"]
    avoid_colors: list[str] = Field(default_factory=list)
    temperature_feel: Literal["cold", "normal", "hot"]
    variety: Literal["low", "moderate", "high"]


class StyleQuizSubmitRequest(BaseModel):
    quiz_version: str = "v1"
    answers: StyleQuizAnswers


class StyleQuizSubmitResponse(BaseModel):
    updated_preferences: PreferenceResponse
    style_insight: str
    next_step: str | None = None
