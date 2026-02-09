import logging
from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

DEFAULT_SECRET_KEY = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Wardrowbe"
    debug: bool = False
    secret_key: str = Field(default=DEFAULT_SECRET_KEY)

    # CORS
    cors_origins: list[str] = Field(default=["http://localhost:3000", "http://localhost:8081"])

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://wardrobe:wardrobe@localhost:5432/wardrobe"
    )
    database_echo: bool = False

    # Redis
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")

    # Authentication - OIDC
    oidc_issuer_url: str | None = Field(default=None)
    oidc_client_id: str | None = Field(default=None)
    oidc_client_secret: str | None = Field(default=None)

    # Forward Auth (TinyAuth, Authelia, etc.)
    # When True, trusts Remote-User/Remote-Email headers from proxy
    auth_trust_header: bool = Field(default=False)

    # AI Service (OpenAI-compatible API - supports Ollama, OpenAI, etc.)
    ai_base_url: str = Field(default="")
    ai_api_key: str | None = Field(default=None)  # API key for authenticated AI endpoints
    ai_vision_model: str = Field(default="gpt-4o")  # For image analysis
    ai_text_model: str = Field(default="gpt-4o")  # For text generation (recommendations)
    ai_timeout: int = Field(default=120)
    ai_max_retries: int = Field(default=3)

    # Weather
    openmeteo_url: str = Field(default="https://api.open-meteo.com/v1")

    # Notifications - default ntfy channel (used when user has none configured)
    ntfy_server: str | None = None
    ntfy_topic: str | None = None
    ntfy_token: str | None = None
    # Legacy/other providers
    mattermost_webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    # Storage
    storage_path: str = Field(default="/data/wardrobe")
    max_upload_size_mb: int = Field(default=10)

    # Image processing
    thumbnail_size: int = 400
    medium_size: int = 800
    original_max_size: int = 2400
    image_quality: int = 90

    def validate_security(self) -> None:
        if self.secret_key == DEFAULT_SECRET_KEY and not self.debug:
            raise RuntimeError(
                "SECRET_KEY is still the default value. "
                "Set a secure SECRET_KEY or enable DEBUG mode for development."
            )

        oidc_issuer = bool(self.oidc_issuer_url)
        oidc_client = bool(self.oidc_client_id)
        if oidc_issuer != oidc_client:
            raise RuntimeError(
                "OIDC is partially configured: both OIDC_ISSUER_URL and OIDC_CLIENT_ID must be set together."
            )

        oidc_configured = oidc_issuer and oidc_client
        if not self.auth_trust_header and not oidc_configured and not self.debug:
            raise RuntimeError(
                "No authentication method configured. "
                "Set OIDC_ISSUER_URL + OIDC_CLIENT_ID, or AUTH_TRUST_HEADER=true, or enable DEBUG mode."
            )

    def get_auth_mode(self) -> str:
        if self.debug and self.secret_key == DEFAULT_SECRET_KEY:
            return "dev"
        if self.oidc_issuer_url and self.oidc_client_id:
            return "oidc"
        if self.auth_trust_header:
            return "forward-auth"
        return "unknown"


@lru_cache
def get_settings() -> Settings:
    return Settings()
