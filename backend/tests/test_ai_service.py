from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.ai_service import (
    DESCRIPTION_LANGUAGES,
    AIResponseTruncatedError,
    AIService,
    ClothingTags,
)
from app.utils.locale import SUPPORTED_LOCALES

FAKE_REQUEST = httpx.Request("POST", "http://ai-endpoint.test/chat/completions")


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=json_data, request=FAKE_REQUEST)


async def _complete(service: AIService, path: str) -> str:
    if path == "text":
        return await service.generate_text("suggest an outfit")
    content, error, _ = await service._call_with_fallback(
        [{"role": "user", "content": "tag this"}], "tags"
    )
    if error is not None:
        raise error
    return content


class TestLocalizedDescription:
    @pytest.mark.parametrize(
        ("locale", "language"),
        [
            ("en", "English"),
            ("zh-CN", "Simplified Chinese"),
            ("zh-TW", "Traditional Chinese"),
            ("ko", "Korean"),
            ("ja", "Japanese"),
            ("fr", "French"),
            ("de", "German"),
            ("it", "Italian"),
        ],
    )
    @pytest.mark.asyncio
    async def test_only_description_prompt_uses_locale(self, locale, language):
        service = AIService()
        call = AsyncMock(
            side_effect=[
                ('{"type": "shirt", "material": "cotton"}', None, None),
                ("A shirt", None, None),
            ]
        )
        with (
            patch.object(service, "_preprocess_image", return_value="image-data"),
            patch.object(service, "_call_with_fallback", call),
        ):
            tags = await service.analyze_image("unused.jpg", locale=locale)

        tagging_messages = call.call_args_list[0].args[0]
        description_messages = call.call_args_list[1].args[0]
        assert language in description_messages[0]["content"]
        assert "{language}" not in description_messages[0]["content"]
        assert language not in tagging_messages[0]["content"]
        assert tags.type == "shirt"
        assert tags.material == "cotton"
        assert tags.description == "A shirt"

    def test_every_supported_locale_has_a_description_language(self):
        assert set(DESCRIPTION_LANGUAGES) == set(SUPPORTED_LOCALES)

    @pytest.mark.asyncio
    async def test_unexpected_stored_locale_falls_back_to_english(self):
        service = AIService()
        call = AsyncMock(side_effect=[(None, None, None), ("A shirt", None, None)])
        with (
            patch.object(service, "_preprocess_image", return_value="image-data"),
            patch.object(service, "_call_with_fallback", call),
        ):
            await service.analyze_image("unused.jpg", locale="unexpected")

        assert "in English" in call.call_args_list[1].args[0][0]["content"]

    @pytest.mark.parametrize(
        ("reply", "expected"),
        [
            ('"A navy shirt"', "A navy shirt"),
            ("“Eine blaue Bluse”", "Eine blaue Bluse"),
            ("「紺色のシャツ」", "紺色のシャツ"),
            ("『藍色襯衫』", "藍色襯衫"),
            ("« Chemise bleue »", "Chemise bleue"),
            ('Un "trench" beige', 'Un "trench" beige'),
            ('"Levi\'s" jeans in "indigo"', '"Levi\'s" jeans in "indigo"'),
            ("「ユニクロ」のシャツ、色は「紺」", "「ユニクロ」のシャツ、色は「紺」"),
        ],
        ids=[
            "ascii",
            "curly",
            "kagikakko",
            "double-kagikakko",
            "guillemets",
            "inner-quotes",
            "two-quoted-spans",
            "two-kagikakko-spans",
        ],
    )
    @pytest.mark.asyncio
    async def test_description_loses_wrapping_quotes_of_any_script(self, reply, expected):
        service = AIService()
        call = AsyncMock(side_effect=[(None, None, None), (reply, None, None)])
        with (
            patch.object(service, "_preprocess_image", return_value="image-data"),
            patch.object(service, "_call_with_fallback", call),
        ):
            tags = await service.analyze_image("unused.jpg", locale="en")

        assert tags.description == expected


class TestTagParsing:
    """Tests for AI response parsing."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "primary_color": "blue",
            "colors": ["blue", "white"],
            "pattern": "striped",
            "material": "cotton",
            "formality": "casual",
            "confidence": 0.85
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.type == "shirt"
        assert tags.primary_color == "blue"
        assert tags.colors == ["blue", "white"]
        assert tags.pattern == "striped"
        assert tags.material == "cotton"
        # Confidence is now computed by compute_tag_completeness (not AI self-reported)
        # type(0.25) + primary_color(0.20) + pattern(0.15) + formality(0.15) + material(0.10) + colors(0.05) = 0.90
        assert tags.confidence == 0.9

    def test_parse_json_in_markdown(self):
        """Test parsing JSON wrapped in markdown code block."""
        service = AIService()
        response = """
        Here's the analysis:
        ```json
        {
            "type": "pants",
            "primary_color": "black",
            "colors": ["black"],
            "material": "denim",
            "confidence": 0.9
        }
        ```
        """
        tags = service._parse_tags_from_response(response)
        assert tags.type == "pants"
        assert tags.primary_color == "black"
        assert tags.material == "denim"

    def test_parse_invalid_type(self):
        """Test that invalid type returns unknown."""
        service = AIService()
        response = """
        {
            "type": "invalid_type_xyz",
            "primary_color": "blue"
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.type == "unknown"

    def test_rejected_type_is_kept_as_unrecognized(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"type": " Culottes ", "primary_color": "black"}')
        assert tags.type == "unknown"
        assert tags.unrecognized_type == "culottes"

    def test_tights_are_recognized(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"type": " Tights ", "primary_color": "black"}')
        assert tags.type == "tights"
        assert tags.unrecognized_type is None

    def test_missing_type_is_not_unrecognized(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"primary_color": "black"}')
        assert tags.type == "unknown"
        assert tags.unrecognized_type is None

    def test_valid_type_is_not_unrecognized(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"type": "socks"}')
        assert tags.unrecognized_type is None

    def test_parse_invalid_color(self):
        """Test that invalid colors are filtered out."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "primary_color": "chartreuse",
            "colors": ["blue", "invalid_color", "black"]
        }
        """
        tags = service._parse_tags_from_response(response)
        # Invalid colors should be removed
        assert tags.primary_color is None
        assert "blue" in tags.colors
        assert "black" in tags.colors
        assert "invalid_color" not in tags.colors

    def test_parse_grey_to_gray(self):
        """Test that 'grey' is normalized to 'gray'."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "primary_color": "grey"
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.primary_color == "gray"

    def test_frontend_only_names_normalise_to_stored_colors(self):
        service = AIService()
        tags = service._parse_tags_from_response(
            '{"type": "pants", "primary_color": "Charcoal", '
            '"colors": ["charcoal", "gray", "khaki", "teal", "army green", "light-blue"]}'
        )
        assert tags.primary_color == "gray"
        assert tags.colors == ["gray", "tan", "blue", "olive", "light-blue"]

    def test_gold_and_silver_are_stored_not_aliased(self):
        service = AIService()
        tags = service._parse_tags_from_response(
            '{"type": "belt", "primary_color": "gold", "colors": ["gold", "silver"]}'
        )
        assert tags.primary_color == "gold"
        assert tags.colors == ["gold", "silver"]

    def test_parse_invalid_json(self):
        """Test parsing completely invalid response."""
        service = AIService()
        response = "This is not JSON at all, just some random text."
        tags = service._parse_tags_from_response(response)
        assert tags.type == "unknown"
        assert tags.raw_response == response

    def test_parse_confidence_computed_from_completeness(self):
        """Test that confidence is computed from tag completeness, not AI self-reported value."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "confidence": 1.5
        }
        """
        tags = service._parse_tags_from_response(response)
        # Confidence is now computed by compute_tag_completeness: type only = 0.25
        assert tags.confidence == 0.25

    def test_parse_valid_formality(self):
        """Test parsing formality levels."""
        service = AIService()
        response = """
        {
            "type": "blazer",
            "formality": "business-casual"
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.formality == "business-casual"

    def test_parse_invalid_formality(self):
        """Test that invalid formality is None."""
        service = AIService()
        response = """
        {
            "type": "shirt",
            "formality": "ultra-super-formal"
        }
        """
        tags = service._parse_tags_from_response(response)
        assert tags.formality is None

    def test_parse_very_formal(self):
        service = AIService()
        response = '{"type": "suit", "formality": "very-formal", "material": "shearling"}'
        tags = service._parse_tags_from_response(response)
        assert tags.type == "suit"
        assert tags.formality == "very-formal"
        assert tags.material == "shearling"

    def test_parse_down_material(self):
        service = AIService()
        tags = service._parse_tags_from_response('{"type": "jacket", "material": "down"}')
        assert tags.material == "down"


class TestClothingTags:
    """Tests for ClothingTags model."""

    def test_default_values(self):
        """Test default values for ClothingTags."""
        tags = ClothingTags()
        assert tags.type == "unknown"
        assert tags.colors == []
        assert tags.style == []
        assert tags.confidence == 0.0

    def test_full_construction(self):
        """Test constructing ClothingTags with all fields."""
        tags = ClothingTags(
            type="jacket",
            subtype="blazer",
            primary_color="navy",
            colors=["navy", "white"],
            pattern="solid",
            material="wool",
            style=["formal", "classic"],
            formality="formal",
            season=["fall", "winter"],
            confidence=0.92,
            description="A classic navy blazer",
        )
        assert tags.type == "jacket"
        assert tags.subtype == "blazer"
        assert tags.primary_color == "navy"
        assert len(tags.colors) == 2
        assert tags.confidence == 0.92


class TestGenerateTextTruncatedResponse:
    """Regression tests for issue #139: reasoning-capable models (e.g. Qwen3 via

    LM Studio) can exhaust the entire completion token budget on their
    ``reasoning_content`` chain-of-thought, leaving ``message.content`` empty with
    ``finish_reason == "length"``. That used to surface as an opaque "Could not parse
    AI response as JSON: " error, further masked upstream as a generic "AI service is
    not available" message. It should now raise AIResponseTruncatedError with the real
    cause, every retry attempt, so callers can tell the user what actually happened.
    """

    @staticmethod
    def _truncated_reasoning_response() -> dict:
        # Mirrors the exact shape reported in the issue's attached LM Studio /
        # backend logs: assistant content is empty, the model's chain-of-thought
        # landed in reasoning_content instead, and finish_reason is "length".
        return {
            "id": "chatcmpl-j0ue2a2xp0kziw0f8gof",
            "object": "chat.completion",
            "model": "qwen/qwen3.5-9b",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "The user wants me to create 3 outfits...",
                        "tool_calls": [],
                    },
                    "finish_reason": "length",
                }
            ],
            "usage": {"prompt_tokens": 3417, "completion_tokens": 4775, "total_tokens": 8192},
        }

    @pytest.mark.asyncio
    async def test_empty_content_with_reasoning_raises_truncated_error(self):
        service = AIService()
        mock_response = _mock_response(self._truncated_reasoning_response())

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(AIResponseTruncatedError) as exc_info:
                await service.generate_text("suggest an outfit")

        message = str(exc_info.value)
        assert "reasoning" in message
        assert "AI_MAX_TOKENS" in message

    @pytest.mark.asyncio
    async def test_empty_content_without_reasoning_still_raises_truncated_error(self):
        service = AIService()
        payload = self._truncated_reasoning_response()
        del payload["choices"][0]["message"]["reasoning_content"]
        mock_response = _mock_response(payload)

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(AIResponseTruncatedError):
                await service.generate_text("suggest an outfit")

    @pytest.mark.asyncio
    async def test_missing_content_key_raises_truncated_error(self):
        # Some providers omit the "content" key entirely instead of returning ""
        # when the response is truncated; bracket access would raise KeyError
        # instead of the actionable AIResponseTruncatedError.
        service = AIService()
        payload = self._truncated_reasoning_response()
        del payload["choices"][0]["message"]["content"]
        mock_response = _mock_response(payload)

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            with pytest.raises(AIResponseTruncatedError):
                await service.generate_text("suggest an outfit")

    @pytest.mark.asyncio
    async def test_normal_response_is_unaffected(self):
        service = AIService()
        payload = self._truncated_reasoning_response()
        payload["choices"][0]["message"]["content"] = '{"outfits": []}'
        payload["choices"][0]["message"]["reasoning_content"] = ""
        payload["choices"][0]["finish_reason"] = "stop"
        mock_response = _mock_response(payload)

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'


class TestGenerateTextErrorEnvelope:
    """HTTP 200 provider error envelopes must use normal retry/fallback handling."""

    @staticmethod
    def _success_response() -> httpx.Response:
        return _mock_response(
            {
                "model": "text-model",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            }
        )

    @pytest.mark.asyncio
    async def test_generate_text_retries_after_200_error_envelope(self):
        service = AIService()
        error_envelope = _mock_response({"error": {"message": "The operation was aborted"}})

        with patch(
            "httpx.AsyncClient.post", side_effect=[error_envelope, self._success_response()]
        ) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == "ok"
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_text_repeated_200_error_envelope_raises_controlled_error(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        error_envelope = _mock_response({"error": {"message": "The operation was aborted"}})

        with patch("httpx.AsyncClient.post", return_value=error_envelope):
            with pytest.raises(RuntimeError, match="The operation was aborted"):
                await service.generate_text("suggest an outfit")


class TestEmptyCompletion:
    """A blank vision completion read as success left analyze_image storing an "unknown"
    item with no error to raise, so both paths must treat it as a failed attempt."""

    @staticmethod
    def _empty_vision_response() -> dict:
        return {
            "model": "vision-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": ""},
                    "finish_reason": "length",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_blank_completion_is_not_treated_as_success(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        mock_response = _mock_response(self._empty_vision_response())

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            content, error, _ = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags"
            )

        assert content is None
        assert isinstance(error, AIResponseTruncatedError)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("first_endpoint", "retryable"),
        [("unreachable", True), ("cut-off", False)],
    )
    async def test_cutoff_is_retryable_unless_every_endpoint_cut_off(
        self, first_endpoint, retryable
    ):
        service = AIService(endpoints=[{"url": "http://custom:11434/v1", "name": "custom"}])
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        first = (
            httpx.ConnectError("custom down")
            if first_endpoint == "unreachable"
            else _mock_response(self._empty_vision_response())
        )

        with patch(
            "httpx.AsyncClient.post",
            side_effect=[first, _mock_response(self._empty_vision_response())],
        ):
            _, error, _ = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags"
            )

        assert isinstance(error, AIResponseTruncatedError)
        assert error.retryable is retryable

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["vision", "text"])
    @pytest.mark.parametrize(("finish_reason", "expected_calls"), [("length", 1), ("stop", 3)])
    async def test_only_an_empty_completion_that_can_change_is_retried(
        self, path, finish_reason, expected_calls
    ):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 3})
        payload = self._empty_vision_response()
        payload["choices"][0]["finish_reason"] = finish_reason

        with (
            patch("httpx.AsyncClient.post", return_value=_mock_response(payload)) as mock_post,
            patch("app.services.ai_service.asyncio.sleep"),
        ):
            with pytest.raises(AIResponseTruncatedError) as exc_info:
                await _complete(service, path)

        assert mock_post.call_count == expected_calls
        assert exc_info.value.retryable is (finish_reason != "length")

    def _analyze_responses(self, tags_content: str, description: str | int) -> list:
        tags_payload = self._empty_vision_response()
        tags_payload["choices"][0]["message"]["content"] = tags_content
        if isinstance(description, int):
            return [
                _mock_response(tags_payload),
                _mock_response({"error": "upstream down"}, status_code=description),
            ]
        description_payload = self._empty_vision_response()
        description_payload["choices"][0]["message"]["content"] = description
        description_payload["choices"][0]["finish_reason"] = "stop" if description else "length"
        return [_mock_response(tags_payload), _mock_response(description_payload)]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("max_retries", "tags_content", "description", "expected_error", "message", "retryable"),
        [
            (1, "", "", AIResponseTruncatedError, "empty response", False),
            (1, "", 503, AIResponseTruncatedError, "empty response", True),
            (1, "I cannot identify this garment.", 500, RuntimeError, "no usable tags", True),
            (1, "{}", '""', RuntimeError, "empty description reply", True),
            (0, "", "", RuntimeError, "nothing usable", True),
        ],
        ids=[
            "empty-completions",
            "cut-tags-transient-description",
            "unparseable-tags",
            "empty-json-empty-description",
            "no-attempts",
        ],
    )
    async def test_analyze_image_raises_when_neither_pass_returns_anything_usable(
        self, max_retries, tags_content, description, expected_error, message, retryable
    ):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": max_retries})

        with (
            patch(
                "httpx.AsyncClient.post",
                side_effect=self._analyze_responses(tags_content, description),
            ),
            patch.object(AIService, "_preprocess_image", return_value="base64data"),
        ):
            with pytest.raises(expected_error, match=message) as exc_info:
                await service.analyze_image("/fake/image.jpg", locale="en")

        assert type(exc_info.value) is expected_error
        assert getattr(exc_info.value, "retryable", True) is retryable

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tags_content", "description", "expected"),
        [
            ('{"type": "poncho"}', 500, {"unrecognized_type": "poncho"}),
            ('{"subtype": "maxi"}', 500, {"subtype": "maxi"}),
            ("", "A navy jumpsuit", {"description": "A navy jumpsuit"}),
        ],
        ids=["unsupported-type-only", "subtype-only", "description-only"],
    )
    async def test_analyze_image_keeps_a_partial_result(self, tags_content, description, expected):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})

        with (
            patch(
                "httpx.AsyncClient.post",
                side_effect=self._analyze_responses(tags_content, description),
            ),
            patch.object(AIService, "_preprocess_image", return_value="base64data"),
        ):
            tags = await service.analyze_image("/fake/image.jpg", locale="en")

        assert tags.type == "unknown"
        for field, value in expected.items():
            assert getattr(tags, field) == value


class TestLogprobsRejection:
    """Regression tests for issue #143: providers like Gemini reject the

    logprobs/top_logprobs request params with a 400, which used to burn every
    retry attempt and leave tags empty (while the separate, logprobs-free
    description call succeeded silently, giving no indication of the failure).
    """

    _TAGS_CONTENT = '{"type": "shirt", "primary_color": "blue", "colors": ["blue"]}'

    @staticmethod
    def _logprobs_rejected_response() -> httpx.Response:
        # Mirrors Gemini's OpenAI-compat error shape from the issue report.
        return _mock_response(
            {"error": {"message": 'Unknown name "logprobs": Cannot find field.'}},
            status_code=400,
        )

    @staticmethod
    def _success_response(content: str) -> httpx.Response:
        return _mock_response(
            {
                "model": "gemini-2.0-flash",
                "choices": [{"message": {"content": content}}],
            }
        )

    @pytest.mark.asyncio
    async def test_retries_without_logprobs_after_rejection(self):
        service = AIService()
        responses = [self._logprobs_rejected_response(), self._success_response(self._TAGS_CONTENT)]

        with patch("httpx.AsyncClient.post", side_effect=responses) as mock_post:
            content, err, logprobs_content = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert err is None
        assert content == self._TAGS_CONTENT
        assert logprobs_content is None
        assert mock_post.call_count == 2
        first_body = mock_post.call_args_list[0].kwargs["json"]
        second_body = mock_post.call_args_list[1].kwargs["json"]
        assert first_body["logprobs"] is True
        assert "logprobs" not in second_body
        assert "top_logprobs" not in second_body

    @pytest.mark.asyncio
    async def test_retries_without_logprobs_after_200_error_envelope(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        error_envelope = _mock_response(
            {"error": {"message": 'Unknown name "logprobs": Cannot find field.'}}
        )
        responses = [error_envelope, self._success_response(self._TAGS_CONTENT)]

        with patch("httpx.AsyncClient.post", side_effect=responses) as mock_post:
            content, err, logprobs_content = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert err is None
        assert content == self._TAGS_CONTENT
        assert logprobs_content is None
        assert mock_post.call_count == 2
        first_body = mock_post.call_args_list[0].kwargs["json"]
        second_body = mock_post.call_args_list[1].kwargs["json"]
        assert first_body["logprobs"] is True
        assert "logprobs" not in second_body
        assert "top_logprobs" not in second_body

    @pytest.mark.asyncio
    async def test_repeated_200_error_envelope_returns_controlled_error(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        error_envelope = _mock_response({"error": {"message": "The operation was aborted"}})

        with patch("httpx.AsyncClient.post", return_value=error_envelope) as mock_post:
            content, err, logprobs_content = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert content is None
        assert isinstance(err, RuntimeError)
        assert "The operation was aborted" in str(err)
        assert logprobs_content is None
        assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_transient_200_error_envelope_keeps_logprobs_and_backs_off(self):
        # An overloaded provider says nothing about logprobs, so dropping them would cost
        # the item its logprobs confidence and hammer the endpoint with no backoff.
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 2})
        error_envelope = _mock_response({"error": {"message": "Model is overloaded"}})
        logprobs = [{"token": "shirt", "logprob": -0.1}]
        success = _mock_response(
            {
                "model": "gemini-2.0-flash",
                "choices": [
                    {"message": {"content": self._TAGS_CONTENT}, "logprobs": {"content": logprobs}}
                ],
            }
        )

        with (
            patch("httpx.AsyncClient.post", side_effect=[error_envelope, success]) as mock_post,
            patch("app.services.ai_service.asyncio.sleep") as mock_sleep,
        ):
            content, err, logprobs_content = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert err is None
        assert content == self._TAGS_CONTENT
        assert logprobs_content == logprobs
        assert mock_post.call_args_list[1].kwargs["json"]["logprobs"] is True
        mock_sleep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logprobs_rejection_does_not_consume_retry_budget(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        responses = [self._logprobs_rejected_response(), self._success_response(self._TAGS_CONTENT)]

        with patch("httpx.AsyncClient.post", side_effect=responses) as mock_post:
            content, err, _ = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert err is None
        assert content == self._TAGS_CONTENT
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_unrelated_400_is_not_treated_as_logprobs_rejection(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        unrelated_400 = _mock_response({"error": {"message": "invalid model"}}, status_code=400)

        with patch("httpx.AsyncClient.post", return_value=unrelated_400) as mock_post:
            content, err, _ = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags", request_logprobs=True
            )

        assert content is None
        assert err is not None
        assert mock_post.call_count == 1


class TestReasoningEffort:
    """Tests for reasoning_effort configuration, rejection handling, and recovery."""

    @staticmethod
    def _reasoning_effort_rejected_response() -> httpx.Response:
        return _mock_response(
            {
                "error": {
                    "message": "Unsupported parameter: 'reasoning_effort' is not supported with this model."
                }
            },
            status_code=400,
        )

    @staticmethod
    def _success_response(content: str = '{"outfits": []}') -> httpx.Response:
        return _mock_response(
            {
                "model": "gemma4:12b",
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            }
        )

    @pytest.mark.asyncio
    async def test_generate_text_includes_default_reasoning_effort(self):
        service = AIService()
        mock_response = self._success_response()

        with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
            await service.generate_text("suggest an outfit")

        assert mock_post.call_count == 1
        body = mock_post.call_args.kwargs["json"]
        assert body.get("reasoning_effort") == "none"

    @pytest.mark.asyncio
    async def test_generate_text_retries_without_reasoning_effort_after_rejection(self):
        service = AIService()
        responses = [self._reasoning_effort_rejected_response(), self._success_response()]

        with patch("httpx.AsyncClient.post", side_effect=responses) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'
        assert mock_post.call_count == 2
        first_body = mock_post.call_args_list[0].kwargs["json"]
        second_body = mock_post.call_args_list[1].kwargs["json"]
        assert first_body.get("reasoning_effort") == "none"
        assert "reasoning_effort" not in second_body

    @pytest.mark.asyncio
    async def test_generate_text_retries_without_reasoning_effort_after_200_error_envelope(self):
        service = AIService()
        rejected = _mock_response(
            {"error": {"message": "Unsupported parameter: 'reasoning_effort'"}}
        )
        with patch(
            "httpx.AsyncClient.post", side_effect=[rejected, self._success_response()]
        ) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'
        assert "reasoning_effort" not in mock_post.call_args_list[1].kwargs["json"]

    @pytest.mark.asyncio
    async def test_vision_retries_without_reasoning_effort_after_200_error_envelope(self):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_max_retries": 1})
        rejected = _mock_response(
            {"error": {"message": "Unsupported parameter: 'reasoning_effort'"}}
        )
        with patch(
            "httpx.AsyncClient.post", side_effect=[rejected, self._success_response("tags")]
        ) as mock_post:
            content, err, _ = await service._call_with_fallback(
                [{"role": "user", "content": "tag this"}], "tags"
            )

        assert err is None
        assert content == "tags"
        assert "reasoning_effort" not in mock_post.call_args_list[1].kwargs["json"]

    @pytest.mark.asyncio
    async def test_empty_content_with_ollama_reasoning_raises_truncated_error(self):
        service = AIService()
        # Ollama returns "reasoning", not "reasoning_content"
        ollama_response = _mock_response(
            {
                "id": "chatcmpl-123",
                "model": "gemma4:12b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning": "Let me think about styling outfits...",
                        },
                        "finish_reason": "length",
                    }
                ],
            }
        )

        with patch("httpx.AsyncClient.post", return_value=ollama_response):
            with pytest.raises(AIResponseTruncatedError) as exc_info:
                await service.generate_text("suggest an outfit")

        assert "reasoning" in str(exc_info.value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path", ["vision", "text"])
    async def test_truncation_recovers_by_retrying_with_none(self, path):
        service = AIService()
        service.settings = service.settings.model_copy(update={"ai_reasoning_effort": "high"})
        truncated = _mock_response(
            {
                "id": "chatcmpl-123",
                "model": "gemma4:12b",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "reasoning": "Thinking consumed all tokens...",
                        },
                        "finish_reason": "length",
                    }
                ],
            }
        )
        success = self._success_response('{"outfits": [{"items": [1, 2]}]}')

        with patch("httpx.AsyncClient.post", side_effect=[truncated, success]) as mock_post:
            result = await _complete(service, path)

        assert "items" in result
        assert mock_post.call_count == 2
        # First call had reasoning_effort="high"
        assert mock_post.call_args_list[0].kwargs["json"].get("reasoning_effort") == "high"
        # Recovered call switched to reasoning_effort="none"
        assert mock_post.call_args_list[1].kwargs["json"].get("reasoning_effort") == "none"

    @pytest.mark.asyncio
    async def test_ollama_invalid_think_value_falls_back_without_reasoning_effort(self):
        # Ollama releases predating the "none" effort level reject it without ever naming
        # reasoning_effort, so matching only OpenAI's wording would fail every request.
        service = AIService()
        ollama_rejection = _mock_response(
            {
                "error": 'invalid think value: "none" (must be "high", "medium", "low", true, or false)'
            },
            status_code=400,
        )

        with patch(
            "httpx.AsyncClient.post", side_effect=[ollama_rejection, self._success_response()]
        ) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'
        assert mock_post.call_count == 2
        assert mock_post.call_args_list[0].kwargs["json"].get("reasoning_effort") == "none"
        assert "reasoning_effort" not in mock_post.call_args_list[1].kwargs["json"]

    @pytest.mark.asyncio
    async def test_transient_empty_response_still_retries(self):
        service = AIService()
        empty = _mock_response(
            {
                "model": "gemma3:latest",
                "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
            }
        )

        with patch(
            "httpx.AsyncClient.post", side_effect=[empty, self._success_response()]
        ) as mock_post:
            content = await service.generate_text("suggest an outfit")

        assert content == '{"outfits": []}'
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_length_cutoff_at_lowest_effort_does_not_retry(self):
        service = AIService()
        truncated = _mock_response(
            {
                "model": "gemma4:12b",
                "choices": [
                    {
                        "message": {"content": "", "reasoning": "still thinking"},
                        "finish_reason": "length",
                    }
                ],
            }
        )

        with patch("httpx.AsyncClient.post", return_value=truncated) as mock_post:
            with pytest.raises(AIResponseTruncatedError):
                await service.generate_text("suggest an outfit")

        assert mock_post.call_count == 1
