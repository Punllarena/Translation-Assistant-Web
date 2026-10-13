import httpx
import pytest

from api import wp_prefs
from api.routers import wp as wp_router

SITE = "https://blog.example.com"


@pytest.fixture
def wp_site(monkeypatch):
    """A fake WordPress: `answers[path]` is (status, json); every request is recorded."""
    answers = {"/wp-json/ta-publisher/v1/status": (200, {"status": "not_found", "post_url": None})}
    calls = []

    def handle(request):
        calls.append(request)
        status, body = answers.get(request.url.path, (404, {"error": "no route"}))
        return httpx.Response(status, json=body)

    monkeypatch.setattr(wp_router, "http_client",
                        lambda: wp_router.wp_http.client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr("api.publish.check_user_url", lambda url, allow, label: None)
    return answers, calls


def save_wp(app_client, url=SITE, key="plugin-key-1234"):
    body = {"kind": "wordpress", "secret": key, "endpoint_url": url}
    r = app_client.post("/credentials", json=body)
    assert r.status_code == 201


def test_prefs_have_the_desktop_defaults(app_client, me):
    assert app_client.get("/wp/prefs").json() == {
        "wp_password_enabled": False, "wp_unlock_after": 3, "wp_attribution_enabled": True,
        "wp_default_schedule_time": "", "wp_chapters_per_day": 1, "wp_schedule_scope_global": False,
    }


def test_saved_prefs_are_read_and_bad_shapes_fall_back(app_client, me):
    app_client.put("/settings", json={
        "wp_password_enabled": True, "wp_unlock_after": 0, "wp_default_schedule_time": "20:30",
        "wp_chapters_per_day": "2", "wp_schedule_scope_global": True,
    })
    p = app_client.get("/wp/prefs").json()
    assert p["wp_password_enabled"] is True and p["wp_schedule_scope_global"] is True
    assert p["wp_default_schedule_time"] == "20:30"
    assert p["wp_unlock_after"] == 3 and p["wp_chapters_per_day"] == 1  # out of range / wrong type


@pytest.mark.parametrize("value", ["24:00", "8:00", "20:30:00", 2030])
def test_bad_schedule_times_read_as_unset(value):
    assert wp_prefs.parse({"wp_default_schedule_time": value}).wp_default_schedule_time == ""


def test_connection_test_needs_a_credential(app_client, me, wp_site):
    r = app_client.post("/wp/test")
    assert r.status_code == 422 and "Settings → WordPress" in r.json()["detail"]


def test_connection_test_ok(app_client, me, wp_site):
    _, calls = wp_site
    save_wp(app_client)
    assert app_client.post("/wp/test").json()["ok"] is True
    assert calls[0].url.params["api_key"] == "plugin-key-1234"


def test_connection_test_reports_a_rejected_key(app_client, me, wp_site):
    answers, _ = wp_site
    answers["/wp-json/ta-publisher/v1/status"] = (401, {"error": "Invalid API key"})
    save_wp(app_client)
    body = app_client.post("/wp/test").json()
    assert body["ok"] is False and "rejected the API key" in body["message"]


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.5/", "http://169.254.169.254/",
                                 "ftp://example.com/"])
def test_private_and_non_http_endpoints_are_refused_before_any_request(
    app_client, me, monkeypatch, url
):
    calls = []
    monkeypatch.setattr(wp_router, "http_client", lambda: wp_router.wp_http.client(
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={}))))
    save_wp(app_client, url=url)
    r = app_client.post("/wp/test")
    assert r.status_code == 422 and calls == []


def test_private_endpoints_are_allowed_with_the_flag(app_client, me, monkeypatch):
    from api.config import get_settings
    monkeypatch.setattr(get_settings(), "wp_allow_private_urls", True)
    monkeypatch.setattr(wp_router, "http_client", lambda: wp_router.wp_http.client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "not_found"}))))
    save_wp(app_client, url="http://127.0.0.1:8080/")
    assert app_client.post("/wp/test").json()["ok"] is True


def test_document_out_carries_the_wp_dates(app_client, me, make_doc):
    doc = make_doc(me, ["x"])
    body = app_client.get(f"/documents/{doc.id}").json()
    assert body["wp_published_at"] is None and body["wp_scheduled_for"] is None
