import pytest
from pydantic import ValidationError

from api.config import PLACEHOLDER_SECRET_KEY, Settings


def test_settings_require_secret_key(monkeypatch):
    monkeypatch.delenv("TA_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reject_short_secret_key(monkeypatch):
    monkeypatch.setenv("TA_SECRET_KEY", "too-short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_read_env_with_prefix(monkeypatch):
    monkeypatch.setenv("TA_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("TA_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.setenv("TA_ALLOW_PUBLIC_SIGNUP", "true")
    # CI exports TA_COOKIE_SECURE=false; this test pins the defaults.
    monkeypatch.delenv("TA_COOKIE_SECURE", raising=False)
    monkeypatch.delenv("TA_SESSION_TTL_DAYS", raising=False)
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@h:5432/d"
    assert s.allow_public_signup is True
    assert s.cookie_secure is True
    assert s.session_ttl_days == 30


def test_settings_reject_env_example_placeholder(monkeypatch):
    monkeypatch.setenv("TA_SECRET_KEY", PLACEHOLDER_SECRET_KEY)
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(_env_file=None)


def test_mt_settings_defaults(monkeypatch):
    monkeypatch.setenv("TA_SECRET_KEY", "x" * 32)
    for name in ("TA_OLLAMA_URL", "TA_LIBRETRANSLATE_URL", "TA_EDICT_PATH", "TA_CONJUGATIONS_PATH"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert (s.ollama_url, s.libretranslate_url, s.edict_path, s.conjugations_path) == (
        "http://localhost:11434", "", "", ""
    )
