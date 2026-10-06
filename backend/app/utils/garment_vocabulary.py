import json
import re
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
    entry["value"]: tuple(entry["formality"]) for entry in _DATA["occasions"]
}
COLORS: tuple[str, ...] = tuple(entry["value"] for entry in _DATA["colors"])
COLOR_ALIASES: dict[str, str] = dict(_DATA["color_aliases"])


# "Light Blue" from a free-text client or an old row means the stored "light-blue", so a name is
# also tried with its inner whitespace collapsed to one hyphen.
def normalize_color(name: str) -> str | None:
    key = name.strip().lower()
    for candidate in (key, re.sub(r"\s+", "-", key)):
        if candidate in COLORS:
            return candidate
        if candidate in COLOR_ALIASES:
            return COLOR_ALIASES[candidate]
    return None


# Unlike normalize_color, unknown names pass through (lowercased) so that API
# clients sending colours outside the vocabulary keep working.
def canonical_color(name: str) -> str:
    key = name.strip().lower()
    return normalize_color(key) or key


def canonical_colors(names: list[str]) -> list[str]:
    return list(dict.fromkeys(c for c in map(canonical_color, names) if c))


def render_tagging_prompt(template: str) -> str:
    return (
        template.replace("<<TYPES>>", ", ".join(TYPES))
        .replace("<<MATERIALS>>", ", ".join(MATERIALS))
        .replace("<<FORMALITY>>", ", ".join(FORMALITY))
        .replace("<<COLORS>>", ", ".join(COLORS))
    )
