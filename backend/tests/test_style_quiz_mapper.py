from app.schemas.onboarding import StyleQuizAnswers
from app.services.style_quiz_mapper import map_style_quiz_answers


def test_style_quiz_mapper_generates_expected_patch():
    patch = map_style_quiz_answers(
        StyleQuizAnswers(
            primary_occasion="office",
            style_focus="formal",
            color_palette="neutral",
            avoid_colors=["pink"],
            temperature_feel="hot",
            variety="high",
        )
    )

    assert patch["default_occasion"] == "office"
    assert patch["temperature_sensitivity"] == "low"
    assert patch["layering_preference"] == "minimal"
    assert patch["variety_level"] == "high"
    assert "pink" in patch["color_avoid"]

    profile = patch["style_profile"]
    assert profile["formal"] > 50
    assert all(0 <= value <= 100 for value in profile.values())
