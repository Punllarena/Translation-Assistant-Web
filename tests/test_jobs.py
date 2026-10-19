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
        ctx.db.commit()  # durable, as another session's committed cascade is
        ctx.progress(1, 1)
        return {}

    kind("vanish", vanish)
    jobs.enqueue(in_test_db, user.id, "vanish", {})
    assert jobs.run_next() is True
    assert "failed" not in caplog.text
    assert jobs.run_next() is False


def test_a_handler_bug_raising_invalid_request_error_still_fails_the_job(
    in_test_db, make_user, kind
):
    from sqlalchemy.exc import InvalidRequestError
    user = make_user(email="j@example.com")

    def boom(ctx):
        raise InvalidRequestError("boom")

    kind("boom", boom)
    job = jobs.enqueue(in_test_db, user.id, "boom", {})
    assert jobs.run_next() is True
    in_test_db.refresh(job)
    assert (job.state, job.message) == ("failed", "boom failed")


def _row(ctx):
    from api.models import Job
    with jobs.progress_session() as s:
        job = s.get(Job, ctx.job.id, populate_existing=True)
        return (job.progress, job.total, job.message)


def test_report_writes_the_job_row_and_is_throttled(in_test_db, make_user, kind, monkeypatch):
    clock = iter([100.0, 100.5, 101.6, 101.7])
    monkeypatch.setattr(jobs, "_clock", lambda: next(clock))
    seen = []

    def work(ctx):
        # first call writes; 0.5 s later skipped; 1.6 s writes; done == total always writes
        for done, msg in ((1, "a"), (2, "b"), (3, "c"), (10, "d")):
            ctx.report(done, 10, msg)
            seen.append(_row(ctx))
        return {}

    kind("rep", work)
    jobs.enqueue(in_test_db, make_user(email="r@example.com").id, "rep", {})
    jobs.run_next()
    assert seen == [(1, 10, "a"), (1, 10, "a"), (3, 10, "c"), (10, 10, "d")]


def test_report_raises_cancelled_when_cancel_was_requested(in_test_db, make_user, kind):
    from sqlalchemy import update

    from api.models import Job

    def work(ctx):
        ctx.report(1, 2, "half")
        raise AssertionError("not reached")

    kind("rep", work)
    job = jobs.enqueue(in_test_db, make_user(email="r@example.com").id, "rep", {})
    in_test_db.execute(update(Job).where(Job.id == job.id).values(cancel_requested=True))
    jobs.run_next()
    in_test_db.refresh(job)
    assert job.state == "cancelled"


def test_report_does_not_commit_the_work_session(in_test_db, make_user, kind):
    from api.models import Series
    user = make_user(email="r@example.com")

    def work(ctx):
        with ctx.db.begin_nested():
            ctx.db.add(Series(user_id=user.id, title="Uncommitted"))
        ctx.report(1, 1, "done")
        raise jobs.JobError("stop")

    kind("rep", work)
    jobs.enqueue(in_test_db, user.id, "rep", {})
    jobs.run_next()
    assert in_test_db.query(Series).filter_by(title="Uncommitted").count() == 0
