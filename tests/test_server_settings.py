import pytest

from api import publish, server_settings
from api.config import Settings, get_settings
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
    # Hermetic: a developer's .env (e.g. TA_LIBRETRANSLATE_URL) must not leak into the sources.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    try:
        assert entry(app_client, "libretranslate_url") == {
            "key": "libretranslate_url", "value": "http://lt.env", "source": "env"}
        assert all(e["key"] != "ollama_url" for e in app_client.get("/admin/settings").json())
    finally:
        get_settings.cache_clear()


def test_db_row_wins_and_reset_falls_back(app_client, admin, db):
    r = app_client.put(
        "/admin/settings/libretranslate_url", json={"value": "  http://gpu.lan:5000  "})
    assert r.status_code == 200
    assert r.json() == {"key": "libretranslate_url", "value": "http://gpu.lan:5000", "source": "db"}
    assert server_settings.effective(db).libretranslate_url == "http://gpu.lan:5000"
    assert app_client.delete("/admin/settings/libretranslate_url").status_code == 204
    assert app_client.delete("/admin/settings/libretranslate_url").status_code == 204  # idempotent
    assert server_settings.effective(db).libretranslate_url == get_settings().libretranslate_url


def test_ollama_url_is_no_longer_a_server_setting(app_client, admin):
    r = app_client.put("/admin/settings/ollama_url", json={"value": "http://x"})
    assert r.status_code == 404


@pytest.mark.parametrize("key,value", [
    ("libretranslate_url", "localhost:5000"),        # no scheme
    ("libretranslate_url", "ftp://x"),
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
