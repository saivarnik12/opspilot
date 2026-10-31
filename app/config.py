from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OpsPilot"
    database_url: str = "sqlite:///./opspilot.db"
    # MUST be overridden in production: openssl rand -hex 32
    secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 60
    # Optional. Without a key, incident analysis uses the built-in rule engine.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return v or None


settings = Settings()
