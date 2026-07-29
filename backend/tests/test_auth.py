import pytest
from httpx import AsyncClient

from app.api.auth import create_access_token
from app.utils.auth import decode_token


class TestJWTToken:
    """Tests for JWT token creation and validation."""

    def test_create_access_token(self):
        """Test that access token is created successfully."""
        token = create_access_token("test-user-id")
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        """Test that valid token is decoded correctly."""
        external_id = "test-user-id"
        token = create_access_token(external_id)
        payload = decode_token(token)
        assert payload.sub == external_id

    def test_decode_expired_token(self):
        """Test that expired token raises error."""
        from datetime import timedelta

        from fastapi import HTTPException

        # Create token that expired 1 hour ago
        token = create_access_token("test-user", expires_delta=timedelta(hours=-1))

        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401


class TestAuthConfig:
    @pytest.mark.asyncio
    async def test_get_auth_config(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/config")
        assert response.status_code == 200
        data = response.json()
        assert "oidc" in data
        assert "dev_mode" in data
        assert isinstance(data["oidc"]["enabled"], bool)

    @pytest.mark.asyncio
    async def test_auth_config_dev_mode(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/config")
        data = response.json()
        assert data["dev_mode"] is True
        assert data["oidc"]["enabled"] is False


class TestAuthSync:
    """Tests for auth sync endpoint."""

    @pytest.mark.asyncio
    async def test_sync_new_user(self, client: AsyncClient):
        """Test syncing a new user creates the user."""
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "new-user-123",
                "email": "newuser@example.com",
                "display_name": "New User",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["display_name"] == "New User"
        assert "access_token" in data
        assert data["is_new_user"] is True

    @pytest.mark.asyncio
    async def test_sync_existing_user(self, client: AsyncClient, test_user):
        """Test syncing an existing user returns existing data."""
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": test_user.external_id,
                "email": test_user.email,
                "display_name": "Updated Name",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["is_new_user"] is False

    @pytest.mark.asyncio
    async def test_sync_missing_required_fields(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "test-123",
                # display_name still required; email is now optional
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_sync_null_email_dev_mode_returns_400(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "test-123",
                "email": None,
                "display_name": "Test User",
            },
        )
        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_sync_omitted_email_dev_mode_returns_400(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/sync",
            json={
                "external_id": "test-123",
                "display_name": "Test User",
            },
        )
        assert response.status_code == 400
        assert "email" in response.json()["detail"].lower()


class TestMobileCallback:
    @pytest.mark.asyncio
    async def test_mobile_callback_redirects_with_params(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/mobile-callback",
            params={"code": "test-auth-code", "state": "test-state"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("wardrowbe://auth/callback?")
        assert "code=test-auth-code" in location
        assert "state=test-state" in location

    @pytest.mark.asyncio
    async def test_mobile_callback_redirects_without_params(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/mobile-callback",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "wardrowbe://auth/callback"

    @pytest.mark.asyncio
    async def test_mobile_callback_preserves_error_params(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/mobile-callback",
            params={"error": "access_denied", "error_description": "User cancelled"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=access_denied" in location
        assert "error_description=User+cancelled" in location

    @pytest.mark.asyncio
    async def test_mobile_callback_only_redirects_to_app_scheme(self, client: AsyncClient):
        response = await client.get(
            "/api/v1/auth/mobile-callback",
            params={"code": "x", "redirect": "https://evil.com"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("wardrowbe://")
        assert not location.startswith("https://evil.com")


class TestProtectedRoutes:
    """Tests for authentication requirement on protected routes."""

    @pytest.mark.asyncio
    async def test_unauthenticated_request_fails(self, client: AsyncClient):
        """Test that unauthenticated requests to protected routes fail."""
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_fails(self, client: AsyncClient):
        """Test that invalid token is rejected."""
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_succeeds(self, client: AsyncClient, test_user, auth_headers):
        """Test that valid token allows access to protected routes."""
        response = await client.get("/api/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
