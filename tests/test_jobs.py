from contextlib import contextmanager

import pytest

from api import jobs


@pytest.fixture
def in_test_db(monkeypatch, db):
    """Run the worker against the test transaction. db joins it with
    create_savepoint, so the worker's commits only release savepoints."""
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    return db


@pytest.fixture
def kind(monkeypatch):
    """Register throwaway handlers for one test."""
    def register(name, fn):
        monkeypatch.setitem(jobs.HANDLERS, name, fn)
    return register


def test_a_job_runs_once_and_records_its_result(in_test_db, make_user, kind):
    user = make_user(email="j@example.com")
    kind("echo", lambda ctx: {"got": ctx.params["x"]})
    job = jobs.enqueue(in_test_db, user.id, "echo", {"x": 7})
    assert jobs.run_next() is True
    assert jobs.run_next() is False
    in_test_db.refresh(job)
    assert (job.state, job.result_json) == ("done", {"got": 7})
    assert job.started_at and job.finished_at


def test_cancel_stops_at_the_next_progress_point_keeping_the_work(
    in_test_db, make_user, make_series, kind
):
    from api.models import Series
    user = make_user(email="j@example.com")
    series = make_series(user, "Kept")

    def work(ctx):
        ctx.progress(1, 3, "first")
        ctx.job.cancel_requested = True     # what POST /jobs/{id}/cancel does, from another session
        ctx.db.get(Series, series.id).syosetu_url = "https://ncode.syosetu.com/n1/"
        ctx.progress(2, 3, "second")        # commits the work so far, then raises Cancelled
        raise AssertionError("not reached")

    kind("three", work)
    job = jobs.enqueue(in_test_db, user.id, "three", {})
    jobs.run_next()
    in_test_db.refresh(job)
    assert (job.state, job.progress, job.message) == ("cancelled", 2, "second")
    in_test_db.refresh(series)
    assert series.syosetu_url == "https://ncode.syosetu.com/n1/"


def test_a_failing_handler_fails_the_job_with_a_safe_message(in_test_db, make_user, kind):
    user = make_user(email="j@example.com")

    def boom(ctx):
        raise RuntimeError("secret internals")

    def refused(ctx):
        raise jobs.JobError("the series no longer exists")

    kind("boom", boom)
    kind("refused", refused)
    a = jobs.enqueue(in_test_db, user.id, "boom", {})
    b = jobs.enqueue(in_test_db, user.id, "refused", {})
    jobs.run_next()
    jobs.run_next()
    in_test_db.refresh(a)
    in_test_db.refresh(b)
    assert (a.state, a.message) == ("failed", "boom failed")
    assert (b.state, b.message) == ("failed", "the series no longer exists")


def test_unknown_kind_fails(in_test_db, make_user):
    job = jobs.enqueue(in_test_db, make_user(email="j@example.com").id, "nope", {})
    jobs.run_next()
    in_test_db.refresh(job)
    assert job.state == "failed"


def test_restart_fails_jobs_left_running(in_test_db, make_user):
    job = jobs.enqueue(in_test_db, make_user(email="j@example.com").id, "x", {})
    job.state = "running"
    in_test_db.flush()
    assert jobs.fail_interrupted() == 1
    in_test_db.refresh(job)
    assert job.state == "failed" and "restart" in job.message


def test_shutdown_interrupts_at_the_next_progress_point(in_test_db, make_user, kind, monkeypatch):
    monkeypatch.setattr(jobs, "stopping", __import__("threading").Event())
    jobs.stopping.set()
    kind("long", lambda ctx: ctx.progress(1, 9) or {})
    job = jobs.enqueue(in_test_db, make_user(email="j@example.com").id, "long", {})
    jobs.run_next()
    in_test_db.refresh(job)
    assert job.state == "failed" and "start it again" in job.message


async def test_worker_stops_when_asked(in_test_db):
    import asyncio
    stop = asyncio.Event()
    task = asyncio.create_task(jobs.worker(stop, idle=0.01))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, 2)


def test_a_job_deleted_while_running_ends_quietly(in_test_db, make_user, kind, caplog):
    from sqlalchemy import delete

    from api.models import Job
    user = make_user(email="j@example.com")

    def vanish(ctx):
        ctx.db.execute(delete(Job).where(Job.id == ctx.job.id))  # the user-delete cascade
        ctx.progress(1, 1)
        return {}

    kind("vanish", vanish)
    jobs.enqueue(in_test_db, user.id, "vanish", {})
    assert jobs.run_next() is True
    assert "failed" not in caplog.text
    assert jobs.run_next() is False
