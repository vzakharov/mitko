from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    database_url: str
    telegram_bot_token: str
    telegram_webhook_secret: str | None = None
    telegram_webhook_url: str | None = None
    telegram_mode: Literal["webhook", "polling", "auto"] = "auto"

    llm_provider: Literal["openai", "anthropic"] = "openai"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    matching_interval_minutes: int = 30
    similarity_threshold: float = 0.7
    max_matches_per_profile: int = 5

    mitko_language: Literal["en", "ru"] = "en"

    def validate_llm_keys(self) -> None:
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when using OpenAI")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when using Anthropic")

    def get_effective_mode(self) -> Literal["webhook", "polling"]:
        """Resolve auto mode to actual mode"""
        if self.telegram_mode == "auto":
            return "webhook" if self.telegram_webhook_url else "polling"
        return self.telegram_mode


def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-overload]  # pydantic-settings loads required fields from .env
    settings.validate_llm_keys()
    return settings


settings = get_settings()
