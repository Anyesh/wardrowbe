from app.config import Settings


class TestGeocodingUserAgent:
    def test_uses_explicit_user_agent_when_configured(self):
        settings = Settings(
            geocoding_user_agent="WardrowbeCustom/2.0 (+https://example.com/contact)"
        )

        assert settings.get_geocoding_user_agent() == (
            "WardrowbeCustom/2.0 (+https://example.com/contact)"
        )

    def test_builds_user_agent_from_app_metadata_and_contact(self):
        settings = Settings(
            app_name="Wardrowbe",
            app_version="1.2.3",
            geocoding_contact="https://example.com/contact",
        )

        assert settings.get_geocoding_user_agent() == (
            "Wardrowbe/1.2.3 (https://example.com/contact)"
        )
