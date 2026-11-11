from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.preference import UserPreference
from app.services.ai_service import AIService
from app.utils.ai_endpoints import merge_endpoints, public_endpoint

FAKE_REQUEST = httpx.Request("GET", "http://test")
VLLM = "http://vllm.lan:8000/v1"


def _incoming(**fields) -> SimpleNamespace:
    endpoint = {
        "id": None,
        "name": "vllm",
        "url": VLLM,
        "vision_model": "qwen2.5-vl",
        "text_model": "qwen2.5",
        "enabled": True,
        "api_key": None,
    }
    endpoint.update(fields)
    return SimpleNamespace(**endpoint)


@pytest.fixture
def server_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_api_key", "server-key")
    return "server-key"


class TestMergeEndpoints:
    def test_a_new_endpoint_stores_its_key_under_a_fresh_id(self):
        [stored] = merge_endpoints([_incoming(api_key=" secret ")], [])
        assert stored["api_key"] == "secret"
        assert stored["id"]

    def test_a_new_endpoint_without_a_key_has_none_rather_than_the_server_key(self):
        [stored] = merge_endpoints([_incoming()], [])
        assert stored["api_key"] is None
        assert public_endpoint(stored)["uses_server_key"] is False

    def test_an_endpoint_sent_back_without_a_key_keeps_the_stored_one(self):
        [first] = merge_endpoints([_incoming(api_key="secret")], [])
        [again] = merge_endpoints([_incoming(id=first["id"], name="renamed")], [first])
        assert again["api_key"] == "secret"
        assert again["id"] == first["id"]
        assert again["name"] == "renamed"

    def test_an_empty_key_removes_the_stored_one(self):
        [first] = merge_endpoints([_incoming(api_key="secret")], [])
        [again] = merge_endpoints([_incoming(id=first["id"], api_key="")], [first])
        assert again["api_key"] is None

    def test_pointing_an_endpoint_at_another_server_drops_its_key(self):
        [first] = merge_endpoints([_incoming(api_key="secret")], [])
        [moved] = merge_endpoints([_incoming(id=first["id"], url="http://elsewhere/v1")], [first])
        assert moved["api_key"] is None

    def test_a_trailing_slash_is_not_another_server(self):
        [first] = merge_endpoints([_incoming(api_key="secret")], [])
        [again] = merge_endpoints([_incoming(id=first["id"], url=VLLM + "/")], [first])
        assert again["api_key"] == "secret"

    def test_reordering_keeps_each_key_with_its_endpoint(self):
        stored = merge_endpoints(
            [
                _incoming(name="vision", api_key="vision-key"),
                _incoming(name="text", url="http://text.lan/v1", api_key="text-key"),
            ],
            [],
        )
        reordered = merge_endpoints(
            [
                _incoming(id=stored[1]["id"], name="text", url="http://text.lan/v1"),
                _incoming(id=stored[0]["id"], name="vision"),
            ],
            stored,
        )
        assert [(ep["name"], ep["api_key"]) for ep in reordered] == [
            ("text", "text-key"),
            ("vision", "vision-key"),
        ]

    def test_an_endpoint_saved_before_keys_keeps_using_the_server_key(self):
        legacy = {"name": "old", "url": VLLM, "vision_model": "llava", "text_model": "llama"}
        [again] = merge_endpoints([_incoming(name="old")], [legacy])
        assert "api_key" not in again
        assert public_endpoint(again)["uses_server_key"] is True

    def test_an_old_endpoint_moved_to_another_server_stops_getting_the_server_key(self):
        legacy = {"name": "old", "url": VLLM}
        [moved] = merge_endpoints([_incoming(url="http://elsewhere/v1")], [legacy])
        assert moved["api_key"] is None

    def test_an_unknown_id_is_a_new_endpoint(self):
        [first] = merge_endpoints([_incoming(api_key="secret")], [])
        [other] = merge_endpoints([_incoming(id="made-up")], [first])
        assert other["api_key"] is None
        assert other["id"] != "made-up"

    def test_the_public_view_never_carries_the_key(self):
        [stored] = merge_endpoints([_incoming(api_key="secret")], [])
        public = public_endpoint(stored)
        assert "secret" not in str(public)
        assert public["has_api_key"] is True


def _ok(content: str = "ok") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "m",
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        },
        request=FAKE_REQUEST,
    )


class TestAIServiceEndpoints:
    def test_each_endpoint_gets_its_own_key(self, server_key):
        service = AIService(
            endpoints=[
                {"url": "http://own/v1", "api_key": "own-key"},
                {"url": "http://keyless/v1", "api_key": None},
                {"url": "http://legacy/v1"},
            ]
        )
        assert [ep.api_key for ep in service._endpoints] == [
            "own-key",
            None,
            server_key,
            server_key,
        ]

    @pytest.mark.asyncio
    async def test_requests_carry_the_endpoints_own_key(self, server_key):
        service = AIService(endpoints=[{"url": "http://own/v1", "api_key": "own-key"}])
        with patch("httpx.AsyncClient.post", autospec=True, return_value=_ok()) as post:
            await service.generate_text("suggest an outfit")
        _, url = post.await_args.args
        assert url == "http://own/v1/chat/completions"
        assert post.await_args.kwargs["headers"]["Authorization"] == "Bearer own-key"

    @pytest.mark.asyncio
    async def test_a_keyless_endpoint_sends_no_authorization(self, server_key):
        service = AIService(endpoints=[{"url": "http://keyless/v1", "api_key": None}])
        with patch("httpx.AsyncClient.post", autospec=True, return_value=_ok()) as post:
            await service.generate_text("suggest an outfit")
        assert "Authorization" not in post.await_args.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_text_skips_an_endpoint_without_a_text_model(self):
        service = AIService(
            endpoints=[
                {"url": "http://vision-only/v1", "vision_model": "qwen2.5-vl", "text_model": None},
                {"url": "http://text-only/v1", "vision_model": "", "text_model": "qwen2.5"},
            ]
        )
        with patch("httpx.AsyncClient.post", autospec=True, return_value=_ok()) as post:
            await service.generate_text("suggest an outfit")
        assert [call.args[1] for call in post.await_args_list] == [
            "http://text-only/v1/chat/completions"
        ]
        assert post.await_args.kwargs["json"]["model"] == "qwen2.5"

    @pytest.mark.asyncio
    async def test_vision_skips_an_endpoint_without_a_vision_model(self):
        service = AIService(
            endpoints=[
                {"url": "http://text-only/v1", "vision_model": None, "text_model": "qwen2.5"},
                {"url": "http://vision-only/v1", "vision_model": "qwen2.5-vl", "text_model": ""},
            ]
        )
        with patch("httpx.AsyncClient.post", autospec=True, return_value=_ok()) as post:
            content, error, _ = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags"
            )
        assert error is None
        assert [call.args[1] for call in post.await_args_list] == [
            "http://vision-only/v1/chat/completions"
        ]
        assert post.await_args.kwargs["json"]["model"] == "qwen2.5-vl"


class TestPreferencesApi:
    @pytest.mark.asyncio
    async def test_a_saved_key_is_never_sent_back(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        endpoint = {"name": "vllm", "url": VLLM, "vision_model": "qwen2.5-vl", "text_model": ""}
        response = await client.patch(
            "/api/v1/users/me/preferences",
            json={"ai_endpoints": [{**endpoint, "api_key": "secret"}]},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert "secret" not in response.text
        [saved] = response.json()["ai_endpoints"]
        assert saved["has_api_key"] is True
        assert saved["text_model"] is None

        # The settings page sends the endpoint back as it received it, without a key.
        response = await client.patch(
            "/api/v1/users/me/preferences",
            json={"ai_endpoints": [{**saved, "name": "renamed"}]},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["ai_endpoints"][0]["has_api_key"] is True

        preferences = await db_session.get(UserPreference, test_user.id, populate_existing=True)
        assert preferences.ai_endpoints[0]["api_key"] == "secret"
        assert preferences.ai_endpoints[0]["name"] == "renamed"

    @pytest.mark.asyncio
    async def test_the_connection_test_uses_the_saved_key_for_its_url(
        self, client: AsyncClient, db_session: AsyncSession, test_user, auth_headers
    ):
        db_session.add(
            UserPreference(
                user_id=test_user.id,
                ai_endpoints=[{"id": "ep1", "name": "vllm", "url": VLLM, "api_key": "secret"}],
            )
        )
        await db_session.commit()
        models = httpx.Response(
            200, json={"data": [{"id": "qwen2.5-vl"}, {"id": "qwen2.5"}]}, request=FAKE_REQUEST
        )

        with patch("httpx.AsyncClient.get", autospec=True, return_value=models) as get:
            response = await client.post(
                "/api/v1/users/me/preferences/test-ai-endpoint",
                json={"url": VLLM, "id": "ep1"},
                headers=auth_headers,
            )
            assert response.json() == {
                "status": "connected",
                "available_models": ["qwen2.5-vl", "qwen2.5"],
                "vision_models": ["qwen2.5-vl"],
                "text_models": ["qwen2.5"],
            }
            assert get.await_args.args[1] == f"{VLLM}/models"
            assert get.await_args.kwargs["headers"] == {"Authorization": "Bearer secret"}

            # The same endpoint pointed at another server is tested without the saved key.
            await client.post(
                "/api/v1/users/me/preferences/test-ai-endpoint",
                json={"url": "http://elsewhere/v1", "id": "ep1"},
                headers=auth_headers,
            )
            assert get.await_args_list[1].kwargs["headers"] == {}

    @pytest.mark.asyncio
    async def test_the_connection_test_reports_a_rejected_key(
        self, client: AsyncClient, test_user, auth_headers
    ):
        rejected = httpx.Response(401, json={"error": "unauthorized"}, request=FAKE_REQUEST)
        with patch("httpx.AsyncClient.get", autospec=True, return_value=rejected):
            response = await client.post(
                "/api/v1/users/me/preferences/test-ai-endpoint",
                json={"url": VLLM, "api_key": "wrong"},
                headers=auth_headers,
            )
        assert response.json() == {
            "status": "error",
            "error": "HTTP 401 - check the API key",
            "error_code": "AI_ENDPOINT_KEY_REJECTED",
            "params": {"status": 401},
        }
