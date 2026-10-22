"""Reads the vision model's answer to "which garments are in this photo, and where".

The model's boxes are approximate and its JSON is not always tidy, so everything here is about
turning an answer into a short list of sane boxes: inside the photo, not tiny, not stacked on
top of each other. Nothing here touches the network or the database.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from app.utils.garment_vocabulary import TYPES, normalize_color

logger = logging.getLogger(__name__)

MAX_GARMENTS = 8
# A box narrower or shorter than this share of the photo is a speck, not a garment.
MIN_BOX_SIDE = 0.05
# Two boxes overlapping more than this (intersection over union) are the same garment twice.
DUPLICATE_IOU = 0.7

_VALID_TYPES = frozenset(TYPES)


@dataclass(frozen=True)
class DetectedGarment:
    """One garment with its box as fractions (0-1) of the photo's width and height."""

    type: str
    colors: list[str] = field(default_factory=list)
    left: float = 0.0
    top: float = 0.0
    width: float = 0.0
    height: float = 0.0


def _extract_json(text: str) -> object | None:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if number == number and abs(number) != float("inf") else None


def _box_edges(raw: object) -> tuple[float, float, float, float] | None:
    """(left, top, right, bottom) from either a {left, top, right, bottom} object or a list."""
    if isinstance(raw, dict):
        values = [_number(raw.get(k)) for k in ("left", "top", "right", "bottom")]
    elif isinstance(raw, list) and len(raw) == 4:
        values = [_number(v) for v in raw]
    else:
        return None
    if any(v is None for v in values):
        return None
    return values[0], values[1], values[2], values[3]  # type: ignore[return-value]


def _iou(a: DetectedGarment, b: DetectedGarment) -> float:
    inter_w = min(a.left + a.width, b.left + b.width) - max(a.left, b.left)
    inter_h = min(a.top + a.height, b.top + b.height) - max(a.top, b.top)
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    inter = inter_w * inter_h
    return inter / (a.width * a.height + b.width * b.height - inter)


def parse_detection(response_text: str) -> list[DetectedGarment]:
    """Turn the model's reply into clean garments; an unusable reply gives an empty list."""
    data = _extract_json(response_text)
    entries = data.get("garments") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        if response_text.strip():
            logger.warning(f"Could not read garments from AI response: {response_text[:200]}")
        return []

    parsed: list[tuple[str, list[str], tuple[float, float, float, float]]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        edges = _box_edges(entry.get("box"))
        if edges is None:
            continue
        raw_type = entry.get("type")
        garment_type = (
            raw_type.lower().strip()
            if isinstance(raw_type, str) and raw_type.lower().strip() in _VALID_TYPES
            else "unknown"
        )
        raw_colors = entry.get("colors")
        colors = (
            list(
                dict.fromkeys(
                    c for c in (normalize_color(v) for v in raw_colors if isinstance(v, str)) if c
                )
            )
            if isinstance(raw_colors, list)
            else []
        )
        parsed.append((garment_type, colors, edges))

    # The prompt asks for percentages, but a model may answer in 0-1 fractions; a box that is
    # really under 1% of the photo is not a garment, so "everything is at most 1" means fractions.
    scale = 1.0 if parsed and max(max(e) for _, _, e in parsed) <= 1.0 else 100.0

    garments: list[DetectedGarment] = []
    for garment_type, colors, (left, top, right, bottom) in parsed:
        left, right = sorted((left / scale, right / scale))
        top, bottom = sorted((top / scale, bottom / scale))
        left, right = max(left, 0.0), min(right, 1.0)
        top, bottom = max(top, 0.0), min(bottom, 1.0)
        width, height = right - left, bottom - top
        if width < MIN_BOX_SIDE or height < MIN_BOX_SIDE:
            continue
        candidate = DetectedGarment(garment_type, colors, left, top, width, height)
        if any(_iou(candidate, kept) > DUPLICATE_IOU for kept in garments):
            continue
        garments.append(candidate)
        if len(garments) == MAX_GARMENTS:
            break
    return garments
