"""Which of the user's own clothes appear in a photo of them: the vision model gets the photo
and a numbered list of the wardrobe and answers with numbers, which keeps it from inventing
items (an answer can only point at a line of the list)."""

import asyncio
import json
import re
from pathlib import Path

from app.models.item import ClothingItem
from app.services.ai_service import AIService

MAX_CANDIDATES = 150

SELFIE_PROMPT = """You are shown a photo of a person and a numbered list of clothes they own.
Decide which of the listed clothes the person is wearing in the photo.
Answer with JSON only, in exactly this form: {"matches": [3, 7]}
- Use only numbers from the list.
- Include a garment only when you can see it in the photo; leave out anything unsure.
- At most one garment per body area (one pair of trousers, one pair of shoes, and so on).
- If none of the listed clothes is visible, answer {"matches": []}."""


def describe(item: ClothingItem) -> str:
    parts = [item.name, item.primary_color, item.pattern, item.material, item.type]
    text = " ".join(p for p in parts if p)
    if item.ai_description:
        text += f" - {item.ai_description[:90]}"
    return text


def parse_matches(content: str, count: int) -> list[int]:
    """Zero-based indexes of the listed items the answer names, in order, without repeats."""
    numbers: list[object] = []
    match = re.search(r"\{.*\}", content, re.S)
    if match:
        try:
            numbers = json.loads(match.group(0)).get("matches", [])
        except (ValueError, AttributeError):
            numbers = []
    if not numbers:
        numbers = re.findall(r"\d+", content)
    seen: list[int] = []
    for number in numbers:
        try:
            index = int(number) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= index < count and index not in seen:
            seen.append(index)
    return seen


async def match_selfie(ai: AIService, photo: Path, items: list[ClothingItem]) -> list[ClothingItem]:
    candidates = items[:MAX_CANDIDATES]
    if not candidates:
        return []
    listing = "\n".join(f"{n}. {describe(item)}" for n, item in enumerate(candidates, start=1))
    image_base64 = await asyncio.to_thread(ai._preprocess_image, photo)
    messages = [
        {"role": "system", "content": SELFIE_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Clothes:\n{listing}"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                },
            ],
        },
    ]
    content, error, _ = await ai._call_with_fallback(messages, "selfie")
    if content is None:
        raise error or RuntimeError("The AI did not answer")
    return [candidates[i] for i in parse_matches(content, len(candidates))]
