from unittest.mock import patch

import httpx
import pytest

from app.services.ai_service import AIResponseTruncatedError, AIService, ClothingTags

FAKE_REQUEST = httpx.Request("POST", "http://ai-endpoint.test/chat/completions")


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=json_data, request=FAKE_REQUEST)


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
