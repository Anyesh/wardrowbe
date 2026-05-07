from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_onboarding_state_returns_blocking_style_quiz_for_new_user(
    client: AsyncClient,
    test_user,
    auth_headers,
):
    response = await client.get("/api/v1/onboarding/state", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["is_blocking"] is True
    assert data["current_step"] == "style_quiz"
    assert any(step["step_key"] == "style_quiz" for step in data["active_steps"])


@pytest.mark.asyncio
async def test_get_style_quiz_definition_returns_six_questions(
    client: AsyncClient,
    test_user,
    auth_headers,
):
    response = await client.get("/api/v1/onboarding/steps/style-quiz", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["step_key"] == "style_quiz"
    assert len(data["questions"]) == 6


@pytest.mark.asyncio
async def test_submit_style_quiz_updates_preferences_and_unlocks(
    client: AsyncClient,
    test_user,
    auth_headers,
):
    payload = {
        "quiz_version": "v1",
        "answers": {
            "primary_occasion": "casual",
            "style_focus": "minimalist",
            "color_palette": "neutral",
            "avoid_colors": ["orange"],
            "temperature_feel": "cold",
            "variety": "moderate",
        },
    }

    response = await client.post(
        "/api/v1/onboarding/steps/style-quiz/submit",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["updated_preferences"]["default_occasion"] == "casual"
    assert response_data["updated_preferences"]["layering_preference"] == "heavy"
    assert "orange" in response_data["updated_preferences"]["color_avoid"]

    state_resp = await client.get("/api/v1/onboarding/state", headers=auth_headers)
    assert state_resp.status_code == 200
    assert state_resp.json()["is_blocking"] is False


@pytest.mark.asyncio
async def test_submit_style_quiz_falls_back_when_ai_fails(
    client: AsyncClient,
    test_user,
    auth_headers,
    monkeypatch,
):
    from app.services.style_quiz_insight import StyleQuizInsightService

    monkeypatch.setattr(
        StyleQuizInsightService,
        "generate",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    payload = {
        "quiz_version": "v1",
        "answers": {
            "primary_occasion": "office",
            "style_focus": "formal",
            "color_palette": "neutral",
            "avoid_colors": [],
            "temperature_feel": "normal",
            "variety": "moderate",
        },
    }
    response = await client.post(
        "/api/v1/onboarding/steps/style-quiz/submit",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert "风格" in response.json()["style_insight"]


@pytest.mark.asyncio
async def test_wechat_sync_new_user_can_immediately_fetch_onboarding_state(
    client: AsyncClient,
):
    external_subject = f"openid-{uuid4()}"
    sync_resp = await client.post(
        "/api/v1/auth/wechat-miniapp/sync",
        json={
            "openid": external_subject,
            "display_name": "Fresh User",
        },
    )
    assert sync_resp.status_code == 200
    token = sync_resp.json()["access_token"]

    state_resp = await client.get(
        "/api/v1/onboarding/state",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert state_resp.status_code == 200
    assert state_resp.json()["current_step"] == "style_quiz"


@pytest.mark.asyncio
async def test_retake_style_quiz_keeps_unblocked_and_updates_preferences(
    client: AsyncClient,
    test_user,
    auth_headers,
):
    first = {
        "quiz_version": "v1",
        "answers": {
            "primary_occasion": "casual",
            "style_focus": "casual",
            "color_palette": "neutral",
            "avoid_colors": [],
            "temperature_feel": "normal",
            "variety": "low",
        },
    }
    second = {
        "quiz_version": "v1",
        "answers": {
            "primary_occasion": "formal",
            "style_focus": "formal",
            "color_palette": "bright",
            "avoid_colors": ["orange"],
            "temperature_feel": "hot",
            "variety": "high",
        },
    }

    first_resp = await client.post(
        "/api/v1/onboarding/steps/style-quiz/submit",
        json=first,
        headers=auth_headers,
    )
    assert first_resp.status_code == 200

    second_resp = await client.post(
        "/api/v1/onboarding/steps/style-quiz/submit",
        json=second,
        headers=auth_headers,
    )
    assert second_resp.status_code == 200

    prefs_resp = await client.get("/api/v1/users/me/preferences", headers=auth_headers)
    assert prefs_resp.status_code == 200
    assert prefs_resp.json()["default_occasion"] == "formal"

    state_resp = await client.get("/api/v1/onboarding/state", headers=auth_headers)
    assert state_resp.status_code == 200
    assert state_resp.json()["is_blocking"] is False


@pytest.mark.asyncio
async def test_reopen_style_quiz_sets_blocking_true(
    client: AsyncClient,
    test_user,
    auth_headers,
):
    payload = {
        "quiz_version": "v1",
        "answers": {
            "primary_occasion": "casual",
            "style_focus": "casual",
            "color_palette": "neutral",
            "avoid_colors": [],
            "temperature_feel": "normal",
            "variety": "moderate",
        },
    }

    submit_resp = await client.post(
        "/api/v1/onboarding/steps/style-quiz/submit",
        json=payload,
        headers=auth_headers,
    )
    assert submit_resp.status_code == 200

    reopen_resp = await client.post(
        "/api/v1/onboarding/steps/style-quiz/reopen",
        headers=auth_headers,
    )
    assert reopen_resp.status_code == 200

    state_resp = await client.get("/api/v1/onboarding/state", headers=auth_headers)
    assert state_resp.status_code == 200
    state_data = state_resp.json()
    assert state_data["is_blocking"] is True
    assert state_data["current_step"] == "style_quiz"
