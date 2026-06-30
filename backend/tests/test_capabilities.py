"""Tests for AI capability flags, the /capabilities endpoint, and the AI-disabled
guard. Covers the AI-off and AI-on paths and asserts defaults preserve current
behavior (internal AI on)."""

import pytest
from httpx import AsyncClient

from app.config import Settings
from app.services.ai_service import (
    AIDisabledError,
    AIService,
    get_ai_service,
    require_internal_ai,
)

# --- Flag resolution truth table (no DB) -----------------------------------


@pytest.mark.parametrize(
    "internal, vision, text, exp_vision, exp_text",
    [
        # Defaults: everything inherits the master, which defaults on.
        (True, None, None, True, True),
        # Master on, a single capability explicitly disabled.
        (True, False, None, False, True),
        (True, None, False, True, False),
        (True, False, False, False, False),
        # Master off forces both off, even with an explicit sub-switch on.
        (False, None, None, False, False),
        (False, True, None, False, False),
        (False, True, True, False, False),
        # Master on, both explicitly enabled.
        (True, True, True, True, True),
    ],
)
def test_effective_flag_resolution(internal, vision, text, exp_vision, exp_text):
    settings = Settings(
        ai_internal_enabled=internal,
        ai_vision_enabled=vision,
        ai_text_enabled=text,
    )
    assert settings.effective_ai_vision_enabled is exp_vision
    assert settings.effective_ai_text_enabled is exp_text
    assert settings.ai_enabled is (exp_vision or exp_text)


def test_defaults_keep_internal_ai_on():
    """Regression: an unconfigured Settings keeps internal AI fully on."""
    settings = Settings()
    assert settings.ai_internal_enabled is True
    assert settings.effective_ai_vision_enabled is True
    assert settings.effective_ai_text_enabled is True
    assert settings.ai_enabled is True


# --- AI-disabled guard ------------------------------------------------------


def test_get_ai_service_raises_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_internal_enabled=False),
    )
    with pytest.raises(AIDisabledError):
        get_ai_service()


def test_get_ai_service_constructs_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_internal_enabled=True),
    )
    monkeypatch.setattr("app.services.ai_service._ai_service", None)
    service = get_ai_service()
    assert isinstance(service, AIService)


# --- /capabilities endpoint -------------------------------------------------


@pytest.mark.asyncio
async def test_capabilities_default_on(client: AsyncClient):
    response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["ai"] == {"vision": True, "text": True}
    assert data["features"] == {
        "external_tagging": False,
        "external_suggestions": False,
        "external_pairings": False,
    }
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_capabilities_reports_disabled(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.api.health.get_settings",
        lambda: Settings(ai_internal_enabled=False),
    )
    response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    assert response.json()["ai"] == {"vision": False, "text": False}


@pytest.mark.asyncio
async def test_capabilities_reports_vision_only(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        "app.api.health.get_settings",
        lambda: Settings(ai_text_enabled=False),
    )
    response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    assert response.json()["ai"] == {"vision": True, "text": False}


@pytest.mark.asyncio
async def test_ai_health_reports_disabled(client: AsyncClient, monkeypatch):
    """With AI off, /health/ai degrades cleanly instead of probing endpoints."""
    monkeypatch.setattr(
        "app.api.health.get_settings",
        lambda: Settings(ai_internal_enabled=False),
    )
    response = await client.get("/api/v1/health/ai")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "disabled"
    assert data["endpoints"] == []


# --- require_internal_ai() guard (per-capability) ---------------------------


def test_require_internal_ai_text_raises_when_off(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_text_enabled=False),
    )
    with pytest.raises(AIDisabledError):
        require_internal_ai("text")


def test_require_internal_ai_vision_raises_when_off(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_vision_enabled=False),
    )
    with pytest.raises(AIDisabledError):
        require_internal_ai("vision")


def test_require_internal_ai_passes_when_on(monkeypatch):
    monkeypatch.setattr("app.services.ai_service.get_settings", lambda: Settings())
    # Neither call raises when internal AI is on.
    require_internal_ai("vision")
    require_internal_ai("text")


def test_require_internal_ai_capability_isolation(monkeypatch):
    """vision off + text on: the text guard passes, the vision guard raises."""
    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_vision_enabled=False),
    )
    require_internal_ai("text")
    with pytest.raises(AIDisabledError):
        require_internal_ai("vision")


# --- AIService.__init__ backstop --------------------------------------------


def test_aiservice_init_raises_when_fully_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_internal_enabled=False),
    )
    with pytest.raises(AIDisabledError):
        AIService()


def test_aiservice_init_constructs_when_enabled(monkeypatch):
    monkeypatch.setattr("app.services.ai_service.get_settings", lambda: Settings())
    assert AIService() is not None


# --- Worker: tagging no-op when vision disabled -----------------------------


@pytest.mark.asyncio
async def test_tag_item_image_skips_when_vision_disabled(monkeypatch):
    """Vision off: the task builds no client, calls no provider, and leaves the
    item ready (untagged) instead of marking it error."""
    from app.workers import tagging

    monkeypatch.setattr(tagging, "get_settings", lambda: Settings(ai_internal_enabled=False))

    def _boom(*args, **kwargs):
        raise AssertionError("AIService constructed while vision disabled")

    monkeypatch.setattr(tagging, "AIService", _boom)

    marked: dict[str, str] = {}

    async def _skip(ctx, item_id):
        marked["id"] = item_id

    monkeypatch.setattr(tagging, "mark_item_tagging_skipped", _skip)

    item_id = "11111111-1111-1111-1111-111111111111"
    result = await tagging.tag_item_image({}, item_id, "/unused/path.jpg")
    assert result["status"] == "skipped"
    assert marked["id"] == item_id


@pytest.mark.asyncio
async def test_tag_item_image_runs_ai_when_enabled(monkeypatch):
    """Regression: vision on still reaches the AI path (constructs a client)."""
    from app.workers import tagging

    monkeypatch.setattr(tagging, "get_settings", lambda: Settings())

    constructed = {"called": False}

    class _StubAI:
        def __init__(self, *args, **kwargs):
            constructed["called"] = True

        async def analyze_image(self, path):  # pragma: no cover - not reached
            raise RuntimeError("stop after construction")

    monkeypatch.setattr(tagging, "AIService", _StubAI)

    async def _err(ctx, item_id, msg):
        return None

    monkeypatch.setattr(tagging, "update_item_status_to_error", _err)

    # Missing image short-circuits before construction, so point at this file.
    result = await tagging.tag_item_image({}, "1", __file__)
    # It did NOT take the "skipped" branch — it proceeded into the AI path.
    assert result["status"] != "skipped"


# --- Worker startup: no AI client when fully disabled -----------------------


@pytest.mark.asyncio
async def test_worker_startup_skips_ai_when_disabled(monkeypatch):
    from app.workers import worker

    monkeypatch.setattr(worker, "get_settings", lambda: Settings(ai_internal_enabled=False))

    def _boom(*args, **kwargs):
        raise AssertionError("AIService constructed at startup while disabled")

    monkeypatch.setattr(worker, "AIService", _boom)

    async def _noop(ctx):
        return None

    monkeypatch.setattr(worker, "init_db", _noop)
    monkeypatch.setattr(worker, "recover_stale_processing_items", _noop)

    ctx: dict = {}
    await worker.startup(ctx)
    assert ctx["ai_service"] is None


# --- Endpoints degrade to a clean 503 (not 500) when text is off ------------


@pytest.mark.asyncio
async def test_suggest_returns_503_when_text_disabled(client, auth_headers, monkeypatch):
    async def _raise(self, *args, **kwargs):
        raise AIDisabledError("text disabled")

    monkeypatch.setattr(
        "app.services.recommendation_service.RecommendationService.generate_recommendation",
        _raise,
    )
    resp = await client.post(
        "/api/v1/outfits/suggest", json={"occasion": "casual"}, headers=auth_headers
    )
    assert resp.status_code == 503
    assert "external agent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_pairings_returns_503_when_text_disabled(client, auth_headers, monkeypatch):
    async def _raise(self, *args, **kwargs):
        raise AIDisabledError("text disabled")

    monkeypatch.setattr(
        "app.services.pairing_service.PairingService.generate_pairings",
        _raise,
    )
    item_id = "22222222-2222-2222-2222-222222222222"
    resp = await client.post(
        f"/api/v1/pairings/generate/{item_id}",
        json={"num_pairings": 3},
        headers=auth_headers,
    )
    assert resp.status_code == 503
    assert "external agent" in resp.json()["detail"]


# --- Service guards run first: deferred contract is unconditional ------------
# These exercise the REAL guard placement (the 503 tests above stub the service
# methods). They lock in fail-fast ordering: with text disabled the guard must
# fire before any location/weather/item validation, so the deferred contract
# never depends on unrelated preconditions.


@pytest.mark.asyncio
async def test_generate_recommendation_defers_before_location_check(
    db_session, test_user, monkeypatch
):
    from app.services.recommendation_service import RecommendationService

    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_text_enabled=False),
    )
    service = RecommendationService(db_session)
    # test_user has no location set; a misordered guard would raise
    # ValueError("User location not set") before reaching the AI guard.
    with pytest.raises(AIDisabledError):
        await service.generate_recommendation(user=test_user, occasion="casual")


@pytest.mark.asyncio
async def test_generate_pairings_defers_before_item_lookup(db_session, test_user, monkeypatch):
    from uuid import uuid4

    from app.services.pairing_service import PairingService

    monkeypatch.setattr(
        "app.services.ai_service.get_settings",
        lambda: Settings(ai_text_enabled=False),
    )
    service = PairingService(db_session)
    # Nonexistent source item; a misordered guard would raise
    # ValueError("Source item not found") before reaching the AI guard.
    with pytest.raises(AIDisabledError):
        await service.generate_pairings(user=test_user, source_item_id=uuid4())
