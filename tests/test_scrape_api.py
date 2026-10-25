from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from api import fetch_job, jobs
from api.core import scrape
from api.models import Document, Volume, VolumeSyosetuGroup
from api.routers import scrape as scrape_router

INDEX = ('<div class="p-eplist__sublist"><a href="/n1/1/">One</a></div>'
         '<div class="p-eplist__sublist"><a href="/n1/2/">Two</a></div>'
         '<div class="p-eplist__sublist"><a href="/n1/3/">Three</a></div>')

DATED = ('<div class="p-eplist__sublist"><a href="/n1/1/">One</a>'
         '<div class="p-eplist__update">2024/01/02 09:00</div></div>'
         '<div class="p-eplist__sublist"><a href="/n1/2/">Two</a>'
         '<div class="p-eplist__update">2024/03/04 18:30 <span title="2025/05/06 07:00 改稿">'
         '（<u>改稿</u>）</span></div></div>'
         '<div class="p-eplist__sublist"><a href="/n1/3/">Three</a></div>')
NEWEST = datetime(2024, 3, 4, 18, 30, tzinfo=ZoneInfo("Asia/Tokyo"))

SERIAL_ROOT = ('<h1 class="p-novel__title">勇者の旅</h1>'
               '<div class="p-novel__author">作者：<a href="/u/1/">山田太郎</a></div>'
               + INDEX)
SHORT_ROOT = ('<h1 class="p-novel__title">一夜の話</h1>'
              '<div class="p-novel__author">作者：<a href="/u/2/">鈴木</a></div>'
              '<div class="js-novel-text p-novel__text"><p>本文一行目</p></div>')


def chapter(title, body):
    return (f'<h1 class="p-novel__title p-novel__title--rensai">{title}</h1>'
            f'<div class="js-novel-text p-novel__text"><p>{body}</p></div>')


@pytest.fixture
def site(monkeypatch, db):
    """Serve fake syosetu pages; route the worker's sessions to the test db."""
    pages = {"https://ncode.syosetu.com/n1/": INDEX,
             "https://ncode.syosetu.com/n1/1/": chapter("第一話", "一行目です。"),
             "https://ncode.syosetu.com/n1/2/": chapter("第二話", "二行目です。"),
             "https://ncode.syosetu.com/n1/3/": chapter("第三話", "三行目です。"),
             "https://ncode.syosetu.com/n7696mg/": SERIAL_ROOT,
             "https://ncode.syosetu.com/n0001aa/": SHORT_ROOT,
             "https://ncode.syosetu.com/n0000zz/": "<html></html>"}
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
    body = app_client.get(f"/series/{s.id}/syosetu/chapters").json()["chapters"]
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
    docs = db.query(Document).filter_by(series_id=s.id).order_by(Document.series_order).all()
    assert job["result"] == {"added": 2, "skipped": 1, "errors": [], "missing": [99],
                             "document_ids": [docs[0].id, docs[2].id]}
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


@pytest.fixture
def busy():
    """Hold both request slots, as two slow syosetu requests would."""
    assert scrape_router.syosetu_slots.acquire(blocking=False)
    assert scrape_router.syosetu_slots.acquire(blocking=False)
    yield
    scrape_router.syosetu_slots.release()
    scrape_router.syosetu_slots.release()


def test_request_paths_are_503_while_syosetu_is_busy(
        app_client, me, make_series, make_doc, site, db, busy):
    _, calls = site
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    doc = make_doc(me, ["x"])
    doc.source_url = "https://ncode.syosetu.com/n1/1/"
    db.flush()
    for r in (app_client.post("/scrape/syosetu", json={"url": "https://ncode.syosetu.com/n1/1/"}),
              app_client.get(f"/series/{s.id}/syosetu/chapters"),
              app_client.post(f"/documents/{doc.id}/refetch", json={})):
        assert r.status_code == 503 and "busy" in r.json()["detail"]
    assert calls == []


def test_request_slots_are_released_after_errors(app_client, me, site):
    for _ in range(3):
        bad = app_client.post("/scrape/syosetu", json={"url": "https://ncode.syosetu.com/n1/9/"})
        assert bad.status_code == 502
    assert app_client.post(
        "/scrape/syosetu", json={"url": "https://ncode.syosetu.com/n1/1/"}).status_code == 200


@pytest.mark.parametrize("url", ["https://ncode.syosetu.com/n1/\t1/",
                                 "https://ncode.syosetu.com/n1/\x001/",
                                 "http://ｅvil.syosetu.com/"])
def test_malformed_urls_are_422_not_500(app_client, me, site, url):
    _, calls = site
    r = app_client.post("/scrape/syosetu", json={"url": url})
    assert r.status_code == 422 and calls == []


def test_a_second_fetch_job_for_the_same_series_is_409(app_client, me, make_series, site, db):
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    other = make_series(me, "O")
    other.syosetu_url = "https://ncode.syosetu.com/n1/"
    db.flush()
    url = f"/series/{s.id}/syosetu/fetch"
    assert app_client.post(url, json={"nums": [1]}).status_code == 202
    assert app_client.post(url, json={"nums": [2]}).status_code == 409
    other_url = f"/series/{other.id}/syosetu/fetch"
    assert app_client.post(other_url, json={"nums": [1]}).status_code == 202
    jobs.run_next()
    jobs.run_next()
    assert app_client.post(url, json={"nums": [2]}).status_code == 202


GROUPED = ('<div class="p-eplist__sublist"><a href="/n1/1/">One</a></div>'
           '<div class="p-eplist__chapter-title">第一章</div>'
           '<div class="p-eplist__sublist"><a href="/n1/2/">Two</a></div>'
           '<div class="p-eplist__chapter-title">第二章</div>'
           '<div class="p-eplist__sublist"><a href="/n1/3/">Three</a></div>')


def _grouped_series(make_series, site, db, me):
    pages, _ = site
    pages["https://ncode.syosetu.com/n1/"] = GROUPED
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    db.flush()
    return s


def _fetch(app_client, s, nums):
    app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": nums})
    assert jobs.run_next() is True


def _placement(db, s):
    docs = db.query(Document).filter_by(series_id=s.id).order_by(Document.series_order).all()
    return [(d.series_order, d.volume_id and db.get(Volume, d.volume_id).label) for d in docs]


def test_chapter_list_reports_groups(app_client, me, make_series, site, db):
    s = _grouped_series(make_series, site, db, me)
    body = app_client.get(f"/series/{s.id}/syosetu/chapters").json()["chapters"]
    assert [c["group"] for c in body] == [None, "第一章", "第二章"]


def test_fetch_puts_grouped_chapters_into_volumes_in_order(
        app_client, me, make_series, site, db):
    s = _grouped_series(make_series, site, db, me)
    _fetch(app_client, s, [1, 2, 3])
    assert _placement(db, s) == [(1, None), (2, "第一章"), (3, "第二章")]
    vols = db.query(Volume).filter_by(series_id=s.id).order_by(Volume.volume_order).all()
    assert [(v.kind, v.volume_index, v.subtitle) for v in vols] == [
        ("", None, "第一章"), ("", None, "第二章")]
    assert db.query(VolumeSyosetuGroup).filter_by(series_id=s.id).count() == 2
    assert "syosetu_group" not in app_client.get(f"/series/{s.id}/volumes").text


def test_a_renamed_group_volume_still_receives_its_chapters(
        app_client, me, make_series, site, db):
    s = _grouped_series(make_series, site, db, me)
    _fetch(app_client, s, [2])
    vol = db.query(Volume).filter_by(series_id=s.id).one()
    assert app_client.patch(f"/volumes/{vol.id}", json={"subtitle": "Arc 1"}).status_code == 200
    pages, _ = site
    pages["https://ncode.syosetu.com/n1/"] = GROUPED.replace(
        '<div class="p-eplist__chapter-title">第二章</div>', "")
    _fetch(app_client, s, [3])
    assert _placement(db, s) == [(2, "Arc 1"), (3, "Arc 1")]


def test_a_group_whose_title_is_taken_gets_a_suffix(app_client, me, make_series, site, db):
    s = _grouped_series(make_series, site, db, me)
    db.add(Volume(series_id=s.id, kind="", subtitle="第一章", volume_order=1))
    db.flush()
    _fetch(app_client, s, [2])
    assert _placement(db, s) == [(2, "第一章 (2)")]


def test_chapters_already_fetched_are_not_moved(
        app_client, me, make_series, make_doc, site, db):
    s = _grouped_series(make_series, site, db, me)
    make_doc(me, ["x"], series=s, order=2)
    db.flush()
    _fetch(app_client, s, [2, 3])
    assert _placement(db, s) == [(2, None), (3, "第二章")]


MARKED = ('<div class="p-eplist__chapter-title">★ 一日</div>'
          '<div class="p-eplist__sublist"><a href="/n1/1/">One</a></div>'
          '<div class="p-eplist__chapter-title">◇ 編</div>'
          '<div class="p-eplist__sublist"><a href="/n1/2/">Two</a></div>'
          '<div class="p-eplist__chapter-title">★ 二日</div>'
          '<div class="p-eplist__sublist"><a href="/n1/3/">Three</a></div>')


def _marked_series(make_series, site, db, me, mode="all", marker=""):
    s = _grouped_series(make_series, site, db, me)
    site[0]["https://ncode.syosetu.com/n1/"] = MARKED
    s.syosetu_volume_mode, s.syosetu_volume_marker = mode, marker
    db.flush()
    return s


def test_marker_mode_folds_other_headings_into_the_previous_volume(
        app_client, me, make_series, site, db):
    s = _marked_series(make_series, site, db, me, "marker", "★")
    _fetch(app_client, s, [2, 3])
    assert _placement(db, s) == [(2, "★ 一日"), (3, "★ 二日")]
    db.refresh(s)
    assert s.syosetu_headings == [[1, "★ 一日"], [2, "◇ 編"], [3, "★ 二日"]]


def test_off_creates_no_volumes(app_client, me, make_series, site, db):
    s = _marked_series(make_series, site, db, me, "off")
    _fetch(app_client, s, [1, 2, 3])
    assert _placement(db, s) == [(1, None), (2, None), (3, None)]
    assert db.query(Volume).filter_by(series_id=s.id).count() == 0


def test_marker_mode_with_no_starting_heading_creates_no_volumes(
        app_client, me, make_series, site, db):
    s = _marked_series(make_series, site, db, me, "marker", "◎")
    _fetch(app_client, s, [1, 2, 3])
    assert _placement(db, s) == [(1, None), (2, None), (3, None)]


def test_chapter_list_reports_markers(app_client, me, make_series, site, db):
    s = _marked_series(make_series, site, db, me)
    body = app_client.get(f"/series/{s.id}/syosetu/chapters").json()
    assert body["markers"] == [{"marker": "★", "headings": 2}]
    assert [c["group"] for c in body["chapters"]] == ["★ 一日", "◇ 編", "★ 二日"]
    db.refresh(s)
    assert s.syosetu_headings is None


def test_heading_volume_is_unnamed_kind(app_client, me, make_series, site, db):
    s = _grouped_series(make_series, site, db, me)
    db.add(Volume(series_id=s.id, kind="Volume", volume_index=1, volume_order=1))
    db.flush()
    _fetch(app_client, s, [2, 3])
    vols = db.query(Volume).filter_by(series_id=s.id).order_by(Volume.volume_order).all()
    assert [(v.kind, v.volume_index and int(v.volume_index), v.subtitle) for v in vols] == [
        ("Volume", 1, ""), ("", None, "第一章"), ("", None, "第二章")]


def test_a_taken_heading_title_is_suffixed_in_arc_order(app_client, me, make_series, site, db):
    s = _grouped_series(make_series, site, db, me)
    db.add(Volume(series_id=s.id, kind="", subtitle="第一章", volume_order=1))
    db.flush()
    _fetch(app_client, s, [2, 3])
    vols = db.query(Volume).filter_by(series_id=s.id).order_by(Volume.volume_order).all()
    assert [v.subtitle for v in vols] == ["第一章", "第一章 (2)", "第二章"]


def test_novel_read_serial(app_client, me, site):
    r = app_client.post("/scrape/syosetu/novel", json={"url": "https://ncode.syosetu.com/n7696mg/"})
    assert r.status_code == 200
    assert r.json() == {"title": "勇者の旅", "author": "山田太郎", "short_story": False,
                        "first_chapter": {"num": 1, "title": "One"}}


def test_novel_read_short_story(app_client, me, site):
    r = app_client.post("/scrape/syosetu/novel", json={"url": "https://ncode.syosetu.com/n0001aa/"})
    assert r.status_code == 200
    body = r.json()
    assert body["short_story"] is True and body["first_chapter"]["num"] == 1


@pytest.mark.parametrize("url", ["https://ncode.syosetu.com/n7696mg/1/",
                                 "https://example.com/n7696mg/"])
def test_novel_read_refuses_chapter_and_foreign_urls(app_client, me, site, url):
    assert app_client.post("/scrape/syosetu/novel", json={"url": url}).status_code == 422


def test_novel_read_with_nothing_is_422(app_client, me, site, db):
    from api.models import Series
    r = app_client.post("/scrape/syosetu/novel", json={"url": "https://ncode.syosetu.com/n0000zz/"})
    assert r.status_code == 422
    assert db.query(Series).count() == 0


def test_novel_read_upstream_failure_is_502(app_client, me, site):
    r = app_client.post("/scrape/syosetu/novel", json={"url": "https://ncode.syosetu.com/n9999/"})
    assert r.status_code == 502


def test_fetch_job_reports_document_ids(app_client, me, make_series, site, db):
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    db.flush()
    jid = app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [1]}).json()["id"]
    jobs.run_next()
    doc = db.query(Document).filter_by(series_id=s.id).one()
    assert app_client.get(f"/jobs/{jid}").json()["result"]["document_ids"] == [doc.id]


def _short_series(me, make_series, db):
    s = make_series(me, "Short")
    s.syosetu_url = "https://ncode.syosetu.com/n0001aa/"
    db.flush()
    return s


def test_short_story_fetch_creates_one_chapter(app_client, me, make_series, site, db):
    s = _short_series(me, make_series, db)
    app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [1]})
    jobs.run_next()
    doc = db.query(Document).filter_by(series_id=s.id).one()
    assert (doc.series_order, doc.title, doc.source_url) == (
        1, "一夜の話", "https://ncode.syosetu.com/n0001aa/")
    lines = app_client.get(f"/documents/{doc.id}/lines").json()["lines"]
    assert "本文一行目" in [ln["raw_text"] for ln in lines]
    chapters = app_client.get(f"/series/{s.id}/syosetu/chapters").json()["chapters"]
    assert [(c["num"], c["fetched"]) for c in chapters] == [(1, True)]


def test_short_story_fetch_is_idempotent(app_client, me, make_series, site, db):
    s = _short_series(me, make_series, db)
    for _ in range(2):
        jid = app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [1]}).json()["id"]
        jobs.run_next()
    result = app_client.get(f"/jobs/{jid}").json()["result"]
    assert result["added"] == 0 and result["skipped"] == 1
    assert db.query(Document).filter_by(series_id=s.id).count() == 1


def test_short_story_without_a_title_falls_back_to_chapter_1(
        app_client, me, make_series, site, db):
    pages, _ = site
    pages["https://ncode.syosetu.com/n0001aa/"] = (
        '<div class="js-novel-text p-novel__text"><p>本文</p></div>')
    s = _short_series(me, make_series, db)
    app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [1]})
    jobs.run_next()
    assert db.query(Document).filter_by(series_id=s.id).one().title == "Chapter 1"


def test_chapter_list_records_the_latest_post_date(app_client, me, make_series, site, db):
    site[0]["https://ncode.syosetu.com/n1/"] = DATED
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    db.flush()
    assert app_client.get(f"/series/{s.id}/syosetu/chapters").status_code == 200
    db.refresh(s)
    assert s.syosetu_updated_at == NEWEST
    assert s.syosetu_headings is None


def test_fetch_job_records_the_latest_post_date(app_client, me, make_series, site, db):
    site[0]["https://ncode.syosetu.com/n1/"] = DATED
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    db.flush()
    app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [1]})
    assert jobs.run_next() is True
    db.refresh(s)
    assert s.syosetu_updated_at == NEWEST


def test_a_read_with_no_dates_keeps_the_stored_date(app_client, me, make_series, site, db):
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    s.syosetu_updated_at = NEWEST
    db.flush()
    assert app_client.get(f"/series/{s.id}/syosetu/chapters").status_code == 200
    db.refresh(s)
    assert s.syosetu_updated_at == NEWEST
