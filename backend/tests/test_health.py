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
@pytest.mark.parametrize(
    "ui_switch, internal, expected",
    [(None, True, True), (None, False, False), (True, False, True), (False, True, False)],
)
async def test_features_report_effective_ai_ui(
    client: AsyncClient, monkeypatch, ui_switch, internal, expected
):
    monkeypatch.setattr(get_settings(), "ai_ui_enabled", ui_switch)
    monkeypatch.setattr(get_settings(), "ai_internal_enabled", internal)
    response = await client.get("/api/v1/health/features")
    assert response.status_code == 200
    assert response.json()["ai_ui_enabled"] is expected
