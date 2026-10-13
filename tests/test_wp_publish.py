import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from api import publish
from api.models import DocumentImage
from api.routers import wp as wp_router

SITE = "https://blog.example.com"
STATUS = "/wp-json/ta-publisher/v1/status"
PUBLISH = "/wp-json/ta-publisher/v1/publish"


@pytest.fixture
def wp_site(monkeypatch):
    answers = {STATUS: (200, {"status": "not_found", "post_url": None}),
               PUBLISH: (200, {"created": True, "updated": False, "page_url": f"{SITE}/s/s-c1/",
                               "post_url": f"{SITE}/2026/s-c1/"})}
    posted = []

    def handle(request):
        if request.method == "POST":
            posted.append(json.loads(request.content))
        code, body = answers[request.url.path]
        return httpx.Response(code, json=body)

    monkeypatch.setattr(wp_router, "http_client",
                        lambda: wp_router.wp_http.client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr("api.publish.check_user_url", lambda url, allow, label: None)
    return answers, posted


@pytest.fixture
def ready(app_client, me, make_series, db):
    """WordPress configured, and a series with its WordPress fields."""
    app_client.post("/credentials", json={"kind": "wordpress", "secret": "k" * 12, "endpoint_url": SITE})  # noqa: E501
    s = make_series(me, "Sword")
    s.wp_series_slug, s.wp_series_title_short = "sword", "SotW"
    db.flush()
    return s


def test_publish_sends_the_desktop_payload_and_records_the_result(app_client, me, ready, make_doc, wp_site, db):  # noqa: E501
    _, posted = wp_site
    doc = make_doc(me, ["一", "二"], series=ready, order=1, title="The Beginning")
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert r.status_code == 200
    assert r.json()["created"] is True and r.json()["password"] is None
    p = posted[0]
    assert (p["api_key"], p["series_slug"], p["chapter_index"]) == ("k" * 12, "sword", 1)
    assert p["chapter_title"] == "SotW The Beginning"
    assert p["chapter_body"].startswith("<p>tr:一</p>\n<p>tr:二</p>")
    assert "automatically published" in p["chapter_body"] and p["first_line"] == "tr:一"
    db.refresh(doc)
    assert (doc.wp_status, doc.wp_post_url, doc.wp_chapter_index) == ("publish", f"{SITE}/2026/s-c1/", 1)  # noqa: E501
    assert doc.wp_published_at is not None and doc.wp_scheduled_for is None


def test_scheduled_publish_sends_utc_and_records_future(app_client, me, ready, make_doc, wp_site, db):  # noqa: E501
    _, posted = wp_site
    doc = make_doc(me, ["一"], series=ready, order=1)
    r = app_client.post(f"/documents/{doc.id}/wp/publish",
                        json={"scheduled_for": "2026-11-01T20:00:00+09:00"})
    assert r.status_code == 200
    assert posted[0]["publish_date"] == "2026-11-01T11:00:00Z"
    db.refresh(doc)
    assert doc.wp_status == "future"
    assert doc.wp_scheduled_for == doc.wp_published_at == datetime(2026, 11, 1, 11, tzinfo=UTC)


def test_naive_schedule_is_422(app_client, me, ready, make_doc, wp_site):
    doc = make_doc(me, ["一"], series=ready, order=1)
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={"scheduled_for": "2026-11-01T20:00:00"})  # noqa: E501
    assert r.status_code == 422


def test_republish_needs_confirmation_cached(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    doc = make_doc(me, ["一"], series=ready, order=1)
    doc.wp_status = "publish"
    db.flush()
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 409
    assert posted == []
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={"confirm_republish": True})
    assert r.status_code == 200 and len(posted) == 1


def test_republish_needs_confirmation_when_only_wordpress_knows(app_client, me, ready, make_doc, wp_site):  # noqa: E501
    answers, posted = wp_site
    answers[STATUS] = (200, {"status": "future", "post_url": "u"})
    doc = make_doc(me, ["一"], series=ready, order=1)
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 409
    assert posted == []


def test_unreachable_status_falls_back_to_cache_and_a_failed_publish_writes_nothing(
        app_client, me, ready, make_doc, wp_site, db):
    answers, _ = wp_site
    answers[STATUS] = (500, {"error": "down"})
    answers[PUBLISH] = (500, {"error": "Failed to create page"})
    doc = make_doc(me, ["一"], series=ready, order=1)
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert r.status_code == 502 and r.json()["detail"] == "Failed to create page"
    db.refresh(doc)
    assert doc.wp_status == "" and doc.wp_published_at is None


def test_password_protection_follows_series_then_user(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    app_client.put("/settings", json={"wp_password_enabled": True, "wp_unlock_after": 1})
    doc = make_doc(me, ["一"], series=ready, order=3)
    body = app_client.post(f"/documents/{doc.id}/wp/publish", json={}).json()
    assert len(body["password"]) == 12 and body["unlock_chapter_index"] == 2
    assert posted[0]["password"] == body["password"]
    ready.wp_password_enabled = False  # the series override wins
    db.flush()
    other = make_doc(me, ["二"], series=ready, order=4)
    assert app_client.post(f"/documents/{other.id}/wp/publish", json={}).json()["password"] is None


def test_unpublishable_chapters_are_422(app_client, me, ready, make_doc, wp_site, db):
    blank = make_doc(me, ["一"], series=ready, order=1, translated=False)
    assert "No translated lines" in app_client.post(f"/documents/{blank.id}/wp/publish", json={}).json()["detail"]  # noqa: E501
    loose = make_doc(me, ["一"])
    assert app_client.post(f"/documents/{loose.id}/wp/publish", json={}).status_code == 422
    ready.wp_series_slug = ""
    db.flush()
    doc = make_doc(me, ["一"], series=ready, order=2)
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert r.status_code == 422 and "slug" in r.json()["detail"]


def test_inline_images_and_cover_ride_along(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    doc = make_doc(me, ["一", "二"], series=ready, order=1)
    db.add_all([
        DocumentImage(document_id=doc.id, anchor_position=1, src_path="i/a.png", data=b"A"),
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="i/c.jpg", data=b"C", is_cover=True),  # noqa: E501
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="i/x.png", data=b"X", exclude_export=True),  # noqa: E501
    ])
    db.flush()
    app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    p = posted[0]
    assert [(i["position"], i["filename"]) for i in p["images"]] == [(1, "a.png")]
    assert p["cover"]["filename"] == "c.jpg"


def test_status_refresh_writes_status_but_not_dates(app_client, me, ready, make_doc, wp_site, db):
    answers, _ = wp_site
    answers[STATUS] = (200, {"status": "publish", "post_url": "u2"})
    doc = make_doc(me, ["一"], series=ready, order=1)
    doc.wp_status, doc.wp_published_at = "future", datetime(2026, 1, 1, tzinfo=UTC)
    db.flush()
    body = app_client.post(f"/documents/{doc.id}/wp/status").json()
    assert (body["cached_status"], body["status"], body["post_url"]) == ("future", "publish", "u2")
    db.refresh(doc)
    assert doc.wp_published_at == datetime(2026, 1, 1, tzinfo=UTC)
    answers[STATUS] = (200, {"status": "not_found", "post_url": None})
    assert app_client.post(f"/documents/{doc.id}/wp/status").json()["status"] == ""


def test_status_refresh_survives_an_unreachable_site(app_client, me, ready, make_doc, wp_site):
    answers, _ = wp_site
    answers[STATUS] = (503, {"error": "maintenance"})
    doc = make_doc(me, ["一"], series=ready, order=1)
    body = app_client.post(f"/documents/{doc.id}/wp/status").json()
    assert body["remote_error"] == "maintenance" and body["status"] == ""


def test_status_suggests_the_auto_slot_after_a_scheduled_previous_chapter(
        app_client, me, ready, make_doc, wp_site, db):
    app_client.put("/settings", json={"wp_chapters_per_day": 1, "wp_default_schedule_time": "20:00"})  # noqa: E501
    prev = make_doc(me, ["一"], series=ready, order=1)
    prev.wp_status = "future"
    prev.wp_published_at = datetime(2026, 11, 1, 11, tzinfo=UTC)  # 20:00 in Tokyo
    doc = make_doc(me, ["二"], series=ready, order=2)
    db.flush()
    body = app_client.post(f"/documents/{doc.id}/wp/status", params={"tz": "Asia/Tokyo"}).json()
    assert body["previous_scheduled"] is True
    assert datetime.fromisoformat(body["suggested_slot"]) == datetime(2026, 11, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo"))  # noqa: E501


@pytest.mark.parametrize("tz", ["Mars/Base", "../../etc/passwd", "x" * 65])
def test_bad_time_zones_are_422(app_client, me, ready, make_doc, wp_site, tz):
    doc = make_doc(me, ["一"], series=ready, order=1)
    assert app_client.post(f"/documents/{doc.id}/wp/status", params={"tz": tz}).status_code == 422


def test_another_users_chapter_is_404(app_client, ready, make_user, make_doc, wp_site):
    theirs = make_doc(make_user(email="o@example.com"), ["一"])
    assert app_client.post(f"/documents/{theirs.id}/wp/publish", json={}).status_code == 404
    assert app_client.post(f"/documents/{theirs.id}/wp/status").status_code == 404


def test_batch_slots_fill_each_day_then_roll_over():
    tokyo = ZoneInfo("Asia/Tokyo")
    start = datetime(2026, 7, 20, 20, tzinfo=tokyo)
    slots = publish.batch_slots(start, 4, 2, "20:00", tokyo)
    assert [s.strftime("%d %H:%M") for s in slots] == ["20 20:00", "20 21:00", "21 20:00", "21 21:00"]  # noqa: E501
