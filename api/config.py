from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
