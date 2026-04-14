import logging
from datetime import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.notification import Notification, NotificationSettings
from app.models.user import User
from app.schemas.notification import (
    EmailConfig,
    ExpoPushConfig,
    MattermostConfig,
    MessageResponse,
    NotificationResponse,
    NotificationSettingsCreate,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
    NtfyConfig,
    ScheduleCreate,
    ScheduleResponse,
    ScheduleUpdate,
    TestNotificationResponse,
)
from app.services.notification_service import NotificationService
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_local_time(time_str: str) -> time:
    hours, minutes = map(int, time_str.split(":"))
    return time(hours, minutes)


@router.get("/defaults/ntfy")
async def get_ntfy_defaults(
    current_user: User = Depends(get_current_user),
):
    settings = get_settings()
    has_token = bool(settings.ntfy_token)
    return {
        "server": settings.ntfy_server or "https://ntfy.sh",
        "has_token": has_token,
    }


# ============= Notification Settings =============


@router.get("/settings", response_model=list[NotificationSettingsResponse])
async def list_notification_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    settings = await service.get_user_settings(current_user.id)
    return settings


@router.post("/settings", response_model=NotificationSettingsResponse, status_code=201)
async def create_notification_setting(
    data: NotificationSettingsCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate channel-specific config
    try:
        if data.channel == "ntfy":
            NtfyConfig(**data.config)
        elif data.channel == "mattermost":
            MattermostConfig(**data.config)
        elif data.channel == "email":
            EmailConfig(**data.config)
        elif data.channel == "expo_push":
            from app.schemas.notification import ExpoPushConfig

            ExpoPushConfig(**data.config)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e.errors()[0]["msg"])) from None

    service = NotificationService(db)
    try:
        setting = await service.create_setting(
            user_id=current_user.id,
            channel=data.channel,
            enabled=data.enabled,
            priority=data.priority,
            config=data.config,
        )
        await db.commit()
        return setting
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/settings/{setting_id}", response_model=NotificationSettingsResponse)
async def get_notification_setting(
    setting_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    setting = await service.get_setting_by_id(setting_id, current_user.id)
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return setting


@router.patch("/settings/{setting_id}", response_model=NotificationSettingsResponse)
async def update_notification_setting(
    setting_id: UUID,
    data: NotificationSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)

    # If config is being updated, validate it against the channel type
    if data.config is not None:
        existing = await service.get_setting_by_id(setting_id, current_user.id)
        if not existing:
            raise HTTPException(status_code=404, detail="Setting not found")

        # Validate channel-specific config
        try:
            if existing.channel == "ntfy":
                NtfyConfig(**data.config)
            elif existing.channel == "mattermost":
                MattermostConfig(**data.config)
            elif existing.channel == "email":
                EmailConfig(**data.config)
            elif existing.channel == "expo_push":
                ExpoPushConfig(**data.config)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e.errors()[0]["msg"])) from None

    setting = await service.update_setting(
        setting_id=setting_id,
        user_id=current_user.id,
        enabled=data.enabled,
        priority=data.priority,
        config=data.config,
    )
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    await db.commit()
    return setting


@router.delete("/settings/{setting_id}", response_model=MessageResponse)
async def delete_notification_setting(
    setting_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    success = await service.delete_setting(setting_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Setting not found")
    await db.commit()
    return MessageResponse(message="Notification setting deleted")


@router.post("/settings/{setting_id}/test", response_model=TestNotificationResponse)
async def test_notification_setting(
    setting_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    success, message = await service.test_setting(setting_id, current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return TestNotificationResponse(success=True, message=message)


# ============= Push Token Registration =============


class PushTokenRequest(BaseModel):
    push_token: str


@router.post("/push-token", response_model=NotificationSettingsResponse)
async def register_push_token(
    data: PushTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        ExpoPushConfig(push_token=data.push_token)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid push token format") from None

    # Check if expo_push channel already exists
    existing = await db.execute(
        select(NotificationSettings).where(
            and_(
                NotificationSettings.user_id == current_user.id,
                NotificationSettings.channel == "expo_push",
            )
        )
    )
    setting = existing.scalar_one_or_none()

    if setting:
        setting.config = {"push_token": data.push_token}
        setting.enabled = True
    else:
        setting = NotificationSettings(
            user_id=current_user.id,
            channel="expo_push",
            enabled=True,
            priority=0,  # Highest priority - push notifications preferred
            config={"push_token": data.push_token},
        )
        db.add(setting)

    await db.commit()
    await db.refresh(setting)
    return setting


# ============= Schedules =============


@router.get("/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    schedules = await service.get_user_schedules(current_user.id)
    schedules.sort(key=lambda s: s.day_of_week)
    return schedules


@router.post("/schedules", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    data: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    try:
        schedule = await service.create_schedule(
            user_id=current_user.id,
            day_of_week=data.day_of_week,
            notification_time=_parse_local_time(data.notification_time),
            occasion=data.occasion,
            enabled=data.enabled,
            notify_day_before=data.notify_day_before,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e),
        ) from None

    await db.commit()
    return schedule


@router.get("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    schedule = await service.get_schedule_by_id(schedule_id, current_user.id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: UUID,
    data: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    patch = data.model_dump(exclude_unset=True)
    raw_notification_time = patch.get("notification_time")
    schedule = await service.update_schedule(
        schedule_id=schedule_id,
        user_id=current_user.id,
        day_of_week=patch.get("day_of_week"),
        notification_time=(
            _parse_local_time(raw_notification_time) if raw_notification_time is not None else None
        ),
        occasion=patch.get("occasion"),
        enabled=patch.get("enabled"),
        notify_day_before=patch.get("notify_day_before"),
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.commit()
    return schedule


@router.delete("/schedules/{schedule_id}", response_model=MessageResponse)
async def delete_schedule(
    schedule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    success = await service.delete_schedule(schedule_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.commit()
    return MessageResponse(message="Schedule deleted")


# ============= Notification History =============


@router.get("/history", response_model=list[NotificationResponse])
async def list_notification_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())
