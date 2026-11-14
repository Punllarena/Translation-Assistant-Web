from contextlib import contextmanager
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from api import jobs, syosetu_nightly
from api.core import scrape
from api.models import Job

URL = "https://ncode.syosetu.com/n1/"
INDEX = "".join(f'<div class="p-eplist__sublist"><a href="/n1/{n}/">Ch {n}</a></div>'
                for n in (1, 2, 3))


@pytest.fixture
def site(monkeypatch, db):
    pages = {URL: INDEX}

    def handle(request):
        html = pages.get(str(request.url))
        return httpx.Response(200 if html else 404, text=html or "")

    monkeypatch.setattr(syosetu_nightly, "http_client",
                        lambda: scrape.client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(scrape, "throttle", lambda delay: None)

    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    return pages


@pytest.fixture
def series(db, make_series, make_doc, me):
    """make(mark, orders=(), **fields) -> an eligible syosetu series holding chapters `orders`."""
    def make(mark=0, orders=(), title="S", **fields):
        s = make_series(me, title=title)
        s.syosetu_url, s.syosetu_fetched_through = URL, mark
        for k, v in fields.items():
            setattr(s, k, v)
        for n in orders:
            make_doc(me, [f"line {n}"], series=s, order=n, title=f"Ch {n}")
        db.flush()
        return s
    return make


def run_nightly(db, user):
    job = jobs.enqueue(db, user.id, "syosetu_nightly", {"day": "2026-11-15"})
    db.flush()
    assert jobs.run_next() is True
    db.refresh(job)
    return job


def fetches(db, user):
    return db.scalars(select(Job).where(Job.user_id == user.id, Job.kind == "syosetu_fetch")
                      .order_by(Job.id)).all()


def test_queues_chapters_above_the_mark(db, me, site, series):
    s = series(mark=1, orders=(1,))
    job = run_nightly(db, me)
    assert job.state == "done"
    [fetch] = fetches(db, me)
    assert fetch.params_json == {"series_id": s.id, "nums": [2, 3]} and fetch.total == 2
    assert job.result_json["queued"] == [
        {"series_id": s.id, "title": "S", "chapters": 2, "job_id": fetch.id}]
    assert job.result_json["checked"] == 1
    assert job.message == "1 series checked, 1 with new chapters, 0 failed"


def test_deleted_top_chapters_are_not_fetched(db, me, site, series):
    series(mark=3, orders=(1,))
    run_nightly(db, me)
    assert fetches(db, me) == []


def test_series_order_counts_without_a_mark(db, me, site, series):
    s = series(mark=0, orders=(1, 2))
    run_nightly(db, me)
    assert fetches(db, me)[0].params_json == {"series_id": s.id, "nums": [3]}


def test_a_series_with_no_chapters_gets_everything(db, me, site, series):
    series(mark=0)
    run_nightly(db, me)
    assert fetches(db, me)[0].params_json["nums"] == [1, 2, 3]


def test_a_null_mark_is_seeded_and_queues_nothing(db, me, site, series):
    s = series(mark=None, orders=(1,))
    job = run_nightly(db, me)
    db.refresh(s)
    assert s.syosetu_fetched_through == 3 and fetches(db, me) == []
    assert job.result_json["checked"] == 1 and job.result_json["queued"] == []


def test_removed_chapters_never_lower_the_mark(db, me, site, series):
    s = series(mark=5, orders=(1,))
    run_nightly(db, me)
    db.refresh(s)
    assert s.syosetu_fetched_through == 5 and fetches(db, me) == []


def test_date_checked_and_headings_refreshed(db, me, site, series):
    s = series(mark=3, syosetu_check_error="old")
    run_nightly(db, me)
    db.refresh(s)
    assert s.syosetu_check_error == "" and s.syosetu_checked_at is not None
    assert s.syosetu_headings is not None


def test_a_failure_is_recorded_and_the_others_still_run(db, me, site, series):
    bad = series(mark=0, title="Bad")
    bad.syosetu_url = "https://ncode.syosetu.com/n404/"
    good = series(mark=0, title="Good")
    db.flush()
    job = run_nightly(db, me)
    db.refresh(bad)
    assert bad.syosetu_check_error != ""
    assert [f["series_id"] for f in job.result_json["failed"]] == [bad.id]
    assert [f.params_json["series_id"] for f in fetches(db, me)] == [good.id]
    assert job.message == "1 series checked, 1 with new chapters, 1 failed"


def test_a_refused_url_is_recorded_not_raised(db, me, site, series):
    s = series(mark=0)
    s.syosetu_url = "https://example.com/x/"
    db.flush()
    job = run_nightly(db, me)
    db.refresh(s)
    assert job.state == "done" and s.syosetu_check_error != ""


def test_a_busy_series_is_skipped(db, me, site, series):
    s = series(mark=0)
    jobs.enqueue(db, me.id, "syosetu_fetch", {"series_id": s.id, "nums": [1]})
    db.flush()
    job = jobs.enqueue(db, me.id, "syosetu_nightly", {"day": "2026-11-15"})
    db.flush()
    from api.jobs import JobContext
    result = syosetu_nightly.nightly(JobContext(db, job))
    assert result["busy"] == 1 and result["checked"] == 0
    assert len(fetches(db, me)) == 1


@pytest.mark.parametrize("fields", [
    {"archived_at": datetime(2026, 1, 1, tzinfo=UTC)}, {"status": "on_hold"},
    {"syosetu_nightly": False}, {"syosetu_url": ""}])
def test_ineligible_at_run_time_is_skipped(db, me, site, series, fields):
    series(mark=0, **fields)
    job = run_nightly(db, me)
    assert job.result_json["checked"] == 0 and fetches(db, me) == []


def test_other_users_series_are_untouched(db, me, site, series, make_user, make_series):
    other = make_user(email="other@example.com")
    theirs = make_series(other, title="Theirs")
    theirs.syosetu_url, theirs.syosetu_fetched_through = URL, 0
    db.flush()
    run_nightly(db, me)
    assert fetches(db, other) == []


def test_cancel_stops_before_any_series(db, me, site, series):
    series(mark=0)
    job = jobs.enqueue(db, me.id, "syosetu_nightly", {"day": "2026-11-15"})
    job.cancel_requested = True
    db.flush()
    jobs.run_next()
    db.refresh(job)
    assert job.state == "cancelled" and fetches(db, me) == []


def test_the_app_registers_the_handler():
    import api.main  # noqa: F401
    assert "syosetu_nightly" in jobs.HANDLERS


# --- the tick ---------------------------------------------------------------

def nightly_jobs(db):
    return db.scalars(select(Job).where(Job.kind == "syosetu_nightly")).all()


@pytest.fixture
def settings(monkeypatch):
    """settings(**env) sets TA_SYOSETU_NIGHTLY_* for this test (no .env, cache cleared)."""
    from api.config import Settings, get_settings
    monkeypatch.setitem(Settings.model_config, "env_file", None)

    def apply(**env):
        for k, v in env.items():
            monkeypatch.setenv(f"TA_SYOSETU_NIGHTLY_{k.upper()}", v)
        get_settings.cache_clear()
    apply()
    yield apply
    get_settings.cache_clear()


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_tick_disabled_or_early_queues_nothing(db, me, series, settings):
    series(mark=0)
    syosetu_nightly.tick(db, at("2026-11-15T03:59"))
    assert nightly_jobs(db) == []
    settings(enabled="false")
    syosetu_nightly.tick(db, at("2026-11-15T04:00"))
    assert nightly_jobs(db) == []


def test_tick_queues_once_per_user_per_day(db, me, series, settings):
    series(mark=0)
    syosetu_nightly.tick(db, at("2026-11-15T04:00"))
    [job] = nightly_jobs(db)
    assert job.user_id == me.id and job.params_json == {"day": "2026-11-15"}
    syosetu_nightly.tick(db, at("2026-11-15T05:00"))
    job.state = "failed"
    db.flush()
    syosetu_nightly.tick(db, at("2026-11-15T23:59"))
    assert len(nightly_jobs(db)) == 1
    syosetu_nightly.tick(db, at("2026-11-16T04:00"))
    assert len(nightly_jobs(db)) == 2


def test_tick_skips_users_without_eligible_series(db, me, series, settings):
    series(mark=0, status="dropped")
    syosetu_nightly.tick(db, at("2026-11-15T04:00"))
    assert nightly_jobs(db) == []


def test_tick_uses_the_local_date(db, me, series, settings):
    settings(tz="Asia/Tokyo", time="05:00")
    series(mark=0)
    syosetu_nightly.tick(db, at("2026-11-14T19:59"))  # 04:59 in Tokyo
    assert nightly_jobs(db) == []
    syosetu_nightly.tick(db, at("2026-11-14T20:00"))  # 05:00 on the 15th in Tokyo
    assert [j.params_json for j in nightly_jobs(db)] == [{"day": "2026-11-15"}]


@pytest.mark.parametrize("env", [{"time": "25:00"}, {"tz": "Nowhere/Land"}])
def test_tick_with_a_bad_env_value_does_nothing(db, me, series, settings, env):
    settings(**env)
    series(mark=0)
    syosetu_nightly.tick(db, at("2026-11-15T12:00"))
    assert nightly_jobs(db) == []


def test_ticker_runs_ollama_even_if_syosetu_fails(monkeypatch, db):
    from api import ticker
    from api.ollama import schedule
    calls = []
    monkeypatch.setattr(ticker, "SessionLocal", lambda: contextmanager(lambda: (yield db))())

    def boom(db, now):
        raise RuntimeError("boom")
    monkeypatch.setattr(syosetu_nightly, "tick", boom)
    monkeypatch.setattr(schedule, "tick", lambda db, now: calls.append(now))
    ticker._tick_once()
    assert len(calls) == 1
