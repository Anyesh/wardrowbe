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
# Per axis, coordinates up to FRACTION_LIMIT read as 0-1 fractions, up to PERCENT_LIMIT as
# percentages and anything larger as 0-1000.
FRACTION_LIMIT = 2.0
PERCENT_LIMIT = 150.0
BOX_2D_SCALE = 1000.0

_VALID_TYPES = frozenset(TYPES)
_JSON_OPENER = re.compile(r"[\[{]")

DETECTION_EXAMPLE = {
    "garments": [
        {
            "type": "shirt",
            "colors": ["blue"],
            "box": {"left": 5, "top": 8, "right": 48, "bottom": 60},
        }
    ]
}


@dataclass(frozen=True)
class DetectedGarment:
    """One garment with its box as fractions (0-1) of the photo's width and height."""

    type: str
    colors: list[str] = field(default_factory=list)
    left: float = 0.0
    top: float = 0.0
    width: float = 0.0
    height: float = 0.0


def _json_values(text: str) -> list[object]:
    try:
        return [json.loads(text.strip())]
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    values: list[object] = []
    position = 0
    while match := _JSON_OPENER.search(text, position):
        try:
            value, position = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            position = match.start() + 1
            continue
        values.append(value)
    return values


def _garment_entries(value: object) -> list | None:
    if isinstance(value, dict) and isinstance(value.get("garments"), list):
        return value["garments"]
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        return value
    return None


def _extract_entries(text: str) -> list | None:
    """The last non-empty answer in the reply, else an empty one; echoed examples never count."""
    answers = [
        entries
        for value in _json_values(text)
        if value != DETECTION_EXAMPLE and (entries := _garment_entries(value)) is not None
    ]
    non_empty = [entries for entries in answers if entries]
    if non_empty:
        return non_empty[-1]
    return answers[-1] if answers else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if number == number and abs(number) != float("inf") else None


def _edges(values: list[float | None]) -> tuple[float, float, float, float] | None:
    if any(v is None for v in values):
        return None
    return values[0], values[1], values[2], values[3]  # type: ignore[return-value]


def _box_edges(raw: object) -> tuple[float, float, float, float] | None:
    """(left, top, right, bottom) from either a {left, top, right, bottom} object or a list."""
    if isinstance(raw, dict):
        return _edges([_number(raw.get(k)) for k in ("left", "top", "right", "bottom")])
    if isinstance(raw, list) and len(raw) == 4:
        return _edges([_number(v) for v in raw])
    return None


def _box_2d_fractions(raw: object) -> tuple[float, float, float, float] | None:
    """Fraction edges from a Gemma/Gemini `box_2d`: [ymin, xmin, ymax, xmax] on a 0-1000 scale."""
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    edges = _edges([_number(v) for v in raw])
    if edges is None:
        return None
    ymin, xmin, ymax, xmax = (v / BOX_2D_SCALE for v in edges)
    return xmin, ymin, xmax, ymax


def _axis_scale(values: list[float]) -> float:
    largest = max(values, default=0.0)
    if largest <= FRACTION_LIMIT:
        return 1.0
    return 100.0 if largest <= PERCENT_LIMIT else 1000.0


def _iou(a: DetectedGarment, b: DetectedGarment) -> float:
    inter_w = min(a.left + a.width, b.left + b.width) - max(a.left, b.left)
    inter_h = min(a.top + a.height, b.top + b.height) - max(a.top, b.top)
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    inter = inter_w * inter_h
    return inter / (a.width * a.height + b.width * b.height - inter)


def parse_detection(response_text: str) -> list[DetectedGarment]:
    """Turn the model's reply into clean garments; an unusable reply gives an empty list."""
    entries = _extract_entries(response_text)
    if entries is None:
        if response_text.strip():
            logger.warning(f"Could not read garments from AI response: {response_text[:200]}")
        return []

    parsed: list[tuple[str, list[str], tuple[float, float, float, float], bool]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        edges = _box_edges(entry.get("box"))
        is_fraction = False
        if edges is None:
            edges = _box_2d_fractions(entry.get("box_2d"))
            is_fraction = True
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
        parsed.append((garment_type, colors, edges, is_fraction))

    # Each axis gets its own scale, since a model has answered 0-1000 x with percentage y in one
    # box. A fraction box can overflow an edge a little (right: 1.03), hence a fraction limit of 2.
    scaled = [edges for _, _, edges, is_fraction in parsed if not is_fraction]
    x_scale = _axis_scale([v for left, _, right, _ in scaled for v in (left, right)])
    y_scale = _axis_scale([v for _, top, _, bottom in scaled for v in (top, bottom)])

    garments: list[DetectedGarment] = []
    for garment_type, colors, (left, top, right, bottom), is_fraction in parsed:
        x, y = (1.0, 1.0) if is_fraction else (x_scale, y_scale)
        left, right = sorted((left / x, right / x))
        top, bottom = sorted((top / y, bottom / y))
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
