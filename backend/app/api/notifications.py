from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.notification import Notification, NotificationSettings
from app.models.schedule import Schedule
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

router = APIRouter()


# ============= Timezone Helpers =============


def local_time_to_utc(local_time_str: str, day_of_week: int, user_tz: ZoneInfo) -> tuple[time, int]:
    hours, minutes = map(int, local_time_str.split(":"))

    # Use a reference date that falls on the given day_of_week
    # Jan 5, 2026 is a Monday (day_of_week=0)
    reference_monday = datetime(2026, 1, 5, tzinfo=ZoneInfo("UTC"))
    reference_date = reference_monday + timedelta(days=day_of_week)

    # Create datetime in user's timezone
    local_dt = reference_date.replace(
        hour=hours, minute=minutes, second=0, microsecond=0, tzinfo=user_tz
    )

    # Convert to UTC
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

    return utc_dt.time(), utc_dt.weekday()


def utc_time_to_local(utc_time: time, utc_day_of_week: int, user_tz: ZoneInfo) -> tuple[str, int]:
    # Use same reference date approach
    reference_monday = datetime(2026, 1, 5, tzinfo=ZoneInfo("UTC"))
    reference_date = reference_monday + timedelta(days=utc_day_of_week)

    # Create datetime in UTC
    utc_dt = reference_date.replace(
        hour=utc_time.hour, minute=utc_time.minute, second=0, microsecond=0, tzinfo=ZoneInfo("UTC")
    )

    # Convert to user's timezone
    local_dt = utc_dt.astimezone(user_tz)

    return local_dt.strftime("%H:%M"), local_dt.weekday()


def _schedule_to_local_response(schedule: Schedule, user_tz: ZoneInfo) -> dict:
    local_time_str, local_day = utc_time_to_local(
        schedule.notification_time, schedule.day_of_week, user_tz
    )
    return {
        "id": schedule.id,
        "user_id": schedule.user_id,
        "day_of_week": local_day,  # Return local day
        "notification_time": local_time_str,  # Return local time
        "occasion": schedule.occasion,
        "enabled": schedule.enabled,
        "notify_day_before": schedule.notify_day_before,
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
    }


# ============= Defaults =============


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
    # Get user's timezone
    try:
        user_tz = ZoneInfo(current_user.timezone or "UTC")
    except Exception:
        user_tz = ZoneInfo("UTC")

    result = await db.execute(select(Schedule).where(Schedule.user_id == current_user.id))
    schedules = list(result.scalars().all())

    # Convert to local time and sort by local day
    local_schedules = [_schedule_to_local_response(s, user_tz) for s in schedules]
    local_schedules.sort(key=lambda x: x["day_of_week"])

    return local_schedules


@router.post("/schedules", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    data: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get user's timezone
    try:
        user_tz = ZoneInfo(current_user.timezone or "UTC")
    except Exception:
        user_tz = ZoneInfo("UTC")

    # Convert local time to UTC (day might shift!)
    utc_time, utc_day = local_time_to_utc(data.notification_time, data.day_of_week, user_tz)

    # Prevent exact duplicate schedules
    existing = await db.execute(
        select(Schedule).where(
            and_(
                Schedule.user_id == current_user.id,
                Schedule.day_of_week == utc_day,
                Schedule.notification_time == utc_time,
                Schedule.occasion == data.occasion,
                Schedule.notify_day_before == data.notify_day_before,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An identical schedule already exists")

    schedule = Schedule(
        user_id=current_user.id,
        day_of_week=utc_day,  # Store UTC day
        notification_time=utc_time,  # Store UTC time
        occasion=data.occasion,
        enabled=data.enabled,
        notify_day_before=data.notify_day_before,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    # Return with local time (handled by response conversion)
    return _schedule_to_local_response(schedule, user_tz)


@router.get("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get user's timezone
    try:
        user_tz = ZoneInfo(current_user.timezone or "UTC")
    except Exception:
        user_tz = ZoneInfo("UTC")

    result = await db.execute(
        select(Schedule).where(
            and_(Schedule.id == schedule_id, Schedule.user_id == current_user.id)
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return _schedule_to_local_response(schedule, user_tz)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: UUID,
    data: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get user's timezone
    try:
        user_tz = ZoneInfo(current_user.timezone or "UTC")
    except Exception:
        user_tz = ZoneInfo("UTC")

    result = await db.execute(
        select(Schedule).where(
            and_(Schedule.id == schedule_id, Schedule.user_id == current_user.id)
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if data.notification_time is not None:
        # Get current local day to use for conversion
        _, current_local_day = utc_time_to_local(
            schedule.notification_time, schedule.day_of_week, user_tz
        )
        # Convert new local time to UTC
        utc_time, utc_day = local_time_to_utc(data.notification_time, current_local_day, user_tz)
        schedule.notification_time = utc_time
        schedule.day_of_week = utc_day

    if data.occasion is not None:
        schedule.occasion = data.occasion
    if data.enabled is not None:
        schedule.enabled = data.enabled
    if data.notify_day_before is not None:
        schedule.notify_day_before = data.notify_day_before

    await db.commit()
    await db.refresh(schedule)

    return _schedule_to_local_response(schedule, user_tz)


@router.delete("/schedules/{schedule_id}", response_model=MessageResponse)
async def delete_schedule(
    schedule_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Schedule).where(
            and_(Schedule.id == schedule_id, Schedule.user_id == current_user.id)
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    await db.delete(schedule)
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
