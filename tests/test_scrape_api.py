from contextlib import contextmanager

import httpx
import pytest

from api import fetch_job, jobs
from api.core import scrape
from api.models import Document
from api.routers import scrape as scrape_router

INDEX = ('<div class="p-eplist__sublist"><a href="/n1/1/">One</a></div>'
         '<div class="p-eplist__sublist"><a href="/n1/2/">Two</a></div>'
         '<div class="p-eplist__sublist"><a href="/n1/3/">Three</a></div>')


def chapter(title, body):
    return (f'<h1 class="p-novel__title p-novel__title--rensai">{title}</h1>'
            f'<div class="js-novel-text p-novel__text"><p>{body}</p></div>')


@pytest.fixture
def site(monkeypatch, db):
    """Serve fake syosetu pages; route the worker's sessions to the test db."""
    pages = {"https://ncode.syosetu.com/n1/": INDEX,
             "https://ncode.syosetu.com/n1/1/": chapter("第一話", "一行目です。"),
             "https://ncode.syosetu.com/n1/2/": chapter("第二話", "二行目です。"),
             "https://ncode.syosetu.com/n1/3/": chapter("第三話", "三行目です。")}
    calls = []

    def handle(request):
        calls.append(str(request.url))
        html = pages.get(str(request.url))
        return httpx.Response(200 if html else 404, text=html or "")

    def make():
        return scrape.client(transport=httpx.MockTransport(handle))

    monkeypatch.setattr(scrape_router, "http_client", make)
    monkeypatch.setattr(fetch_job, "http_client", make)

    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    return pages, calls


def test_single_fetch_returns_title_and_text(app_client, me, site):
    r = app_client.post("/scrape/syosetu", json={"url": "https://ncode.syosetu.com/n1/1/"})
    assert r.json() == {"title": "第一話", "content": "一行目です。"}


@pytest.mark.parametrize("url", ["https://x.syosetu.com@evil.com/n1/1/", "http://localhost/"])
def test_single_fetch_refuses_other_hosts(app_client, me, site, url):
    _, calls = site
    assert app_client.post("/scrape/syosetu", json={"url": url}).status_code == 422
    assert calls == []


def test_upstream_failure_is_502(app_client, me, site):
    r = app_client.post("/scrape/syosetu", json={"url": "https://ncode.syosetu.com/n1/9/"})
    assert r.status_code == 502 and "404" in r.json()["detail"]


def test_chapter_list_marks_fetched(app_client, me, make_series, make_doc, site, db):
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    make_doc(me, ["x"], series=s, order=2)
    db.flush()
    body = app_client.get(f"/series/{s.id}/syosetu/chapters").json()
    assert [(c["num"], c["fetched"]) for c in body] == [(1, False), (2, True), (3, False)]


def test_fetch_job_adds_selected_chapters_and_skips_existing(
        app_client, me, make_series, make_doc, site, db):
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    make_doc(me, ["x"], series=s, order=2)
    db.flush()
    r = app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [1, 2, 3, 99]})
    assert r.status_code == 202 and r.json()["kind"] == "syosetu_fetch"
    assert jobs.run_next() is True
    job = app_client.get(f"/jobs/{r.json()['id']}").json()
    assert job["state"] == "done"
    assert job["result"] == {"added": 2, "skipped": 1, "errors": [], "missing": [99]}
    docs = db.query(Document).filter_by(series_id=s.id).order_by(Document.series_order).all()
    assert [(d.series_order, d.title, d.source_url) for d in docs] == [
        (1, "第一話", "https://ncode.syosetu.com/n1/1/"), (2, "Ch", ""),
        (3, "第三話", "https://ncode.syosetu.com/n1/3/")]


def test_a_failing_chapter_does_not_stop_the_rest(app_client, me, make_series, site, db):
    pages, _ = site
    del pages["https://ncode.syosetu.com/n1/2/"]
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    db.flush()
    jid = app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [1, 2, 3]}).json()["id"]
    jobs.run_next()
    result = app_client.get(f"/jobs/{jid}").json()["result"]
    assert result["added"] == 2 and [e["num"] for e in result["errors"]] == [2]


def test_cancel_mid_fetch_keeps_what_was_fetched(
        app_client, me, make_series, site, db, monkeypatch):
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    db.flush()
    jid = app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [1, 2, 3]}).json()["id"]
    original = jobs.JobContext.progress

    def cancel_after_first_chapter(self, done, total, message=""):
        if done == 1:
            self.job.cancel_requested = True
        original(self, done, total, message)
    monkeypatch.setattr(jobs.JobContext, "progress", cancel_after_first_chapter)
    jobs.run_next()
    assert app_client.get(f"/jobs/{jid}").json()["state"] == "cancelled"
    assert db.query(Document).filter_by(series_id=s.id).count() == 1


def test_fetch_needs_a_series_url_and_your_series(app_client, me, make_series, make_user, site):
    mine = make_series(me, "No URL")
    url = "/syosetu/fetch"
    assert app_client.post(f"/series/{mine.id}{url}", json={"nums": [1]}).status_code == 422
    theirs = make_series(make_user(email="o@example.com"), "T")
    assert app_client.post(f"/series/{theirs.id}{url}", json={"nums": [1]}).status_code == 404
    assert app_client.get(f"/series/{theirs.id}/syosetu/chapters").status_code == 404


def test_refetch_replaces_source_and_keeps_translations_by_position(
        app_client, me, make_doc, site, db):
    doc = make_doc(me, ["古い"], translated=True)
    doc.source_url = "https://ncode.syosetu.com/n1/1/"
    db.flush()
    # The desktop prepends the title: "第一話", a blank line, then the text — 3 lines, not 1.
    assert app_client.post(f"/documents/{doc.id}/refetch", json={}).status_code == 409
    r = app_client.post(f"/documents/{doc.id}/refetch", json={"force": True})
    assert r.status_code == 200
    lines = app_client.get(f"/documents/{doc.id}/lines").json()["lines"]
    assert [ln["raw_text"] for ln in lines][0] == "第一話"


def test_refetch_without_source_url_is_422(app_client, me, make_doc):
    doc = make_doc(me, ["x"])
    assert app_client.post(f"/documents/{doc.id}/refetch", json={}).status_code == 422
