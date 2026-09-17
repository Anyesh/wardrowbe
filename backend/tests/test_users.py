import pytest
from httpx import AsyncClient


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
    async def test_update_user_location(self, client: AsyncClient, test_user, auth_headers):
        """Test updating user location."""
        response = await client.patch(
            "/api/v1/users/me",
            json={
                "location_lat": 40.7128,
                "location_lon": -74.0060,
                "location_name": "New York City",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["location_name"] == "New York City"
        # Check coordinates are stored (may be string or float depending on serialization)
        assert float(data["location_lat"]) == pytest.approx(40.7128, rel=1e-4)
        assert float(data["location_lon"]) == pytest.approx(-74.0060, rel=1e-4)

    @pytest.mark.asyncio
    async def test_update_user_rejects_unknown_field(
        self, client: AsyncClient, test_user, auth_headers
    ):
        """An unrecognized key (e.g. a client-side naming mismatch like
        timeZone instead of timezone) must 422, not silently no-op with a
        200 that leaves the field unchanged."""
        response = await client.patch(
            "/api/v1/users/me",
            json={"timeZone": "Europe/Amsterdam"},
            headers=auth_headers,
        )
        assert response.status_code == 422

        unchanged = await client.get("/api/v1/users/me", headers=auth_headers)
        assert unchanged.json()["timezone"] != "Europe/Amsterdam"


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
class TestBodyMeasurementHistory:
    @pytest.mark.asyncio
    async def test_measurement_update_exposes_time_aware_current_state(
        self, client: AsyncClient, test_user, auth_headers
    ):
        response = await client.patch(
            "/api/v1/users/me",
            json={"body_measurements": {"weight": 84.2, "chest": 106}},
            headers=auth_headers,
        )
        assert response.status_code == 200

        response = await client.get(
            "/api/v1/users/me/body-measurements", headers=auth_headers
        )
        assert response.status_code == 200
        current = response.json()["measurements"]
        assert current["weight"]["value"] == 84.2
        assert current["weight"]["unit"] == "kg"
        assert current["weight"]["source"] == "manual"
        assert current["weight"]["measured_at"] is not None
        assert current["chest"]["value"] == 106
        assert current["chest"]["unit"] == "cm"

    @pytest.mark.asyncio
    async def test_measurement_history_retains_previous_values_without_refreshing_unchanged_metric(
        self, client: AsyncClient, test_user, auth_headers
    ):
        headers = auth_headers
        first = {"body_measurements": {"weight": 84.2, "waist": 92}}
        assert (await client.patch("/api/v1/users/me", json=first, headers=headers)).status_code == 200

        second = {"body_measurements": {"weight": 84.2, "waist": 90}}
        assert (await client.patch("/api/v1/users/me", json=second, headers=headers)).status_code == 200

        response = await client.get(
            "/api/v1/users/me/body-measurements/history", headers=headers
        )
        assert response.status_code == 200
        history = response.json()["observations"]
        weight = [row for row in history if row["metric"] == "weight"]
        waist = [row for row in history if row["metric"] == "waist"]
        assert [row["value"] for row in weight] == [84.2]
        assert [row["value"] for row in waist] == [90.0, 92.0]

    @pytest.mark.asyncio
    async def test_legacy_snapshot_has_unknown_measurement_time(
        self, client: AsyncClient, test_user, auth_headers, db_session
    ):
        test_user.body_measurements = {"weight": 80, "shirt_size": "L"}
        await db_session.commit()

        response = await client.get(
            "/api/v1/users/me/body-measurements", headers=auth_headers
        )
        assert response.status_code == 200
        current = response.json()["measurements"]
        assert current["weight"] == {
            "value": 80.0,
            "unit": "kg",
            "measured_at": None,
            "source": "legacy_profile",
        }
        assert "shirt_size" not in current
