import base64
import io
import json
import logging
import math
import re
from pathlib import Path

import httpx
from PIL import Image, ImageOps
from pydantic import BaseModel

from app.config import get_settings
from app.utils.prompts import load_prompt

logger = logging.getLogger(__name__)


class TextGenerationResult(BaseModel):
    content: str
    model: str
    endpoint: str


class ClothingTags(BaseModel):
    type: str = "unknown"
    subtype: str | None = None
    primary_color: str | None = None
    colors: list[str] = []
    pattern: str | None = None
    material: str | None = None
    style: list[str] = []
    formality: str | None = None
    season: list[str] = []
    fit: str | None = None
    occasion: list[str] = []
    brand: str | None = None
    condition: str | None = None
    features: list[str] = []
    confidence: float = 0.0
    logprobs_confidence: float | None = None
    description: str | None = None
    raw_response: str | None = None


TAGGING_PROMPT = load_prompt("clothing_analysis")
DESCRIPTION_PROMPT = load_prompt("clothing_description")

# Valid values for validation
VALID_TYPES = {
    "shirt",
    "t-shirt",
    "pants",
    "jeans",
    "shorts",
    "dress",
    "skirt",
    "jacket",
    "coat",
    "sweater",
    "hoodie",
    "blazer",
    "vest",
    "cardigan",
    "polo",
    "blouse",
    "tank-top",
    "shoes",
    "sneakers",
    "boots",
    "sandals",
    "hat",
    "scarf",
    "belt",
    "bag",
    "accessories",
    "top",
    "jumpsuit",
    "socks",
    "tie",
}
VALID_COLORS = {
    "black",
    "white",
    "gray",
    "navy",
    "blue",
    "light-blue",
    "red",
    "burgundy",
    "pink",
    "green",
    "olive",
    "yellow",
    "orange",
    "purple",
    "brown",
    "tan",
    "beige",
    "cream",
    "gold",
    "silver",
}
VALID_PATTERNS = {
    "solid",
    "striped",
    "plaid",
    "checkered",
    "floral",
    "graphic",
    "geometric",
    "polka-dot",
    "camouflage",
    "animal-print",
}
VALID_MATERIALS = {
    "cotton",
    "denim",
    "leather",
    "wool",
    "polyester",
    "silk",
    "linen",
    "knit",
    "fleece",
    "suede",
    "velvet",
    "nylon",
    "canvas",
}
VALID_FORMALITY = {"very-casual", "casual", "smart-casual", "business-casual", "formal"}
VALID_FIT = {"slim", "regular", "relaxed", "oversized", "tailored", "cropped"}
VALID_STYLES = {
    "casual",
    "classic",
    "sporty",
    "minimalist",
    "bohemian",
    "preppy",
    "streetwear",
    "elegant",
    "athletic",
    "vintage",
    "modern",
    "rugged",
}
VALID_SEASONS = {"spring", "summer", "fall", "winter", "all-season"}


def compute_tag_completeness(tags: "ClothingTags") -> float:
    score = 0.0
    if tags.type and tags.type != "unknown":
        score += 0.25
    if tags.primary_color:
        score += 0.20
    if tags.pattern:
        score += 0.15
    if tags.formality:
        score += 0.15
    if tags.material:
        score += 0.10
    if tags.season:
        score += 0.05
    if tags.style:
        score += 0.05
    if tags.colors:
        score += 0.05
    return round(score, 2)


_CONFIDENCE_FIELDS = {"type", "primary_color", "pattern", "material", "formality"}


def compute_confidence_from_logprobs(logprobs_content: list[dict] | None) -> float | None:
    if not logprobs_content:
        return None

    field_probs: dict[str, list[float]] = {}
    current_key = None
    expect_value = False

    for entry in logprobs_content:
        token = entry.get("token", "")
        logprob = entry.get("logprob", 0)
        prob = math.exp(logprob)
        stripped = token.strip().strip('"').strip("'")

        if stripped in _CONFIDENCE_FIELDS:
            current_key = stripped
            expect_value = False
            continue

        if current_key and ":" in token:
            expect_value = True
            continue

        if expect_value and current_key and stripped and stripped not in ("{", "[", ",", "}", "]"):
            if stripped == "null":
                current_key = None
                expect_value = False
                continue
            if current_key not in field_probs:
                field_probs[current_key] = []
            field_probs[current_key].append(prob)
            current_key = None
            expect_value = False

    if not field_probs:
        return None

    weights = {
        "type": 0.30,
        "primary_color": 0.25,
        "pattern": 0.15,
        "material": 0.15,
        "formality": 0.15,
    }
    total_weight = 0.0
    weighted_sum = 0.0

    for field, probs in field_probs.items():
        w = weights.get(field, 0.1)
        weighted_sum += w * min(probs)
        total_weight += w

    if total_weight == 0:
        return None

    return round(weighted_sum / total_weight, 2)


class AIEndpointConfig:
    """Configuration for an AI endpoint."""

    def __init__(
        self,
        url: str,
        vision_model: str = "moondream",
        text_model: str = "phi3:mini",
        name: str = "default",
        enabled: bool = True,
    ):
        self.url = url
        self.vision_model = vision_model
        self.text_model = text_model
        self.name = name
        self.enabled = enabled


class AIService:
    """Service for AI-powered image analysis and text generation."""

    def __init__(self, endpoints: list[dict] | None = None):
        """
        Initialize AI service with optional custom endpoints.

        Args:
            endpoints: List of endpoint configs from user preferences.
                      If None or empty, uses default from settings.
        """
        self.settings = get_settings()
        self.timeout = self.settings.ai_timeout
        self.api_key = self.settings.ai_api_key

        # Build endpoint list
        self._endpoints: list[AIEndpointConfig] = []

        if endpoints:
            for ep in endpoints:
                if ep.get("enabled", True):
                    self._endpoints.append(
                        AIEndpointConfig(
                            url=ep["url"],
                            vision_model=ep.get("vision_model", "moondream"),
                            text_model=ep.get("text_model", "phi3:mini"),
                            name=ep.get("name", "custom"),
                            enabled=True,
                        )
                    )

        # Always add default endpoint as fallback (even if user has custom endpoints)
        # This ensures we can fall back to in-house Ollama if user endpoints are unreachable
        self._endpoints.append(
            AIEndpointConfig(
                url=self.settings.ai_base_url,
                vision_model=self.settings.ai_vision_model,
                text_model=self.settings.ai_text_model,
                name="default",
            )
        )

        # Legacy properties for backwards compatibility
        self.base_url = self._endpoints[0].url
        self.vision_model = self._endpoints[0].vision_model
        self.text_model = self._endpoints[0].text_model

    def _get_headers(self) -> dict:
        """Get headers for AI API requests, including auth if configured."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _preprocess_image(self, image_path: str | Path) -> str:
        """
        Preprocess image for AI analysis.
        Returns base64-encoded JPEG string.
        """
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Auto-orient based on EXIF
            img = ImageOps.exif_transpose(img)

            # Resize to max 512x512 for faster AI processing
            max_size = 512
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            # Convert to JPEG bytes
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            buffer.seek(0)

            return base64.b64encode(buffer.read()).decode("utf-8")

    def _parse_tags_from_response(self, response_text: str) -> ClothingTags:
        def extract_json(text: str) -> dict | None:
            try:
                return json.loads(text.strip())
            except json.JSONDecodeError:
                pass

            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            start_idx = text.find("{")
            if start_idx != -1:
                brace_count = 0
                for i, char in enumerate(text[start_idx:], start_idx):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = text[start_idx : i + 1]
                            try:
                                return json.loads(json_str)
                            except json.JSONDecodeError:
                                break
            return None

        COLOR_ALIASES: dict[str, str] = {
            "grey": "gray",
            "light grey": "gray",
            "light gray": "gray",
            "dark grey": "gray",
            "dark gray": "gray",
            "off-white": "cream",
            "ivory": "cream",
            "wine": "burgundy",
            "maroon": "burgundy",
            "forest green": "green",
            "dark blue": "navy",
            "royal blue": "blue",
            "sky blue": "light-blue",
            "baby blue": "light-blue",
            "camel": "tan",
            "khaki": "tan",
            "rust": "orange",
            "coral": "pink",
            "rose": "pink",
            "mauve": "purple",
            "lavender": "purple",
            "mustard": "yellow",
            "gold": "yellow",
            "silver": "gray",
            "charcoal": "gray",
        }

        def validate_value(value: str | None, valid_set: set) -> str | None:
            if value is None:
                return None
            value_lower = value.lower().strip()
            if value_lower in valid_set:
                return value_lower
            alias = COLOR_ALIASES.get(value_lower)
            if alias and alias in valid_set:
                return alias
            return None

        def validate_list(values: list, valid_set: set) -> list:
            if not values:
                return []
            return [v.lower().strip() for v in values if v and v.lower().strip() in valid_set]

        data = extract_json(response_text)
        if not data:
            logger.warning(f"Could not parse JSON from AI response: {response_text[:200]}")
            return ClothingTags(raw_response=response_text)

        if isinstance(data, list):
            data = data[0] if data and isinstance(data[0], dict) else {}

        tags = ClothingTags()
        tags.raw_response = response_text

        item_type = validate_value(data.get("type"), VALID_TYPES)
        if item_type:
            tags.type = item_type
        else:
            tags.type = "unknown"

        tags.subtype = data.get("subtype") if data.get("subtype") else None
        tags.primary_color = validate_value(data.get("primary_color"), VALID_COLORS)
        tags.colors = validate_list(data.get("colors", []), VALID_COLORS)
        tags.pattern = validate_value(data.get("pattern"), VALID_PATTERNS)
        tags.material = validate_value(data.get("material"), VALID_MATERIALS)
        tags.formality = validate_value(data.get("formality"), VALID_FORMALITY)
        tags.style = validate_list(data.get("style", []), VALID_STYLES)
        tags.season = validate_list(data.get("season", []), VALID_SEASONS)
        tags.fit = validate_value(data.get("fit"), VALID_FIT)
        tags.confidence = compute_tag_completeness(tags)

        logger.info(
            f"Parsed tags: type={tags.type}, color={tags.primary_color}, pattern={tags.pattern}"
        )
        return tags

    async def _call_with_fallback(
        self,
        messages: list,
        task_name: str,
        use_vision_model: bool = True,
        request_logprobs: bool = False,
    ) -> tuple[str | None, Exception | None, list | None]:
        last_error = None

        for endpoint in self._endpoints:
            logger.info(f"Trying AI endpoint for {task_name}: {endpoint.name}")
            model = endpoint.vision_model if use_vision_model else endpoint.text_model

            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                for attempt in range(self.settings.ai_max_retries):
                    try:
                        request_body = {
                            "model": model,
                            "messages": messages,
                            "stream": False,
                            "max_tokens": self.settings.ai_max_tokens,
                        }
                        if request_logprobs:
                            request_body["logprobs"] = True
                            request_body["top_logprobs"] = 3

                        response = await client.post(
                            f"{endpoint.url}/chat/completions",
                            headers=self._get_headers(),
                            json=request_body,
                        )
                        response.raise_for_status()

                        data = response.json()
                        choice = data["choices"][0]
                        content = choice["message"]["content"]
                        logprobs_content = None
                        if request_logprobs:
                            lp = choice.get("logprobs")
                            if lp:
                                logprobs_content = lp.get("content")

                        used_model = data.get("model", model)
                        logger.info(
                            f"AI {task_name} successful via {endpoint.name} (model: {used_model})"
                        )
                        return content, None, logprobs_content

                    except httpx.HTTPStatusError as e:
                        last_error = e
                        logger.warning(f"HTTP error from {endpoint.name}: {e}")
                        if attempt < self.settings.ai_max_retries - 1:
                            continue
                    except httpx.RequestError as e:
                        last_error = e
                        logger.warning(f"Request error from {endpoint.name}: {e}")
                        if attempt < self.settings.ai_max_retries - 1:
                            continue

        return None, last_error, None

    async def analyze_image(self, image_path: str | Path) -> ClothingTags:
        image_base64 = self._preprocess_image(image_path)

        # System/user separation for injection protection
        messages_tags = [
            {"role": "system", "content": TAGGING_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            },
        ]

        messages_desc = [
            {"role": "system", "content": DESCRIPTION_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            },
        ]

        tags = ClothingTags()
        last_error = None

        # First pass: structured tags with logprobs for real confidence
        content, err, logprobs_content = await self._call_with_fallback(
            messages_tags, "tags", request_logprobs=True
        )
        if content:
            tags = self._parse_tags_from_response(content)
            logprobs_confidence = compute_confidence_from_logprobs(logprobs_content)
            if logprobs_confidence is not None:
                tags.logprobs_confidence = logprobs_confidence
        if err:
            last_error = err

        # Second pass: human-readable description
        content, err, _ = await self._call_with_fallback(messages_desc, "description")
        if content:
            description = content.strip()
            if description.startswith('"') and description.endswith('"'):
                description = description[1:-1]
            tags.description = description

        if tags.type == "unknown" and not tags.description and last_error:
            raise last_error

        return tags

    async def check_health(self) -> dict:
        """Check health of all configured AI endpoints."""
        endpoints_health = []

        for endpoint in self._endpoints:
            try:
                async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                    # Try OpenAI-compatible /v1/models endpoint first
                    response = await client.get(
                        f"{endpoint.url}/models", headers=self._get_headers()
                    )
                    if response.status_code == 200:
                        data = response.json()
                        # OpenAI format: {"data": [{"id": "model-name", ...}]}
                        models = data.get("data", [])
                        model_names = [m.get("id", "") for m in models]
                        endpoints_health.append(
                            {
                                "name": endpoint.name,
                                "url": endpoint.url,
                                "status": "healthy",
                                "vision_model": endpoint.vision_model,
                                "text_model": endpoint.text_model,
                                "available_models": model_names,
                            }
                        )
                        continue

                    # Fallback: Try Ollama-specific endpoint
                    response = await client.get(endpoint.url.replace("/v1", "/api/tags"))
                    if response.status_code == 200:
                        models = response.json().get("models", [])
                        model_names = [m.get("name", "") for m in models]
                        endpoints_health.append(
                            {
                                "name": endpoint.name,
                                "url": endpoint.url,
                                "status": "healthy",
                                "vision_model": endpoint.vision_model,
                                "text_model": endpoint.text_model,
                                "available_models": model_names,
                            }
                        )
                    else:
                        endpoints_health.append(
                            {
                                "name": endpoint.name,
                                "url": endpoint.url,
                                "status": "unhealthy",
                                "error": f"HTTP {response.status_code}",
                            }
                        )
            except Exception as e:
                endpoints_health.append(
                    {
                        "name": endpoint.name,
                        "url": endpoint.url,
                        "status": "unhealthy",
                        "error": str(e),
                    }
                )

        # Overall status is healthy if at least one endpoint is healthy
        any_healthy = any(ep["status"] == "healthy" for ep in endpoints_health)
        return {
            "status": "healthy" if any_healthy else "unhealthy",
            "endpoints": endpoints_health,
        }

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        return_metadata: bool = False,
    ) -> str | TextGenerationResult:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None

        for endpoint in self._endpoints:
            logger.info(f"Trying text generation via {endpoint.name}")

            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                for attempt in range(self.settings.ai_max_retries):
                    try:
                        response = await client.post(
                            f"{endpoint.url}/chat/completions",
                            headers=self._get_headers(),
                            json={
                                "model": endpoint.text_model,
                                "messages": messages,
                                "stream": False,
                                "temperature": 0.4,
                                "max_tokens": self.settings.ai_max_tokens,
                            },
                        )
                        response.raise_for_status()

                        data = response.json()
                        used_model = data.get("model", endpoint.text_model)
                        content = data["choices"][0]["message"]["content"]
                        logger.info(
                            f"Text generation successful via {endpoint.name} (model: {used_model})"
                        )

                        if return_metadata:
                            return TextGenerationResult(
                                content=content,
                                model=used_model,
                                endpoint=endpoint.name,
                            )
                        return content

                    except httpx.HTTPStatusError as e:
                        last_error = e
                        logger.warning(f"HTTP error from {endpoint.name}: {e}")
                        if attempt < self.settings.ai_max_retries - 1:
                            continue
                    except httpx.RequestError as e:
                        last_error = e
                        logger.warning(f"Request error from {endpoint.name}: {e}")
                        if attempt < self.settings.ai_max_retries - 1:
                            continue

        if last_error:
            raise last_error
        raise RuntimeError("Failed to generate text - no endpoints available")


# Singleton instance
_ai_service: AIService | None = None


def get_ai_service() -> AIService:
    """Get or create AI service instance."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
