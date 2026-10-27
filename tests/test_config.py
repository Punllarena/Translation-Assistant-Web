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
    for name in ("TA_LIBRETRANSLATE_URL", "TA_EDICT_PATH", "TA_CONJUGATIONS_PATH"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert (s.libretranslate_url, s.edict_path, s.conjugations_path) == ("", "", "")


def test_jobs_settings_defaults(monkeypatch):
    monkeypatch.setenv("TA_SECRET_KEY", "x" * 32)
    for name in ("TA_RUN_JOBS_WORKER", "TA_SYOSETU_DELAY_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert (s.run_jobs_worker, s.syosetu_delay_seconds) == (True, 5.0)


def test_wp_private_urls_default_off(monkeypatch):
    monkeypatch.setenv("TA_SECRET_KEY", "x" * 32)
    monkeypatch.delenv("TA_WP_ALLOW_PRIVATE_URLS", raising=False)
    assert Settings(_env_file=None).wp_allow_private_urls is False


def test_settings_read_the_key_file_when_no_key_is_set(monkeypatch, tmp_path):
    key = tmp_path / "secret_key"
    key.write_text("k" * 48 + "\n", encoding="utf-8")
    monkeypatch.setenv("TA_SECRET_KEY", "")
    monkeypatch.setenv("TA_SECRET_KEY_FILE", str(key))
    assert Settings(_env_file=None).secret_key == "k" * 48


def test_settings_prefer_an_explicit_key_over_the_file(monkeypatch, tmp_path):
    key = tmp_path / "secret_key"
    key.write_text("k" * 48, encoding="utf-8")
    monkeypatch.setenv("TA_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("TA_SECRET_KEY_FILE", str(key))
    assert Settings(_env_file=None).secret_key == "x" * 32
