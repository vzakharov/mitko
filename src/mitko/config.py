from typing import Literal

from pydantic import Field, field_validator
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
    telegram_mode: Literal["webhook", "polling"] = "polling"
    admin_group_id: int

    @field_validator("admin_group_id")
    @classmethod
    def validate_channel_id(cls, v: int) -> int:
        if v >= 0 or not str(v).startswith("-100"):
            raise ValueError(
                f"ADMIN_GROUP_ID must be a Telegram group ID in -100XXXXXXXXX format, got {v}"
            )
        return v

    llm_provider: Literal["openai", "anthropic"] = "openai"
    use_openai_responses_api: bool = False
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    matching_interval_minutes: int = 30
    similarity_threshold: float = 0.7
    max_matches_per_profile: int = 5

    weekly_budget_usd: float = Field(default=6.0, gt=0.0)

    mitko_language: Literal["en", "ru"] = "en"

    mitko_repo_url: str = "https://github.com/vzakharov/mitko"

    def validate_llm_keys(self) -> None:
        # OpenAI key always required (used for embeddings even with Anthropic)
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required (used for embeddings)")

        # Anthropic key only needed if using Anthropic for chat
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )


def get_settings() -> Settings:
    import os

    settings = Settings()  # pyright: ignore[reportCallIssue]  # pydantic-settings loads required fields from .env
    settings.validate_llm_keys()

    # TODO: Handle this more gracefully - we're loading envs into settings to load them back into envs
    # This is needed because PydanticAI expects API keys in os.environ, not in a Settings object.
    # Possible solutions: use load_dotenv() at module init, or pass API keys explicitly to PydanticAI providers
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    return settings


# SETTINGS moved to settings_instance.py to avoid initialization during Docker build
