import json
from pathlib import Path

_SCALES_PATH = Path(__file__).parent.parent / "data" / "scales.json"
_DATA = json.loads(_SCALES_PATH.read_text())

RATING_MIN: int = _DATA["rating"]["min"]
RATING_MAX: int = _DATA["rating"]["max"]
_RATING_MIDPOINT = (RATING_MIN + RATING_MAX) / 2
_RATING_HALF_SPAN = (RATING_MAX - RATING_MIN) / 2

_COLD = _DATA["temperature_thresholds_celsius"]["cold"]
_HOT = _DATA["temperature_thresholds_celsius"]["hot"]
COLD_THRESHOLD_MIN: int = _COLD["min"]
COLD_THRESHOLD_MAX: int = _COLD["max"]
DEFAULT_COLD_THRESHOLD: int = _COLD["default"]
HOT_THRESHOLD_MIN: int = _HOT["min"]
HOT_THRESHOLD_MAX: int = _HOT["max"]
DEFAULT_HOT_THRESHOLD: int = _HOT["default"]

_AVOID_REPEAT = _DATA["avoid_repeat_days"]
AVOID_REPEAT_DAYS_MIN: int = _AVOID_REPEAT["min"]
AVOID_REPEAT_DAYS_MAX: int = _AVOID_REPEAT["max"]
DEFAULT_AVOID_REPEAT_DAYS: int = _AVOID_REPEAT["default"]

_STYLE_SCORE = _DATA["style_score"]
STYLE_SCORE_MIN: int = _STYLE_SCORE["min"]
STYLE_SCORE_MAX: int = _STYLE_SCORE["max"]
DEFAULT_STYLE_SCORE: int = _STYLE_SCORE["default"]


def rating_to_unit(rating: float) -> float:
    return (rating - RATING_MIN) / (RATING_MAX - RATING_MIN)


def rating_to_signed(rating: float) -> float:
    return (rating - _RATING_MIDPOINT) / _RATING_HALF_SPAN
