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


# Zero-width space, word joiner and BOM are dropped so that a name made only of them reads as blank
# rather than as an invisible colour; ZWJ and ZWNJ stay because they shape scripts and emoji.
_ZERO_WIDTH = re.compile("[\u200b\u2060\ufeff]")

# Unicode White_Space spelled out rather than \s, because migrations 952169051179 and 6c1e8f2a9d47
# and frontend/lib/colors.ts use this same class and must agree on tabs, NBSP and ideographic spaces.
_WHITESPACE_RUN = re.compile(
    r"[\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+"
)


def _color_key(name: str) -> str:
    return _WHITESPACE_RUN.sub(" ", _ZERO_WIDTH.sub("", name)).strip(" ").lower()


# "Light Blue" from a free-text client or an old row means the stored "light-blue", so a name is
# also tried with its spaces turned into hyphens.
def normalize_color(name: str) -> str | None:
    key = _color_key(name)
    for candidate in (key, key.replace(" ", "-")):
        if candidate in COLORS:
            return candidate
        if candidate in COLOR_ALIASES:
            return COLOR_ALIASES[candidate]
    return None


# Unlike normalize_color, unknown names pass through (whitespace-collapsed and lowercased) so that
# API clients sending colours outside the vocabulary keep working.
def canonical_color(name: str) -> str:
    key = _color_key(name)
    return normalize_color(key) or key


def canonical_primary_color(name: str) -> str | None:
    return canonical_color(name) or None


def canonical_colors(names: list[str]) -> list[str]:
    return list(dict.fromkeys(c for c in map(canonical_color, names) if c))


def render_tagging_prompt(template: str) -> str:
    return (
        template.replace("<<TYPES>>", ", ".join(TYPES))
        .replace("<<MATERIALS>>", ", ".join(MATERIALS))
        .replace("<<FORMALITY>>", ", ".join(FORMALITY))
        .replace("<<COLORS>>", ", ".join(COLORS))
    )
