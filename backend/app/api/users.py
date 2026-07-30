from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.user_service import UserService
from app.utils.auth import get_current_user
from app.utils.locale import SUPPORTED_LOCALES, is_supported_locale

router = APIRouter(prefix="/users/me", tags=["Users"])


class OnboardingCompleteResponse(BaseModel):
    onboarding_completed: bool


class UserProfileResponse(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: str | None = None
    timezone: str
    locale: str
    location_lat: float | None = None
    location_lon: float | None = None
    location_name: str | None = None
    family_id: str | None = None
    role: str
    onboarding_completed: bool
    body_measurements: dict | None = None


class UserProfileUpdate(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    locale: str | None = None
    location_lat: Decimal | None = None
    location_lon: Decimal | None = None
    location_name: str | None = None
    body_measurements: dict | None = None


@router.get("", response_model=UserProfileResponse)
async def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserProfileResponse:
    return _user_response(current_user)


@router.patch("", response_model=UserProfileResponse)
async def update_profile(
    data: UserProfileUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserProfileResponse:
    update_data = data.model_dump(exclude_unset=True)

    # update_data is applied with a blanket setattr below, so an unsupported locale
    # must be rejected here to prevent it reaching the column.
    if "locale" in update_data and not is_supported_locale(update_data["locale"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"locale must be one of: {', '.join(SUPPORTED_LOCALES)}",
        )

    if "body_measurements" in update_data and update_data["body_measurements"] is not None:
        numeric_keys = {"chest", "waist", "hips", "inseam", "height", "weight"}
        for key, value in update_data["body_measurements"].items():
            if key in numeric_keys and isinstance(value, (int, float)) and value <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{key} must be a positive number",
                )

    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.flush()
    await db.refresh(current_user)
    await db.commit()

    return _user_response(current_user)


def _user_response(user: User) -> UserProfileResponse:
    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        timezone=user.timezone,
        locale=user.locale,
        location_lat=float(user.location_lat) if user.location_lat else None,
        location_lon=float(user.location_lon) if user.location_lon else None,
        location_name=user.location_name,
        family_id=str(user.family_id) if user.family_id else None,
        role=user.role,
        onboarding_completed=user.onboarding_completed,
        body_measurements=user.body_measurements,
    )


@router.post("/onboarding/complete", response_model=OnboardingCompleteResponse)
async def complete_onboarding(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OnboardingCompleteResponse:
    user_service = UserService(db)
    await user_service.complete_onboarding(current_user)
    await db.commit()

    return OnboardingCompleteResponse(onboarding_completed=True)
