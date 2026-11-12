"""Image generation for outfit try-on, through an OpenAI-compatible chat completions endpoint.

Uses the OpenRouter image-generation request shape (`modalities` plus an `images` array on the
returned message). Every call costs money, so nothing here retries. Provider response bodies
and any text they carry are never logged: they can echo the prompt or the user's photo.
"""

import base64
import binascii
import json
import logging
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.utils.prompts import load_prompt

logger = logging.getLogger(__name__)

# Bump when the prompt or the garment data sent with it changes, so cached try-ons turn stale.
PROMPT_VERSION = "1"

ERROR_NO_IMAGE = "TRY_ON_NO_IMAGE"
ERROR_FAILED = "TRY_ON_FAILED"

DATA_URL_PREFIXES = {
    "data:image/png;base64,": ".png",
    "data:image/jpeg;base64,": ".jpg",
    "data:image/webp;base64,": ".webp",
}


class TryOnGenerationError(Exception):
    def __init__(self, error_code: str):
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    extension: str


@dataclass(frozen=True)
class Garment:
    """One outfit item as sent to the model."""

    type: str
    subtype: str | None
    colors: list[str]
    primary_color: str | None
    layer: str | None


def garment_record(garment: Garment) -> dict:
    record: dict = {
        "type": garment.type,
        "subtype": garment.subtype,
        "colors": list(garment.colors),
        "primary_color": garment.primary_color,
    }
    if garment.layer:
        record["layer"] = garment.layer
    return record


def _escaped_json(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def build_prompt(garments: list[Garment]) -> str:
    present_slots = sorted({g.type for g in garments})
    return (
        f"{load_prompt('outfit_try_on')}\n\n"
        f"<present_slots>\n{_escaped_json(present_slots)}\n</present_slots>\n\n"
        f"<garment_data>\n{_escaped_json([garment_record(g) for g in garments])}\n</garment_data>"
    )


def _data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def parse_generated_image(payload: object) -> GeneratedImage:
    """Pick the first usable image out of a chat completion response."""
    try:
        images = payload["choices"][0]["message"]["images"]  # type: ignore[index]
        urls = [image["image_url"]["url"] for image in images]
    except (KeyError, IndexError, TypeError):
        raise TryOnGenerationError(ERROR_NO_IMAGE) from None

    for url in urls:
        if not isinstance(url, str):
            continue
        for prefix, extension in DATA_URL_PREFIXES.items():
            if url.startswith(prefix):
                try:
                    data = base64.b64decode(url[len(prefix) :], validate=True)
                except (binascii.Error, ValueError):
                    break
                if data:
                    return GeneratedImage(data=data, extension=extension)
                break
    raise TryOnGenerationError(ERROR_NO_IMAGE)


async def generate_try_on_image(
    person_jpeg: bytes, garment_jpegs: list[bytes], garments: list[Garment]
) -> GeneratedImage:
    settings = get_settings()
    content: list[dict] = [{"type": "text", "text": build_prompt(garments)}]
    content.append({"type": "image_url", "image_url": {"url": _data_url(person_jpeg)}})
    for jpeg in garment_jpegs:
        content.append({"type": "image_url", "image_url": {"url": _data_url(jpeg)}})

    body = {
        "model": settings.ai_image_model,
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "Authorization": f"Bearer {settings.ai_image_api_key}",
        "Content-Type": "application/json",
    }
    url = f"{settings.ai_image_base_url.rstrip('/')}/chat/completions"

    try:
        async with httpx.AsyncClient(
            timeout=settings.ai_image_timeout, follow_redirects=True
        ) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as e:
        logger.warning("Try-on generation failed: HTTP %s", e.response.status_code)
        raise TryOnGenerationError(ERROR_FAILED) from None
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Try-on generation failed: %s", type(e).__name__)
        raise TryOnGenerationError(ERROR_FAILED) from None

    return parse_generated_image(payload)
