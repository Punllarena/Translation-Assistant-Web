# ruff: noqa: E501
import json
from contextlib import contextmanager

import httpx
import pytest

from api import jobs, publish_job
from api.models import DocumentImage, Job, Volume

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
    assert [x["chapter_number"] for x in rows] == [1, 2, 3] and all(x["ok"] for x in rows)
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
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert len(rows) == 1 and rows[0]["ok"] is True


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


def plates(me, series, make_doc, db, images=(("a.png", b"A" * 30),), cover=False, subtitle="Vol 1"):
    """A volume whose first chapter is a marked, text-free Illustrations chapter holding `images`."""
    vol = Volume(series_id=series.id, subtitle=subtitle)
    db.add(vol)
    db.flush()
    doc = make_doc(me, [], series=series, order=1, volume=vol, title="Illustrations")
    doc.is_illustrations = True
    db.add_all(DocumentImage(document_id=doc.id, anchor_position=0, src_path=src, data=data)
               for src, data in images)
    if cover:
        db.add(DocumentImage(document_id=doc.id, anchor_position=0, src_path="c.jpg", data=b"C", is_cover=True))
    db.flush()
    return vol, doc


def test_illustrations_chapter_uploads_in_batches_own_images_first(
        app_client, me, ready, make_doc, wp_site, db, monkeypatch):
    monkeypatch.setattr("api.core.wp._ILLUS_BATCH_BYTES", 50)  # cover (4) + a (40) fit; then one per batch
    vol, doc = plates(me, ready, make_doc, db, [("a.png", b"A" * 30), ("b.png", b"B" * 30)], cover=True)
    text = make_doc(me, ["一"], series=ready, order=2, volume=vol)
    db.add(DocumentImage(document_id=text.id, anchor_position=0, src_path="t.png", data=b"T" * 30))
    db.flush()
    r = app_client.post(f"/documents/{doc.id}/wp/illustrations", json={})
    assert r.status_code == 202 and r.json()["kind"] == "wp_illustrations"
    jobs.run_next()
    job = app_client.get(f"/jobs/{r.json()['id']}").json()
    assert job["state"] == "done" and job["result"]["batches"] == 3 and job["result"]["images"] == 4
    sent = [(p, b["mode"], "cover" in b, [i["filename"] for i in b["images"]]) for p, b in wp_site["posted"]]
    assert sent == [(ILLUS, "replace", True, ["a.png"]), (ILLUS, "append", False, ["b.png"]),
                    (ILLUS, "append", False, ["t.png"])]
    db.refresh(doc)
    assert (doc.wp_status, doc.wp_post_url, doc.wp_chapter_index) == ("publish", "pg", None)
    assert doc.wp_published_at is not None and doc.wp_scheduled_for is None
    db.refresh(vol)
    assert vol.wp_volume_title == wp_site["posted"][0][1]["volume_title"] == "Volume - Vol 1"


def test_illustrations_endpoint_rules(app_client, me, ready, make_doc, make_user, make_series, wp_site, db):
    vol, doc = plates(me, ready, make_doc, db)
    url = f"/documents/{doc.id}/wp/illustrations"
    theirs = make_doc(make_user(email="o@example.com"), [])
    assert app_client.post(f"/documents/{theirs.id}/wp/illustrations", json={}).status_code == 404
    text = make_doc(me, ["一"], series=ready, order=2, volume=vol)
    r = app_client.post(f"/documents/{text.id}/wp/illustrations", json={})
    assert r.status_code == 422 and "Illustrations chapter" in r.json()["detail"]
    _, bare_doc = plates(me, make_series(me, "Bare"), make_doc, db)
    r = app_client.post(f"/documents/{bare_doc.id}/wp/illustrations", json={})
    assert r.status_code == 422 and "Bare" in r.json()["detail"]
    _, empty = plates(me, ready, make_doc, db, images=(), subtitle="Vol 2")
    r = app_client.post(f"/documents/{empty.id}/wp/illustrations", json={})
    assert r.status_code == 422 and "no illustrations" in r.json()["detail"]
    # a queued batch that lists the chapter holds the upload
    assert app_client.post("/wp/batch", json={"document_ids": [doc.id], "schedule": False}).status_code == 202
    r = app_client.post(url, json={})
    assert r.status_code == 409 and r.json()["detail"] == "an illustrations upload is already queued or running"
    jobs.run_next()
    db.refresh(doc)
    assert doc.wp_status == "publish"
    r = app_client.post(url, json={})
    assert r.status_code == 409
    assert r.json()["detail"] == "already published; publishing again overwrites the illustrations page"
    assert app_client.post(url, json={"confirm_republish": True}).status_code == 202
    r = app_client.post(url, json={"confirm_republish": True})
    assert r.status_code == 409 and r.json()["detail"] == "an illustrations upload is already queued or running"
    # nor may a batch take the chapter while its upload is queued
    r = app_client.post("/wp/batch", json={"document_ids": [doc.id, text.id], "schedule": False,
                                           "confirm_republish": True})
    assert r.status_code == 409 and r.json()["detail"] == "an illustrations upload is already queued or running"
    assert app_client.post("/wp/batch", json={"document_ids": [text.id], "schedule": False}).status_code == 202


def test_batch_routes_illustrations_chapter_to_upload(app_client, me, ready, make_doc, wp_site, db):
    vol, doc = plates(me, ready, make_doc, db)
    text = make_doc(me, ["一"], series=ready, order=2, volume=vol)
    jid = app_client.post("/wp/batch", json={"document_ids": [text.id, doc.id], "schedule": False}).json()["id"]
    jobs.run_next()
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert [(x["document_id"], x["ok"], x["illustrations"], x["chapter_number"]) for x in rows] == [
        (doc.id, True, True, None), (text.id, True, False, 1)]
    assert rows[0]["post_url"] == "pg" and rows[0]["password"] is None
    assert [p for p, _ in wp_site["posted"]] == [ILLUS, PUBLISH]
    db.refresh(doc)
    assert (doc.wp_status, doc.wp_post_url, doc.wp_chapter_index) == ("publish", "pg", None)


def test_batch_gives_illustrations_no_slot(app_client, me, ready, make_doc, wp_site, db):
    vol, doc = plates(me, ready, make_doc, db)
    texts = [make_doc(me, [f"行{i}"], series=ready, order=i + 1, volume=vol) for i in (1, 2)]
    r = app_client.post("/wp/batch", json={
        "document_ids": [d.id for d in (doc, *texts)], "schedule": True,
        "start": "2026-11-01T20:00:00+09:00", "chapters_per_day": 2, "tz": "Asia/Tokyo"})
    assert r.status_code == 202
    params = db.get(Job, r.json()["id"]).params_json["chapters"]
    assert params[0] == {"document_id": doc.id, "scheduled_for": None}
    # the same slots test_batch_schedules_in_order_and_records_each gives its first two chapters
    assert [p["scheduled_for"] for p in params[1:]] == ["2026-11-01T20:00:00+09:00", "2026-11-01T21:00:00+09:00"]
    jobs.run_next()
    dates = [(p, b.get("publish_date")) for p, b in wp_site["posted"]]
    assert dates == [(ILLUS, None), (PUBLISH, "2026-11-01T11:00:00Z"), (PUBLISH, "2026-11-01T12:00:00Z")]
    db.refresh(doc)
    assert doc.wp_status == "publish" and doc.wp_scheduled_for is None


def test_volume_illustrations_route_is_gone(app_client, me, ready, make_doc, wp_site, db):
    vol, _ = plates(me, ready, make_doc, db)
    assert app_client.post(f"/volumes/{vol.id}/wp/illustrations").status_code in (404, 405)


def test_batch_rows_carry_display_numbers_and_flag_illustrations(
        app_client, me, ready, make_doc, wp_site, db):
    illus = make_doc(me, [], series=ready, order=1, title="Illustrations")
    illus.is_illustrations = True
    docs = [make_doc(me, [f"行{i}"], series=ready, order=i + 1) for i in (1, 2)]
    db.flush()
    r = app_client.post("/wp/batch", json={
        "document_ids": [d.id for d in (illus, *docs)], "schedule": False})
    assert r.status_code == 202
    jobs.run_next()
    rows = app_client.get(f"/jobs/{r.json()['id']}").json()["result"]["chapters"]
    assert [(x["chapter_number"], x["illustrations"], x["ok"]) for x in rows] == [
        (None, True, False), (1, False, True), (2, False, True)]
    assert "no illustrations" in rows[0]["error"]  # routed to the upload, which has no images
    assert [b["chapter_index"] for _, b in wp_site["posted"]] == [1, 2]
