from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Must match the TA_SECRET_KEY value in .env.example. A deployment that copies the
# example file unchanged would otherwise boot with a publicly known key.
PLACEHOLDER_SECRET_KEY = "change-me-to-at-least-32-characters-long"


class Settings(BaseSettings):
    """All runtime configuration. Environment only — no config files."""

    model_config = SettingsConfigDict(
        env_prefix="TA_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: str = Field(min_length=32)
    database_url: str = "postgresql+psycopg://ta:ta@localhost:5432/ta"
    allow_public_signup: bool = False
    session_ttl_days: int = 30
    cookie_secure: bool = True
    login_max_attempts: int = 10
    login_window_seconds: int = 300

    @field_validator("secret_key")
    @classmethod
    def _reject_placeholder(cls, value: str) -> str:
        if value == PLACEHOLDER_SECRET_KEY:
            raise ValueError(
                "TA_SECRET_KEY is still the .env.example placeholder; generate one with "
                "python -c 'import secrets;print(secrets.token_urlsafe(32))'"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
