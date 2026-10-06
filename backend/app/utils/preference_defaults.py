import json
from pathlib import Path

_DEFAULTS_PATH = Path(__file__).parent.parent / "data" / "preference_defaults.json"
_DATA = json.loads(_DEFAULTS_PATH.read_text())

DEFAULT_OCCASION: str = _DATA["default_occasion"]
DEFAULT_TEMPERATURE_UNIT: str = _DATA["temperature_unit"]
DEFAULT_TEMPERATURE_SENSITIVITY: str = _DATA["temperature_sensitivity"]
DEFAULT_LAYERING_PREFERENCE: str = _DATA["layering_preference"]
DEFAULT_VARIETY_LEVEL: str = _DATA["variety_level"]
DEFAULT_PREFER_UNDERUSED_ITEMS: bool = _DATA["prefer_underused_items"]
