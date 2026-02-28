import base64
import io
import json
import re
from pathlib import Path

import httpx
from PIL import Image, ImageOps
from pydantic import BaseModel

from app.config import get_settings
from app.utils.prompts import load_prompt


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
    description: str | None = None  # Human-readable description
    raw_response: str | None = None  # Store the raw AI response


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
        """
        Parse clothing tags from AI response.
        Only accepts structured JSON. Validates against allowed values.
        Returns empty/null fields rather than guessing.
        """
        import logging

        logger = logging.getLogger(__name__)

        def extract_json(text: str) -> dict | None:
            """Extract JSON from text, handling markdown and comments."""
            # Try direct parse
            try:
                return json.loads(text.strip())
            except json.JSONDecodeError:
                pass

            # Try extracting from markdown code block
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            # Try finding JSON object with balanced braces
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

        def validate_value(value: str | None, valid_set: set) -> str | None:
            """Validate a value against allowed set. Return None if invalid."""
            if value is None:
                return None
            value_lower = value.lower().strip()
            if value_lower in valid_set:
                return value_lower
            # Check for close matches (e.g., "grey" -> "gray")
            if value_lower == "grey":
                return "gray"
            return None

        def validate_list(values: list, valid_set: set) -> list:
            """Validate a list of values, keeping only valid ones."""
            if not values:
                return []
            return [v.lower().strip() for v in values if v and v.lower().strip() in valid_set]

        # Try to extract JSON
        data = extract_json(response_text)
        if not data:
            logger.warning(f"Could not parse JSON from AI response: {response_text[:200]}")
            return ClothingTags(raw_response=response_text)

        # Build tags with strict validation
        tags = ClothingTags()
        tags.raw_response = response_text

        # Type (required)
        item_type = validate_value(data.get("type"), VALID_TYPES)
        if item_type:
            tags.type = item_type
        else:
            tags.type = "unknown"

        # Subtype (optional, less strict)
        tags.subtype = data.get("subtype") if data.get("subtype") else None

        # Colors - validate each
        tags.primary_color = validate_value(data.get("primary_color"), VALID_COLORS)
        tags.colors = validate_list(data.get("colors", []), VALID_COLORS)

        # Pattern
        tags.pattern = validate_value(data.get("pattern"), VALID_PATTERNS)

        # Material
        tags.material = validate_value(data.get("material"), VALID_MATERIALS)

        # Formality
        tags.formality = validate_value(data.get("formality"), VALID_FORMALITY)

        # Style (less strict - accept common style terms)
        valid_styles = {
            "casual",
            "formal",
            "sporty",
            "minimalist",
            "bohemian",
            "preppy",
            "streetwear",
            "classic",
            "elegant",
            "athletic",
            "vintage",
            "modern",
        }
        tags.style = validate_list(data.get("style", []), valid_styles)

        # Season
        valid_seasons = {"spring", "summer", "fall", "winter", "all-season"}
        tags.season = validate_list(data.get("season", []), valid_seasons)

        # Confidence
        confidence = data.get("confidence", 0.5)
        if isinstance(confidence, (int, float)) and 0 <= confidence <= 1:
            tags.confidence = float(confidence)
        else:
            tags.confidence = 0.5

        logger.info(
            f"Parsed tags: type={tags.type}, color={tags.primary_color}, pattern={tags.pattern}"
        )
        return tags

    async def _call_with_fallback(
        self,
        messages: list,
        task_name: str,
        use_vision_model: bool = True,
    ) -> tuple[str | None, Exception | None]:
        """
        Call AI endpoint with retry and fallback logic.

        Args:
            messages: The messages to send to the AI
            task_name: Name for logging (e.g., "tags", "description")
            use_vision_model: Whether to use vision model (True) or text model (False)

        Returns:
            Tuple of (response_content, last_error)
        """
        import logging

        logger = logging.getLogger(__name__)

        last_error = None

        for endpoint in self._endpoints:
            logger.info(f"Trying AI endpoint for {task_name}: {endpoint.name}")
            model = endpoint.vision_model if use_vision_model else endpoint.text_model

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for attempt in range(self.settings.ai_max_retries):
                    try:
                        response = await client.post(
                            f"{endpoint.url}/chat/completions",
                            headers=self._get_headers(),
                            json={
                                "model": model,
                                "messages": messages,
                                "stream": False,
                            },
                        )
                        response.raise_for_status()

                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        # Log model from response if available, fallback to configured model
                        used_model = data.get("model", model)
                        logger.info(
                            f"AI {task_name} successful via {endpoint.name} (model: {used_model})"
                        )
                        return content, None

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

        return None, last_error

    async def analyze_image(self, image_path: str | Path) -> ClothingTags:
        """
        Analyze a clothing image and return structured tags.
        Uses two-pass approach:
        1. First pass: Get structured JSON tags
        2. Second pass: Get human-readable description
        """
        # Preprocess image
        image_base64 = self._preprocess_image(image_path)

        # Build request for structured tags
        messages_tags = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": TAGGING_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            }
        ]

        # Build request for description
        messages_desc = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": DESCRIPTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            }
        ]

        tags = ClothingTags()
        last_error = None

        # First pass: Get structured tags
        content, err = await self._call_with_fallback(messages_tags, "tags")
        if content:
            tags = self._parse_tags_from_response(content)
        if err:
            last_error = err

        # Second pass: Get description
        content, err = await self._call_with_fallback(messages_desc, "description")
        if content:
            description = content.strip()
            # Clean up description - remove quotes if wrapped
            if description.startswith('"') and description.endswith('"'):
                description = description[1:-1]
            tags.description = description

        # If we got no tags at all, raise the error
        if tags.type == "unknown" and not tags.description and last_error:
            raise last_error

        return tags

    async def check_health(self) -> dict:
        """Check health of all configured AI endpoints."""
        endpoints_health = []

        for endpoint in self._endpoints:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
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
        """
        Generate text completion (for recommendations, etc.).
        Tries each configured endpoint in order until one succeeds.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            return_metadata: If True, returns TextGenerationResult with model info

        Returns:
            Generated text response (str) or TextGenerationResult if return_metadata=True
        """
        import logging

        logger = logging.getLogger(__name__)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        last_error = None

        # Try each endpoint in order
        for endpoint in self._endpoints:
            logger.info(f"Trying text generation via {endpoint.name}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
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
                            },
                        )
                        response.raise_for_status()

                        data = response.json()
                        # Get model from response if available, fallback to configured model
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

        # All endpoints failed
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
