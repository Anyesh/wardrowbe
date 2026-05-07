from __future__ import annotations

from app.schemas.onboarding import StyleQuizAnswers

STYLE_KEYS = ("casual", "formal", "sporty", "minimalist", "bold")


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _base_style_profile() -> dict[str, int]:
    return {key: 50 for key in STYLE_KEYS}


def map_style_quiz_answers(answers: StyleQuizAnswers | dict) -> dict:
    payload = answers.model_dump() if hasattr(answers, "model_dump") else dict(answers)

    style_profile = _base_style_profile()
    style_focus = payload.get("style_focus", "casual")
    if style_focus in style_profile:
        style_profile[style_focus] += 25

    occasion_style_boosts = {
        "office": {"formal": 10, "minimalist": 8},
        "formal": {"formal": 12},
        "sporty": {"sporty": 12},
        "date": {"bold": 8, "casual": 6},
        "outdoor": {"sporty": 8, "casual": 6},
        "casual": {"casual": 10},
    }

    for key, boost in occasion_style_boosts.get(payload.get("primary_occasion", "casual"), {}).items():
        style_profile[key] = _clamp(style_profile[key] + boost)

    color_palette_map = {
        "neutral": ["black", "white", "gray", "navy"],
        "low_saturation": ["beige", "olive", "brown"],
        "bright": ["red", "yellow", "blue"],
    }
    color_favorites = color_palette_map.get(payload.get("color_palette"), ["black", "white"])

    temperature_feel = payload.get("temperature_feel", "normal")
    if temperature_feel == "cold":
        temperature_sensitivity = "high"
        layering_preference = "heavy"
    elif temperature_feel == "hot":
        temperature_sensitivity = "low"
        layering_preference = "minimal"
    else:
        temperature_sensitivity = "normal"
        layering_preference = "moderate"

    for key in STYLE_KEYS:
        style_profile[key] = _clamp(style_profile[key])

    return {
        "default_occasion": payload.get("primary_occasion", "casual"),
        "style_profile": style_profile,
        "color_favorites": color_favorites,
        "color_avoid": list(dict.fromkeys(payload.get("avoid_colors", []))),
        "temperature_sensitivity": temperature_sensitivity,
        "layering_preference": layering_preference,
        "variety_level": payload.get("variety", "moderate"),
    }
