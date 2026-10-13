# ruff: noqa: E501
import json
from contextlib import contextmanager

import httpx
import pytest

from api import jobs, publish_job
from api.models import DocumentImage, Volume

SITE = "https://blog.example.com"
PUBLISH = "/wp-json/ta-publisher/v1/publish"
ILLUS = "/wp-json/ta-publisher/v1/illustrations"


@pytest.fixture
def wp_site(monkeypatch, db):
    """Fake WordPress for the job handlers; route the worker's sessions to the test db."""
    state = {"fail": set(), "posted": []}

    def handle(request):
        body = json.loads(request.content)
        state["posted"].append((request.url.path, body))
        if body.get("chapter_index") in state["fail"]:
            return httpx.Response(500, json={"error": "renumber_conflict"})
        return httpx.Response(200, json={"created": True, "page_url": "pg", "post_url": "po"})

    monkeypatch.setattr(publish_job, "http_client",
                        lambda: publish_job.wp_http.client(transport=httpx.MockTransport(handle)))
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


def chapters(make_doc, user, series, n):
    return [make_doc(user, [f"行{i}"], series=series, order=i) for i in range(1, n + 1)]


def test_batch_schedules_in_order_and_records_each(app_client, me, ready, make_doc, wp_site, db):
    docs = chapters(make_doc, me, ready, 3)
    r = app_client.post("/wp/batch", json={
        "document_ids": [d.id for d in reversed(docs)], "schedule": True,
        "start": "2026-11-01T20:00:00+09:00", "chapters_per_day": 2, "tz": "Asia/Tokyo"})
    assert r.status_code == 202 and r.json()["kind"] == "wp_publish"
    assert jobs.run_next() is True
    job = app_client.get(f"/jobs/{r.json()['id']}").json()
    assert job["state"] == "done"
    rows = job["result"]["chapters"]
    assert [x["series_order"] for x in rows] == [1, 2, 3] and all(x["ok"] for x in rows)
    dates = [b["publish_date"] for _, b in wp_site["posted"]]
    assert dates == ["2026-11-01T11:00:00Z", "2026-11-01T12:00:00Z", "2026-11-02T12:00:00Z"]
    for d in docs:
        db.refresh(d)
    assert {d.wp_status for d in docs} == {"future"}


def test_batch_now_publishes_without_dates(app_client, me, ready, make_doc, wp_site):
    docs = chapters(make_doc, me, ready, 2)
    app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False})
    jobs.run_next()
    assert all("publish_date" not in b for _, b in wp_site["posted"])


def test_one_failing_chapter_does_not_stop_the_rest(app_client, me, ready, make_doc, wp_site):
    docs = chapters(make_doc, me, ready, 3)
    wp_site["fail"].add(2)
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    jobs.run_next()
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert [x["ok"] for x in rows] == [True, False, True]
    assert rows[1]["error"] == "renumber_conflict"


def test_live_chapters_are_skipped_unless_confirmed(app_client, me, ready, make_doc, wp_site, db):
    docs = chapters(make_doc, me, ready, 2)
    docs[0].wp_status = "publish"
    db.flush()
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    jobs.run_next()
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert [x["ok"] for x in rows] == [False, True] and "already" in rows[0]["error"]
    assert len(wp_site["posted"]) == 1


def test_a_chapter_deleted_after_enqueue_is_a_failed_row(app_client, me, ready, make_doc, wp_site, db):
    docs = chapters(make_doc, me, ready, 2)
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    db.delete(docs[0])
    db.flush()
    jobs.run_next()
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert rows[0] == {"document_id": docs[0].id, "ok": False, "error": "the chapter no longer exists"}
    assert rows[1]["ok"] is True


def test_cancel_stops_between_chapters_keeping_what_was_published(
        app_client, me, ready, make_doc, wp_site, db, monkeypatch):
    docs = chapters(make_doc, me, ready, 3)
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    original = jobs.JobContext.progress

    def cancel_after_first(self, done, total, message=""):
        if done == 1:
            self.job.cancel_requested = True
        original(self, done, total, message)
    monkeypatch.setattr(jobs.JobContext, "progress", cancel_after_first)
    jobs.run_next()
    assert app_client.get(f"/jobs/{jid}").json()["state"] == "cancelled"
    db.refresh(docs[0])
    assert docs[0].wp_status == "publish" and len(wp_site["posted"]) == 1


def test_batch_enqueue_checks(app_client, me, ready, make_doc, make_user, make_series, wp_site, db):
    mine = chapters(make_doc, me, ready, 1)[0]
    theirs = make_doc(make_user(email="o@example.com"), ["x"])
    r = app_client.post("/wp/batch", json={"document_ids": [mine.id, theirs.id], "schedule": False})
    assert r.status_code == 422 and "document_ids" in r.json()["detail"]
    bare = make_series(me, "Bare")
    loose = make_doc(me, ["x"], series=bare, order=1)
    r = app_client.post("/wp/batch", json={"document_ids": [loose.id], "schedule": False})
    assert r.status_code == 422 and "Bare" in r.json()["detail"]
    r = app_client.post("/wp/batch", json={"document_ids": [mine.id]})
    assert r.status_code == 422  # scheduling needs a start
    r = app_client.post("/wp/batch", json={"document_ids": [mine.id], "schedule": False, "tz": "Nope/Zone"})
    assert r.status_code == 422
    assert app_client.post("/wp/batch", json={"document_ids": [mine.id], "schedule": False}).status_code == 202
    assert app_client.post("/wp/batch", json={"document_ids": [mine.id], "schedule": False}).status_code == 409


def test_passwords_are_kept_in_the_job_result(app_client, me, ready, make_doc, wp_site):
    app_client.put("/settings", json={"wp_password_enabled": True, "wp_unlock_after": 1})
    docs = chapters(make_doc, me, ready, 2)
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    jobs.run_next()
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert rows[0]["password"] is None and len(rows[1]["password"]) == 12
    assert "k" * 12 not in json.dumps(app_client.get(f"/jobs/{jid}").json())


def test_illustrations_upload_in_batches(app_client, me, ready, make_doc, wp_site, db, monkeypatch):
    monkeypatch.setattr("api.core.wp._ILLUS_BATCH_BYTES", 50)  # cover (4) + a (40) fit; b splits
    vol = Volume(series_id=ready.id, title="Vol 1")
    db.add(vol)
    db.flush()
    doc = make_doc(me, ["一"], series=ready, order=1, volume=vol)
    db.add_all([
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="a.png", data=b"A" * 30),
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="b.png", data=b"B" * 30),
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="c.jpg", data=b"C", is_cover=True),
    ])
    db.flush()
    r = app_client.post(f"/volumes/{vol.id}/wp/illustrations")
    assert r.status_code == 202
    jobs.run_next()
    job = app_client.get(f"/jobs/{r.json()['id']}").json()
    assert job["state"] == "done" and job["result"]["batches"] == 2 and job["result"]["images"] == 3
    modes = [(p, b["mode"], "cover" in b) for p, b in wp_site["posted"]]
    assert modes == [(ILLUS, "replace", True), (ILLUS, "append", False)]


def test_illustrations_need_images_and_your_volume(app_client, me, ready, make_user, make_series, db, wp_site):
    vol = Volume(series_id=ready.id, title="Empty")
    db.add(vol)
    theirs = make_series(make_user(email="o@example.com"), "T")
    other = Volume(series_id=theirs.id, title="Theirs")
    db.add(other)
    db.flush()
    r = app_client.post(f"/volumes/{vol.id}/wp/illustrations")
    assert r.status_code == 422 and "no illustrations" in r.json()["detail"]
    assert app_client.post(f"/volumes/{other.id}/wp/illustrations").status_code == 404
