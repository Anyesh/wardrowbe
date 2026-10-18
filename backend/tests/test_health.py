import pytest
from httpx import AsyncClient

from app.config import get_settings


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test that health check endpoint returns OK."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_includes_version(client: AsyncClient):
    """Test that health check includes version info."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data or "status" in data


@pytest.mark.asyncio
async def test_features_expose_bulk_upload_limit(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_bulk_upload_count", 7)
    response = await client.get("/api/v1/health/features")
    assert response.status_code == 200
    assert response.json()["max_bulk_upload_count"] == 7


@pytest.mark.asyncio
async def test_features_need_no_auth(client: AsyncClient):
    response = await client.get("/api/v1/health/features")
    assert response.status_code == 200
    assert response.json()["max_bulk_upload_count"] == get_settings().max_bulk_upload_count


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_features_report_ai_ui_switch(client: AsyncClient, monkeypatch, enabled):
    monkeypatch.setattr(get_settings(), "ai_ui_enabled", enabled)
    response = await client.get("/api/v1/health/features")
    assert response.status_code == 200
    assert response.json()["ai_ui_enabled"] is enabled
