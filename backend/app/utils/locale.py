import json
from pathlib import Path

_LOCALES_PATH = Path(__file__).parent.parent / "data" / "locales.json"
_DATA = json.loads(_LOCALES_PATH.read_text())

DEFAULT_LOCALE: str = _DATA["default"]

# Order is the order the UI language picker renders; keep it stable.
SUPPORTED_LOCALES: tuple[str, ...] = tuple(_DATA["supported"])

_SUPPORTED_LOCALE_SET = frozenset(SUPPORTED_LOCALES)

LANGUAGE_NAMES = {
    "en": "English",
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "ko": "Korean",
    "ja": "Japanese",
    "fr": "French",
    "de": "German",
    "it": "Italian",
}


def is_supported_locale(value: object) -> bool:
    return isinstance(value, str) and value in _SUPPORTED_LOCALE_SET


def language_name(locale: str | None) -> str:
    return LANGUAGE_NAMES.get(locale or "", LANGUAGE_NAMES[DEFAULT_LOCALE])
