"""OLLAMA_* variables: a shorthand for pointing Wardrowbe at an Ollama server it does not run."""

from app.config import Settings


class TestOllamaSettings:
    def test_ollama_variables_fill_in_the_ai_settings(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434/")
        monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5vl:7b")
        monkeypatch.setenv("OLLAMA_TEXT_MODEL", "qwen3:8b")
        monkeypatch.setenv("OLLAMA_TIMEOUT", "240")
        settings = Settings()
        assert settings.ai_base_url == "http://ollama:11434/v1"
        assert settings.ai_vision_model == "qwen2.5vl:7b"
        assert settings.ai_text_model == "qwen3:8b"
        assert settings.ai_timeout == 240

    def test_a_v1_url_is_kept(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://192.168.1.5:11434/v1")
        assert Settings().ai_base_url == "http://192.168.1.5:11434/v1"

    def test_ai_settings_stay_without_ollama_ones(self, monkeypatch):
        for name in ("OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_VISION_MODEL", "OLLAMA_TEXT_MODEL"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("AI_BASE_URL", "http://other:8080/v1")
        monkeypatch.setenv("AI_VISION_MODEL", "llava")
        settings = Settings()
        assert (settings.ai_base_url, settings.ai_vision_model) == ("http://other:8080/v1", "llava")
