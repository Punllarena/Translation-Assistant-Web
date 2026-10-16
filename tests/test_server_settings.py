import pytest

from api import publish, server_settings
from api.config import get_settings
from api.routers import mt


@pytest.fixture
def admin(app_client, make_user, login):
    user = make_user(email="admin@example.com", is_admin=True)
    login(app_client, "admin@example.com")
    return user


def entry(client, key):
    return next(e for e in client.get("/admin/settings").json() if e["key"] == key)


def test_listing_reports_env_and_default_sources(app_client, admin, monkeypatch):
    monkeypatch.setenv("TA_LIBRETRANSLATE_URL", "http://lt.env")
    monkeypatch.delenv("TA_OLLAMA_URL", raising=False)
    get_settings.cache_clear()
    try:
        assert entry(app_client, "libretranslate_url") == {
            "key": "libretranslate_url", "value": "http://lt.env", "source": "env"}
        assert entry(app_client, "ollama_url")["source"] == "default"
    finally:
        get_settings.cache_clear()


def test_db_row_wins_and_reset_falls_back(app_client, admin, db):
    r = app_client.put("/admin/settings/ollama_url", json={"value": "  http://gpu.lan:11434  "})
    assert r.status_code == 200
    assert r.json() == {"key": "ollama_url", "value": "http://gpu.lan:11434", "source": "db"}
    assert server_settings.effective(db).ollama_url == "http://gpu.lan:11434"
    assert app_client.delete("/admin/settings/ollama_url").status_code == 204
    assert app_client.delete("/admin/settings/ollama_url").status_code == 204  # idempotent
    assert server_settings.effective(db).ollama_url == get_settings().ollama_url


@pytest.mark.parametrize("key,value", [
    ("ollama_url", "localhost:11434"),        # no scheme
    ("ollama_url", "ftp://x"),
    ("mt_allow_private_urls", "yes"),
    ("syosetu_delay_seconds", 0.5),
    ("syosetu_delay_seconds", 61),
    ("syosetu_delay_seconds", True),
])
def test_invalid_values_are_422_and_not_saved(app_client, admin, db, key, value):
    r = app_client.put(f"/admin/settings/{key}", json={"value": value})
    assert r.status_code == 422
    assert key in r.json()["detail"]
    assert entry(app_client, key)["source"] != "db"


def test_unknown_key_is_404(app_client, admin):
    assert app_client.put("/admin/settings/secret_key", json={"value": "x"}).status_code == 404
    assert app_client.delete("/admin/settings/secret_key").status_code == 404


def test_non_admin_is_403(app_client, me):
    assert app_client.get("/admin/settings").status_code == 403


def test_wordpress_check_reads_the_effective_flag(app_client, admin, db, monkeypatch):
    seen = []
    monkeypatch.setattr(publish, "check_user_url", lambda url, allow, label: seen.append(allow))
    app_client.post("/credentials", json={"kind": "wordpress", "secret": "k" * 12,
                                          "endpoint_url": "http://wp.lan"})
    app_client.put("/admin/settings/wp_allow_private_urls", json={"value": True})
    publish.wp_config(db, admin.id)
    assert seen == [True]


def test_mt_server_default_url_reads_the_effective_value(app_client, admin, db):
    app_client.put("/admin/settings/libretranslate_url", json={"value": "http://lt.lan"})
    job = mt._configure(db, admin.id, "libretranslate", mt._prefs(db, admin.id))
    assert job.url == "http://lt.lan"
