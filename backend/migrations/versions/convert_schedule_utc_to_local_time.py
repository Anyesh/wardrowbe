"""Convert schedule notification_time from UTC back to user's local time.

Schedule times were stored as UTC (converted from local using a fixed Jan 5
reference date). This broke DST because the offset was frozen at winter values.
This migration reverses the conversion so notification_time and day_of_week
store the user's intended LOCAL time. The worker now compares against the
user's local clock at trigger time.

Revision ID: e1f2g3h4i5j6
Revises: 7a3b5c8d9e0f
Create Date: 2026-04-12
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2g3h4i5j6"
down_revision: str | None = "7a3b5c8d9e0f"
branch_labels: str | None = None
depends_on: str | None = None

REFERENCE_MONDAY = datetime(2026, 1, 5, tzinfo=ZoneInfo("UTC"))


def upgrade() -> None:
    conn = op.get_bind()

    rows = conn.execute(
        sa.text("""
            SELECT s.id, s.notification_time, s.day_of_week, u.timezone
            FROM schedules s
            JOIN users u ON s.user_id = u.id
        """)
    ).fetchall()

    for row in rows:
        schedule_id, utc_time, utc_day, tz_name = row
        try:
            user_tz = ZoneInfo(tz_name or "UTC")
        except (KeyError, ValueError):
            user_tz = ZoneInfo("UTC")

        ref_date = REFERENCE_MONDAY + timedelta(days=utc_day)
        utc_dt = ref_date.replace(
            hour=utc_time.hour,
            minute=utc_time.minute,
            second=0,
            microsecond=0,
            tzinfo=ZoneInfo("UTC"),
        )
        local_dt = utc_dt.astimezone(user_tz)

        conn.execute(
            sa.text("""
                UPDATE schedules
                SET notification_time = :local_time, day_of_week = :local_day
                WHERE id = :sid
            """),
            {
                "local_time": local_dt.time(),
                "local_day": local_dt.weekday(),
                "sid": schedule_id,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()

    rows = conn.execute(
        sa.text("""
            SELECT s.id, s.notification_time, s.day_of_week, u.timezone
            FROM schedules s
            JOIN users u ON s.user_id = u.id
        """)
    ).fetchall()

    for row in rows:
        schedule_id, local_time, local_day, tz_name = row
        try:
            user_tz = ZoneInfo(tz_name or "UTC")
        except (KeyError, ValueError):
            user_tz = ZoneInfo("UTC")

        ref_date = REFERENCE_MONDAY + timedelta(days=local_day)
        local_dt = ref_date.replace(
            hour=local_time.hour,
            minute=local_time.minute,
            second=0,
            microsecond=0,
            tzinfo=user_tz,
        )
        utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

        conn.execute(
            sa.text("""
                UPDATE schedules
                SET notification_time = :utc_time, day_of_week = :utc_day
                WHERE id = :sid
            """),
            {
                "utc_time": utc_dt.time(),
                "utc_day": utc_dt.weekday(),
                "sid": schedule_id,
            },
        )
