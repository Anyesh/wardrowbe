import json
from pathlib import Path

_VOCABULARY_PATH = Path(__file__).parent.parent / "data" / "garment_vocabulary.json"
_DATA = json.loads(_VOCABULARY_PATH.read_text())

TYPES: tuple[str, ...] = tuple(entry["value"] for entry in _DATA["types"])
ITEM_ROLE: dict[str, str] = {entry["value"]: entry["role"] for entry in _DATA["types"]}
DEFAULT_WASH_INTERVALS: dict[str, int] = {
    entry["value"]: entry["wash_interval"] for entry in _DATA["types"]
}
MATERIALS: tuple[str, ...] = tuple(_DATA["materials"])
# Ordered from least to most formal; the scorer measures distance along this scale.
FORMALITY: tuple[str, ...] = tuple(_DATA["formality"])
OCCASIONS: tuple[str, ...] = tuple(entry["value"] for entry in _DATA["occasions"])
OCCASION_FORMALITY: dict[str, tuple[str, ...]] = {
    entry["value"]: tuple(entry["formality"])
    for entry in _DATA["occasions"]
    if "formality" in entry
}
COLORS: tuple[str, ...] = tuple(entry["value"] for entry in _DATA["colors"])
COLOR_ALIASES: dict[str, str] = dict(_DATA["color_aliases"])


def normalize_color(name: str) -> str | None:
    key = name.strip().lower()
    if key in COLORS:
        return key
    return COLOR_ALIASES.get(key)


def render_tagging_prompt(template: str) -> str:
    return (
        template.replace("<<TYPES>>", ", ".join(TYPES))
        .replace("<<MATERIALS>>", ", ".join(MATERIALS))
        .replace("<<FORMALITY>>", ", ".join(FORMALITY))
        .replace("<<COLORS>>", ", ".join(COLORS))
    )
