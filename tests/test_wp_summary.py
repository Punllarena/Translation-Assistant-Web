# ruff: noqa: E501
import json
from contextlib import contextmanager

import httpx
import pytest
from sqlalchemy import update

from api import jobs, publish, publish_job, wp_summary
from api.models import DocumentImage, Series, Volume
from api.routers import wp as wp_router

SITE = "https://blog.example.com"
STATUS = "/wp-json/ta-publisher/v1/status"
PUBLISH = "/wp-json/ta-publisher/v1/publish"
OK = {"created": True, "updated": False, "page_url": f"{SITE}/s/", "post_url": f"{SITE}/p/"}


@pytest.fixture
def wp_site(monkeypatch, db):
    """Fake WordPress for the route and the jobs. `fail_zero` makes index 0 answer 500."""
    state = {"posted": [], "paths": [], "fail_zero": False, "status": "not_found"}

    def handle(request):
        if request.url.path == STATUS:
            return httpx.Response(200, json={"status": state["status"], "post_url": None})
        body = json.loads(request.content)
        state["paths"].append(request.url.path)
        state["posted"].append(body)
        if state["fail_zero"] and body.get("chapter_index") == 0:
            return httpx.Response(500, json={"error": "nope"})
        return httpx.Response(200, json=OK)

    def factory():
        return wp_router.wp_http.client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(wp_router, "http_client", factory)
    monkeypatch.setattr(publish_job, "http_client", factory)
    monkeypatch.setattr("api.publish.check_user_url", lambda url, allow, label: None)

    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    return state


@pytest.fixture
def ready(app_client, me, make_series, db):
    app_client.post("/credentials", json={"kind": "wordpress", "secret": "k" * 12, "endpoint_url": SITE})
    s = make_series(me, "Sword")
    s.wp_series_slug, s.wp_series_title_short = "sword", "SotW"
    db.flush()
    return s


def indexes(wp_site):
    return [p["chapter_index"] for p in wp_site["posted"]]


def test_single_publish_sends_a_pending_summary_first(app_client, me, ready, make_doc, wp_site, db):
    ready.wp_summary, ready.wp_summary_pending = "About.\n\nMore.", True
    doc = make_doc(me, ["一"], series=ready, order=1)
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 200
    assert indexes(wp_site) == [0, 1]
    s = wp_site["posted"][0]
    assert s["chapter_body"] == "<p>About.</p>\n<p>More.</p>" and s["chapter_title"] == "SotW Summary"
    assert not {"first_line", "password", "publish_date", "volume_title", "cover"} & s.keys()
    db.refresh(ready)
    assert (ready.wp_summary_pending, ready.wp_summary_error) == (False, "")


def test_no_pending_summary_sends_one_request(app_client, me, ready, make_doc, wp_site):
    ready.wp_summary, ready.wp_summary_pending = "About.", False
    doc = make_doc(me, ["一"], series=ready, order=1)
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 200
    assert indexes(wp_site) == [1]


def test_blank_pending_summary_is_not_sent(app_client, me, ready, make_doc, wp_site):
    ready.wp_summary, ready.wp_summary_pending = "  ", True
    doc = make_doc(me, ["一"], series=ready, order=1)
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 200
    assert indexes(wp_site) == [1]


def test_failing_summary_still_publishes_the_chapter(app_client, me, ready, make_doc, wp_site, db):
    wp_site["fail_zero"] = True
    ready.wp_summary, ready.wp_summary_pending = "About.", True
    doc = make_doc(me, ["一"], series=ready, order=1)
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 200
    assert indexes(wp_site) == [0, 1]
    db.refresh(ready)
    db.refresh(doc)
    assert (ready.wp_summary_pending, ready.wp_summary_error) == (True, "nope")
    assert doc.wp_status == "publish"


def test_summary_not_sent_when_the_chapter_cannot_be_built(app_client, me, ready, make_doc, wp_site):
    ready.wp_summary, ready.wp_summary_pending = "About.", True
    doc = make_doc(me, [], series=ready, order=1)
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 422
    assert wp_site["posted"] == []


def test_summary_not_sent_when_republish_is_refused(app_client, me, ready, make_doc, wp_site):
    ready.wp_summary, ready.wp_summary_pending = "About.", True
    doc = make_doc(me, ["一"], series=ready, order=1)
    doc.wp_status = "publish"
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 409
    assert wp_site["posted"] == []


def test_batch_sends_each_series_summary_once_before_its_first_chapter(
        app_client, me, ready, make_doc, make_series, wp_site, db):
    other = make_series(me, "Blade")
    other.wp_series_slug, other.wp_series_title_short = "blade", "BotW"
    for s in (ready, other):
        s.wp_summary, s.wp_summary_pending = f"About {s.title}.", True
    db.flush()
    docs = [make_doc(me, [f"行{i}"], series=s, order=i) for s in (ready, other) for i in (1, 2)]
    r = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False, "tz": "UTC"})
    assert r.status_code == 202
    jobs.run_next()
    assert indexes(wp_site) == [0, 1, 2, 0, 1, 2]
    slugs = [p["series_slug"] for p in wp_site["posted"]]
    assert slugs[:3] == [slugs[0]] * 3 and slugs[3:] == [slugs[3]] * 3 and slugs[0] != slugs[3]
    db.refresh(ready)
    db.refresh(other)
    assert not ready.wp_summary_pending and not other.wp_summary_pending


def test_batch_second_chapter_carries_the_summary_when_the_first_cannot_be_built(
        app_client, me, ready, make_doc, wp_site, db):
    ready.wp_summary, ready.wp_summary_pending = "About.", True
    db.flush()
    docs = [make_doc(me, [], series=ready, order=1), make_doc(me, ["行"], series=ready, order=2)]
    r = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False, "tz": "UTC"})
    assert r.status_code == 202
    jobs.run_next()
    assert indexes(wp_site) == [0, 2]
    db.refresh(ready)
    assert not ready.wp_summary_pending


def test_an_edit_made_while_sending_stays_pending(app_client, me, ready, make_doc, wp_site, db):
    ready.wp_summary, ready.wp_summary_pending = "Old.", True
    db.flush()
    c = httpx.Client(transport=httpx.MockTransport(lambda request: (
        db.execute(update(Series).where(Series.id == ready.id).values(wp_summary="New.")),
        httpx.Response(200, json=OK))[1]))
    wp_summary.send(c, ready, SITE + PUBLISH, "k" * 12)
    db.refresh(ready)
    assert (ready.wp_summary, ready.wp_summary_pending) == ("New.", True)


def test_series_without_slug_sends_nothing_and_keeps_pending(ready, wp_site, db):
    ready.wp_summary, ready.wp_summary_pending = "About.", True
    ready.wp_series_slug = ""
    c = httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("sent")))
    wp_summary.send(c, ready, SITE + PUBLISH, "k" * 12)
    assert (ready.wp_summary_pending, ready.wp_summary_error) == (True, "")


def test_illustrations_job_sends_a_pending_summary_first(app_client, me, ready, make_doc, wp_site, db):
    ready.wp_summary, ready.wp_summary_pending = "About.", True
    vol = Volume(series_id=ready.id, subtitle="Vol 1")
    db.add(vol)
    db.flush()
    doc = make_doc(me, [], series=ready, order=1, volume=vol, title="Illustrations")
    doc.is_illustrations = True
    db.add(DocumentImage(document_id=doc.id, anchor_position=0, src_path="a.png", data=b"A" * 30))
    db.flush()
    r = app_client.post(f"/documents/{doc.id}/wp/illustrations", json={})
    assert r.status_code == 202
    jobs.run_next()
    assert wp_site["paths"][0] == PUBLISH and wp_site["posted"][0]["chapter_index"] == 0
    assert wp_site["paths"][1:] == ["/wp-json/ta-publisher/v1/illustrations"]
    db.refresh(ready)
    assert ready.wp_summary_pending is False


def test_chapter_zero_is_refused(app_client, me, ready, make_doc, wp_site, db):
    doc = make_doc(me, ["一"], series=ready, order=1)
    doc.wp_chapter_index = 0
    db.flush()
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert r.status_code == 422 and r.json()["detail"] == publish.SUMMARY_MOVED
    assert wp_site["posted"] == []


def test_batch_reports_chapter_zero_as_a_failed_row(app_client, me, ready, make_doc, wp_site, db):
    doc = make_doc(me, ["一"], series=ready, order=1)
    doc.wp_chapter_index = 0
    db.flush()
    r = app_client.post("/wp/batch", json={"document_ids": [doc.id], "schedule": False, "tz": "UTC"})
    jobs.run_next()
    row = app_client.get(f"/jobs/{r.json()['id']}").json()["result"]["chapters"][0]
    assert row["ok"] is False and row["error"] == publish.SUMMARY_MOVED
    assert wp_site["posted"] == []
