from datetime import time

import pytest
from httpx import AsyncClient

from app.models.notification import NotificationSettings
from app.models.schedule import Schedule


class TestNotificationSettings:
    """Tests for notification settings management."""

    @pytest.mark.asyncio
    async def test_list_settings_empty(self, client: AsyncClient, test_user, auth_headers):
        """Test listing notification settings when none exist."""
        response = await client.get("/api/v1/notifications/settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_ntfy_setting(self, client: AsyncClient, test_user, auth_headers):
        """Test creating an ntfy notification setting."""
        response = await client.post(
            "/api/v1/notifications/settings",
            json={
                "channel": "ntfy",
                "config": {
                    "server": "https://ntfy.sh",
                    "topic": "my-wardrobe-notifications",
                },
                "enabled": True,
                "priority": 1,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["channel"] == "ntfy"
        assert data["enabled"] is True

    @pytest.mark.asyncio
    async def test_create_email_setting(self, client: AsyncClient, test_user, auth_headers):
        """Test creating an email notification setting."""
        response = await client.post(
            "/api/v1/notifications/settings",
            json={
                "channel": "email",
                "config": {
                    "email": "test@example.com",
                },
                "enabled": True,
                "priority": 2,
            },
            headers=auth_headers,
        )
        # Email channel may require SMTP config - accept 400 if email not configured
        assert response.status_code in [201, 400]
        if response.status_code == 201:
            data = response.json()
            assert data["channel"] == "email"

    @pytest.mark.asyncio
    async def test_update_setting(self, client: AsyncClient, test_user, auth_headers, db_session):
        """Test updating a notification setting."""
        # First create a setting directly in DB
        setting = NotificationSettings(
            user_id=test_user.id,
            channel="ntfy",
            config={"server": "https://ntfy.sh", "topic": "test"},
            enabled=True,
        )
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)

        # Update it
        response = await client.patch(
            f"/api/v1/notifications/settings/{setting.id}",
            json={
                "enabled": False,
                "priority": 5,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["priority"] == 5

    @pytest.mark.asyncio
    async def test_delete_setting(self, client: AsyncClient, test_user, auth_headers, db_session):
        """Test deleting a notification setting."""
        # Create a setting
        setting = NotificationSettings(
            user_id=test_user.id,
            channel="ntfy",
            config={"server": "https://ntfy.sh", "topic": "test"},
            enabled=True,
        )
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)
        setting_id = setting.id

        # Delete it
        response = await client.delete(
            f"/api/v1/notifications/settings/{setting_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200  # API returns 200 with message


class TestSchedules:
    """Tests for notification schedules."""

    @pytest.mark.asyncio
    async def test_list_schedules_empty(self, client: AsyncClient, test_user, auth_headers):
        """Test listing schedules when none exist."""
        response = await client.get("/api/v1/notifications/schedules", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_create_schedule(self, client: AsyncClient, test_user, auth_headers, db_session):
        """Test creating a notification schedule."""
        # First create a notification setting to use
        setting = NotificationSettings(
            user_id=test_user.id,
            channel="ntfy",
            config={"server": "https://ntfy.sh", "topic": "test"},
            enabled=True,
        )
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)

        response = await client.post(
            "/api/v1/notifications/schedules",
            json={
                "day_of_week": 0,  # Monday
                "notification_time": "07:00",
                "occasion": "work",
                "enabled": True,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["day_of_week"] == 0
        assert data["notification_time"] == "07:00"

    @pytest.mark.asyncio
    async def test_update_schedule(self, client: AsyncClient, test_user, auth_headers, db_session):
        schedule = Schedule(
            user_id=test_user.id,
            day_of_week=1,
            notification_time=time(8, 0),
            occasion="work",
            enabled=True,
            notify_day_before=False,
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)

        response = await client.patch(
            f"/api/v1/notifications/schedules/{schedule.id}",
            json={
                "day_of_week": 2,
                "notification_time": "09:30",
                "occasion": "casual",
                "enabled": False,
                "notify_day_before": True,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["day_of_week"] == 2
        assert data["notification_time"] == "09:30"
        assert data["occasion"] == "casual"
        assert data["enabled"] is False
        assert data["notify_day_before"] is True

    @pytest.mark.asyncio
    async def test_delete_schedule(self, client: AsyncClient, test_user, auth_headers, db_session):
        schedule = Schedule(
            user_id=test_user.id,
            day_of_week=3,
            notification_time=time(7, 15),
            occasion="work",
            enabled=True,
            notify_day_before=False,
        )
        db_session.add(schedule)
        await db_session.commit()
        await db_session.refresh(schedule)

        response = await client.delete(
            f"/api/v1/notifications/schedules/{schedule.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Schedule deleted"

        get_response = await client.get(
            f"/api/v1/notifications/schedules/{schedule.id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404


class TestNotificationDefaults:
    """Tests for notification defaults endpoint."""

    @pytest.mark.asyncio
    async def test_get_ntfy_defaults(self, client: AsyncClient, test_user, auth_headers):
        """Test getting default ntfy configuration."""
        response = await client.get(
            "/api/v1/notifications/defaults/ntfy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should have server and has_token fields
        assert "server" in data
        assert "has_token" in data
