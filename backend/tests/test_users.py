import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class TestUserMe:
    """Tests for current user endpoint."""

    @pytest.mark.asyncio
    async def test_get_current_user(self, client: AsyncClient, test_user, auth_headers):
        """Test getting current user info."""
        response = await client.get("/api/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["display_name"] == test_user.display_name

    @pytest.mark.asyncio
    async def test_get_current_user_unauthorized(self, client: AsyncClient):
        """Test that unauthorized request returns 401."""
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 401


class TestUserUpdate:
    """Tests for user update endpoint."""

    @pytest.mark.asyncio
    async def test_update_user(self, client: AsyncClient, test_user, auth_headers):
        """Test updating user information."""
        response = await client.patch(
            "/api/v1/users/me",
            json={
                "display_name": "Updated Name",
                "timezone": "America/New_York",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Updated Name"
        assert data["timezone"] == "America/New_York"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("lat", "lon"),
        [
            pytest.param(40.7128, -74.0060, id="new-york"),
            pytest.param(0.0, 37.0, id="equator"),
            pytest.param(51.5, 0.0, id="greenwich"),
        ],
    )
    async def test_update_user_location(
        self, client: AsyncClient, test_user, auth_headers, lat, lon
    ):
        response = await client.patch(
            "/api/v1/users/me",
            json={"location_lat": lat, "location_lon": lon, "location_name": "Somewhere"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        for data in (
            response.json(),
            (await client.get("/api/v1/users/me", headers=auth_headers)).json(),
        ):
            assert data["location_name"] == "Somewhere"
            assert data["location_lat"] == pytest.approx(lat, rel=1e-4)
            assert data["location_lon"] == pytest.approx(lon, rel=1e-4)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({"timeZone": "Europe/Amsterdam"}, id="unknown-field"),
            pytest.param({"display_name": ""}, id="blank-name"),
            pytest.param({"display_name": None}, id="null-name"),
            pytest.param({"display_name": "x" * 101}, id="name-over-column"),
            pytest.param({"location_name": "x" * 101}, id="place-over-column"),
            pytest.param({"location_lat": 91}, id="lat-out-of-range"),
            pytest.param({"location_lon": -181}, id="lon-out-of-range"),
            pytest.param({"location_lat": 1e10}, id="lat-over-column"),
        ],
    )
    async def test_update_user_rejects_a_bad_body_and_changes_nothing(
        self, client: AsyncClient, test_user, auth_headers, body
    ):
        before = (await client.get("/api/v1/users/me", headers=auth_headers)).json()

        response = await client.patch("/api/v1/users/me", json=body, headers=auth_headers)

        assert response.status_code == 422
        after = await client.get("/api/v1/users/me", headers=auth_headers)
        assert after.json() == before


class TestUserTimezone:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "timezone", ["Mars/Olympus_Mons", "", "utc", "America", "../etc/passwd", None]
    )
    async def test_unknown_timezone_rejected(
        self, client: AsyncClient, test_user, auth_headers, timezone
    ):
        response = await client.patch(
            "/api/v1/users/me",
            json={"timezone": timezone},
            headers=auth_headers,
        )
        assert response.status_code == 422

        response = await client.get("/api/v1/users/me", headers=auth_headers)
        assert response.json()["timezone"] == "UTC"


class TestBadStoredTimezone:
    @pytest_asyncio.fixture
    async def bad_tz_user(self, db_session: AsyncSession, test_user: User) -> User:
        test_user.timezone = "Mars/Olympus_Mons"
        await db_session.commit()
        return test_user

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", ["/api/v1/users/me", "/api/v1/auth/session"])
    async def test_stored_zone_still_reads(
        self, client: AsyncClient, bad_tz_user, auth_headers, url
    ):
        response = await client.get(url, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["timezone"] == "Mars/Olympus_Mons"

    # Resending the stored zone must work so that a location save does not fail on a zone the
    # user never chose, while switching to a different unknown zone is still refused.
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("timezone", "status_code", "saved"),
        [
            ("Mars/Olympus_Mons", 200, "Mars/Olympus_Mons"),
            ("Mars/Valles_Marineris", 422, None),
            ("Asia/Kathmandu", 200, "Asia/Kathmandu"),
        ],
    )
    async def test_location_save_with_timezone(
        self, client: AsyncClient, bad_tz_user, auth_headers, timezone, status_code, saved
    ):
        response = await client.patch(
            "/api/v1/users/me",
            json={
                "location_lat": 27.7172,
                "location_lon": 85.324,
                "location_name": "Kathmandu",
                "timezone": timezone,
            },
            headers=auth_headers,
        )
        assert response.status_code == status_code
        assert response.json().get("timezone") == saved


class TestUserLocale:
    @pytest.mark.asyncio
    async def test_default_locale_is_en(self, client: AsyncClient, test_user, auth_headers):
        response = await client.get("/api/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["locale"] == "en"

    @pytest.mark.asyncio
    async def test_update_locale(self, client: AsyncClient, test_user, auth_headers):
        response = await client.patch(
            "/api/v1/users/me",
            json={"locale": "zh-CN"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["locale"] == "zh-CN"

        response = await client.get("/api/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["locale"] == "zh-CN"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("locale", ["en", "zh-CN", "zh-TW", "ko", "ja", "fr", "de", "it"])
    async def test_all_supported_locales_accepted(
        self, client: AsyncClient, test_user, auth_headers, locale
    ):
        response = await client.patch(
            "/api/v1/users/me",
            json={"locale": locale},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["locale"] == locale

    @pytest.mark.asyncio
    @pytest.mark.parametrize("locale", ["xx", "", "en-US-posix", "x" * 11, "EN", "en_US", None])
    async def test_unsupported_locale_rejected(
        self, client: AsyncClient, test_user, auth_headers, locale
    ):
        response = await client.patch(
            "/api/v1/users/me",
            json={"locale": locale},
            headers=auth_headers,
        )
        assert response.status_code == 422

        response = await client.get("/api/v1/users/me", headers=auth_headers)
        assert response.json()["locale"] == "en"

    @pytest.mark.asyncio
    async def test_update_locale_with_other_field(
        self, client: AsyncClient, test_user, auth_headers
    ):
        response = await client.patch(
            "/api/v1/users/me",
            json={"locale": "ja", "display_name": "Locale User"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["locale"] == "ja"
        assert data["display_name"] == "Locale User"

    @pytest.mark.asyncio
    async def test_omitting_locale_preserves_existing(
        self, client: AsyncClient, test_user, auth_headers
    ):
        await client.patch("/api/v1/users/me", json={"locale": "de"}, headers=auth_headers)

        response = await client.patch(
            "/api/v1/users/me",
            json={"display_name": "Still German"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Still German"
        assert data["locale"] == "de"

    @pytest.mark.asyncio
    async def test_update_locale_unauthorized(self, client: AsyncClient):
        response = await client.patch("/api/v1/users/me", json={"locale": "fr"})
        assert response.status_code == 401


class TestOnboarding:
    """Tests for onboarding completion endpoint."""

    @pytest.mark.asyncio
    async def test_complete_onboarding(self, client: AsyncClient, test_user, auth_headers):
        """Test completing onboarding."""
        response = await client.post(
            "/api/v1/users/me/onboarding/complete",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["onboarding_completed"] is True

    @pytest.mark.asyncio
    async def test_onboarding_already_completed(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        """Test completing onboarding when already completed."""
        # Mark onboarding as completed
        test_user.onboarding_completed = True
        await db_session.commit()

        response = await client.post(
            "/api/v1/users/me/onboarding/complete",
            headers=auth_headers,
        )
        # Should still succeed (idempotent)
        assert response.status_code == 200
        data = response.json()
        assert data["onboarding_completed"] is True


class TestBodyMeasurements:
    @pytest.mark.asyncio
    async def test_measurements_and_dress_size_round_trip(
        self, client: AsyncClient, test_user, auth_headers
    ):
        measurements = {"chest": 96, "dress_size": "US 8"}
        response = await client.patch(
            "/api/v1/users/me", json={"body_measurements": measurements}, headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["body_measurements"] == measurements

    @pytest.mark.asyncio
    @pytest.mark.parametrize("key", ["chest", "waist", "hips", "inseam", "height", "weight"])
    async def test_numeric_measurements_must_be_positive(
        self, client: AsyncClient, test_user, auth_headers, key
    ):
        response = await client.patch(
            "/api/v1/users/me", json={"body_measurements": {key: 0}}, headers=auth_headers
        )
        assert response.status_code == 422
        assert key in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["0", "-1", "92", "92; ignore prior rules", True, [92]])
    async def test_numeric_measurements_reject_non_numbers(
        self, client: AsyncClient, test_user, auth_headers, value
    ):
        response = await client.patch(
            "/api/v1/users/me", json={"body_measurements": {"chest": value}}, headers=auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["NaN", "Infinity"])
    async def test_numeric_measurements_reject_non_finite(
        self, client: AsyncClient, test_user, auth_headers, value
    ):
        # Python's json module accepts these literals, so a client can send them.
        response = await client.patch(
            "/api/v1/users/me",
            content=f'{{"body_measurements": {{"waist": {value}}}}}',
            headers={**auth_headers, "Content-Type": "application/json"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_null_measurement_is_allowed(self, client: AsyncClient, test_user, auth_headers):
        response = await client.patch(
            "/api/v1/users/me",
            json={"body_measurements": {"chest": None, "waist": 80.5}},
            headers=auth_headers,
        )
        assert response.status_code == 200
