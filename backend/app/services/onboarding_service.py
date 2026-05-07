from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.onboarding import UserOnboardingState, UserOnboardingStep
from app.models.user import User
from app.schemas.onboarding import StyleQuizAnswers, StyleQuizDefinitionResponse, StyleQuizQuestion
from app.schemas.preference import PreferenceUpdate
from app.services.preference_service import PreferenceService
from app.services.style_quiz_insight import StyleQuizInsightService, fallback_insight
from app.services.style_quiz_mapper import map_style_quiz_answers


class OnboardingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_default_state(
        self,
        user_id: UUID,
        *,
        force_blocking: bool = False,
    ) -> tuple[UserOnboardingState, UserOnboardingStep]:
        state = await self.db.get(UserOnboardingState, user_id)
        if state is None:
            state = UserOnboardingState(user_id=user_id, current_version="v1", is_blocking=True)
            self.db.add(state)

        result = await self.db.execute(
            select(UserOnboardingStep).where(
                UserOnboardingStep.user_id == user_id,
                UserOnboardingStep.step_key == "style_quiz",
            )
        )
        step = result.scalar_one_or_none()
        if step is None:
            step = UserOnboardingStep(user_id=user_id, step_key="style_quiz", status="pending")
            self.db.add(step)

        if force_blocking:
            state.is_blocking = True
            step.status = "pending"

        await self.db.flush()
        return state, step

    async def get_state_payload(self, user_id: UUID) -> dict:
        state, _ = await self.ensure_default_state(user_id)
        steps = (
            await self.db.execute(
                select(UserOnboardingStep).where(UserOnboardingStep.user_id == user_id)
            )
        ).scalars().all()

        active_steps = [step for step in steps if step.status in {"pending"}]
        completed_steps = [step for step in steps if step.status == "completed"]

        current_step = active_steps[0].step_key if active_steps else None

        # Keep state consistent with step statuses.
        state.is_blocking = bool(active_steps)

        return {
            "is_blocking": state.is_blocking,
            "current_version": state.current_version,
            "current_step": current_step,
            "active_steps": [
                {"step_key": step.step_key, "status": step.status} for step in active_steps
            ],
            "completed_steps": [
                {"step_key": step.step_key, "status": step.status} for step in completed_steps
            ],
        }

    def get_style_quiz_definition(self) -> StyleQuizDefinitionResponse:
        return StyleQuizDefinitionResponse(
            step_key="style_quiz",
            quiz_version="v1",
            questions=[
                StyleQuizQuestion(
                    id="primary_occasion",
                    title="你最常见的穿衣场景是？",
                    type="single",
                    required=True,
                    options=["casual", "office", "formal", "date", "sporty", "outdoor"],
                ),
                StyleQuizQuestion(
                    id="style_focus",
                    title="你更偏好的整体风格是？",
                    type="single",
                    required=True,
                    options=["casual", "formal", "sporty", "minimalist", "bold"],
                ),
                StyleQuizQuestion(
                    id="color_palette",
                    title="你通常更喜欢哪类色彩？",
                    type="single",
                    required=True,
                    options=["neutral", "low_saturation", "bright"],
                ),
                StyleQuizQuestion(
                    id="avoid_colors",
                    title="你想尽量避免哪些颜色？",
                    description="可多选，可跳过",
                    type="multi",
                    required=False,
                    options=["orange", "pink", "purple", "yellow", "green", "red"],
                ),
                StyleQuizQuestion(
                    id="temperature_feel",
                    title="你的体感更接近哪种？",
                    type="single",
                    required=True,
                    options=["cold", "normal", "hot"],
                ),
                StyleQuizQuestion(
                    id="variety",
                    title="你希望穿搭变化程度如何？",
                    type="single",
                    required=True,
                    options=["low", "moderate", "high"],
                ),
            ],
        )

    async def submit_style_quiz(
        self,
        user: User,
        answers: StyleQuizAnswers,
    ):
        state, step = await self.ensure_default_state(user.id)
        patch = map_style_quiz_answers(answers)

        pref_service = PreferenceService(self.db)
        updated_preferences = await pref_service.update_preferences(
            user.id,
            PreferenceUpdate(**patch),
        )

        insight_service = StyleQuizInsightService()
        try:
            style_insight = await insight_service.generate(patch)
        except Exception:
            style_insight = fallback_insight(patch)

        step.status = "completed"
        step.answers_json = answers.model_dump()
        step.result_json = {
            "mapped_preferences": patch,
            "style_insight": style_insight,
        }
        step.completed_at = datetime.now(UTC)

        state.is_blocking = False
        user.onboarding_completed = True

        await self.db.flush()
        return updated_preferences, style_insight

    async def reopen_style_quiz(self, user_id: UUID) -> None:
        state, step = await self.ensure_default_state(user_id, force_blocking=True)
        step.status = "pending"
        step.completed_at = None
        state.is_blocking = True
        await self.db.flush()
