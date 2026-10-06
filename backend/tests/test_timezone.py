import logging
from datetime import UTC, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.models.user import User
from app.utils.timezone import (
    get_user_now,
    get_user_timezone,
    get_user_today,
    is_valid_timezone,
    resolve_timezone,
)


def _user(timezone: str | None) -> User:
    return User(email="tz@example.com", display_name="Tz", timezone=timezone)


class TestZoneinfoDataInImage:
    def test_named_zone_resolves_with_dst_rules(self):
        new_york = ZoneInfo("America/New_York")
        winter = datetime(2026, 1, 15, 12, tzinfo=UTC).astimezone(new_york)
        summer = datetime(2026, 7, 15, 12, tzinfo=UTC).astimezone(new_york)
        assert winter.utcoffset().total_seconds() == -5 * 3600
        assert summer.utcoffset().total_seconds() == -4 * 3600


class TestIsValidTimezone:
    @pytest.mark.parametrize("name", ["UTC", "America/New_York", "Asia/Kathmandu", "Etc/GMT+5"])
    def test_known_zones_are_valid(self, name):
        assert is_valid_timezone(name)

    @pytest.mark.parametrize(
        "name",
        [None, "", "Mars/Olympus_Mons", "utc", "America", "America/New_York ", "../etc/passwd"],
    )
    def test_unknown_or_malformed_zones_are_invalid(self, name):
        assert not is_valid_timezone(name)


class TestResolveTimezone:
    def test_known_zone_is_returned(self):
        assert resolve_timezone("Asia/Kolkata") == ZoneInfo("Asia/Kolkata")

    def test_missing_zone_is_utc_without_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="app.utils.timezone"):
            assert resolve_timezone(None) == ZoneInfo("UTC")
            assert resolve_timezone("") == ZoneInfo("UTC")
        assert caplog.records == []

    @pytest.mark.parametrize("name", ["Mars/Resolve_Once", "../etc/resolve-once"])
    def test_bad_zone_falls_back_to_utc_and_warns_once(self, caplog, name):
        with caplog.at_level(logging.WARNING, logger="app.utils.timezone"):
            assert resolve_timezone(name) == ZoneInfo("UTC")
            assert resolve_timezone(name) == ZoneInfo("UTC")
        assert [r.getMessage() for r in caplog.records] == [f"Unknown timezone {name!r}, using UTC"]


class TestUserClock:
    def test_bad_stored_zone_reads_as_utc(self):
        assert get_user_timezone(_user("Mars/User_Clock")) == ZoneInfo("UTC")

    @pytest.mark.parametrize(
        ("zone", "instant", "today", "clock"),
        [
            ("Asia/Tokyo", datetime(2026, 3, 8, 20, 30, tzinfo=UTC), "2026-03-09", "05:30"),
            ("Pacific/Tongatapu", datetime(2026, 10, 5, 10, 59, tzinfo=UTC), "2026-10-05", "23:59"),
            ("Pacific/Tongatapu", datetime(2026, 10, 5, 11, 0, tzinfo=UTC), "2026-10-06", "00:00"),
            ("Asia/Kathmandu", datetime(2026, 10, 5, 18, 14, tzinfo=UTC), "2026-10-05", "23:59"),
            ("Asia/Kathmandu", datetime(2026, 10, 5, 18, 15, tzinfo=UTC), "2026-10-06", "00:00"),
            ("America/New_York", datetime(2026, 3, 8, 4, 59, tzinfo=UTC), "2026-03-07", "23:59"),
            ("America/New_York", datetime(2026, 3, 8, 7, 0, tzinfo=UTC), "2026-03-08", "03:00"),
            ("America/New_York", datetime(2026, 11, 1, 5, 30, tzinfo=UTC), "2026-11-01", "01:30"),
            ("America/New_York", datetime(2026, 11, 1, 6, 30, tzinfo=UTC), "2026-11-01", "01:30"),
        ],
    )
    def test_today_and_now_follow_the_user_zone(self, zone, instant, today, clock):
        user = _user(zone)
        with patch("app.utils.timezone.datetime") as mock_datetime:
            mock_datetime.now.return_value = instant
            assert get_user_today(user).isoformat() == today
            assert get_user_now(user).strftime("%H:%M") == clock
