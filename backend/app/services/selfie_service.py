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


# An answer that is only a list of numbers ("3, 7" or "matches: [3, 7]"), the one shape read
# without JSON; prose with numbers in it ("it is 2 pm, I see 1 shirt") is not.
BARE_LIST = re.compile(r"^\s*(?:matches\s*:)?\s*\[?\s*\d+(?:\s*,\s*\d+)*\s*\]?\s*\.?\s*$", re.I)


def _as_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def parse_matches(content: str, count: int) -> list[int]:
    """Zero-based indexes of the listed items the answer names, in order, without repeats."""
    numbers: list[object] | None = None
    match = re.search(r"\{.*\}", content, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
        except ValueError:
            data = None
        if isinstance(data, dict) and "matches" in data:
            # A JSON answer is final, even an empty one: no digging numbers out of the prose.
            numbers = data["matches"] if isinstance(data["matches"], list) else []
    if numbers is None:
        numbers = re.findall(r"\d+", content) if BARE_LIST.match(content) else []
    seen: list[int] = []
    for value in numbers:
        number = _as_number(value)
        if number is None:
            continue
        index = number - 1
        if 0 <= index < count and index not in seen:
            seen.append(index)
    return seen


def candidates_for(items: list[ClothingItem]) -> list[ClothingItem]:
    """The items the model is shown, most recently worn first (the caller orders them)."""
    return items[:MAX_CANDIDATES]


async def match_selfie(ai: AIService, photo: Path, items: list[ClothingItem]) -> list[ClothingItem]:
    candidates = candidates_for(items)
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
