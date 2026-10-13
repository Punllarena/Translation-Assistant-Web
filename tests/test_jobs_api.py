import json
from contextlib import contextmanager

import pytest

from api import jobs
from api.routers import jobs as jobs_router


@pytest.fixture
def same_db(monkeypatch, db):
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    monkeypatch.setattr(jobs_router, "SessionLocal", session)
    monkeypatch.setattr(jobs_router, "POLL_SECONDS", 0)
    return db


def frames(body: str):
    return [json.loads(f.split("data: ", 1)[1]) for f in body.strip().split("\n\n")]


def test_list_get_and_filters(app_client, db, me):
    a = jobs.enqueue(db, me.id, "syosetu_fetch", {"series_id": 1})
    b = jobs.enqueue(db, me.id, "syosetu_fetch", {"series_id": 2})
    b.state = "done"
    db.flush()
    assert [j["id"] for j in app_client.get("/jobs").json()] == [b.id, a.id]
    assert [j["id"] for j in app_client.get("/jobs?active=true").json()] == [a.id]
    assert [j["id"] for j in app_client.get("/jobs?series_id=2").json()] == [b.id]
    assert app_client.get(f"/jobs/{a.id}").json()["params"] == {"series_id": 1}


def test_cancel_queued_is_immediate_running_is_requested(app_client, db, me):
    queued = jobs.enqueue(db, me.id, "x", {})
    running = jobs.enqueue(db, me.id, "x", {})
    running.state = "running"
    db.flush()
    assert app_client.post(f"/jobs/{queued.id}/cancel").json()["state"] == "cancelled"
    body = app_client.post(f"/jobs/{running.id}/cancel").json()
    assert body["state"] == "running"
    db.refresh(running)
    assert running.cancel_requested is True


def test_events_stream_until_terminal(app_client, db, me, same_db, monkeypatch):
    job = jobs.enqueue(db, me.id, "x", {})
    job.state, job.progress, job.total = "done", 3, 3
    db.flush()
    seen = frames(app_client.get(f"/jobs/{job.id}/events").text)
    assert seen[-1]["state"] == "done" and seen[-1]["progress"] == 3


def test_other_users_job_is_404_everywhere(app_client, db, me, make_user):
    theirs = jobs.enqueue(db, make_user(email="o@example.com").id, "x", {})
    for method, path in [("get", f"/jobs/{theirs.id}"), ("post", f"/jobs/{theirs.id}/cancel"),
                         ("get", f"/jobs/{theirs.id}/events")]:
        assert getattr(app_client, method)(path).status_code == 404
    assert app_client.get("/jobs").json() == []


def test_events_send_keepalive_comments_while_nothing_changes(app_client, db, me, same_db,
                                                              monkeypatch):
    job = jobs.enqueue(db, me.id, "noop", {})
    states = iter(["running", "running", "running", "done"])
    real = jobs_router._snapshot

    def scripted(job_id):
        snap = real(job_id)
        return {**snap, "state": next(states)}
    monkeypatch.setattr(jobs_router, "_snapshot", scripted)
    monkeypatch.setattr(jobs_router, "KEEPALIVE_SECONDS", 0)
    body = app_client.get(f"/jobs/{job.id}/events").text
    assert ": keepalive\n\n" in body
    assert [f["state"] for f in frames(body.replace(": keepalive\n\n", ""))] == ["running", "done"]


def test_events_end_when_the_job_row_disappears(app_client, db, me, same_db, monkeypatch):
    job = jobs.enqueue(db, me.id, "syosetu_fetch", {"series_id": 1})
    calls = {"n": 0}
    real = jobs_router._snapshot

    def snapshot(job_id):
        calls["n"] += 1
        return real(job_id) if calls["n"] == 1 else None

    monkeypatch.setattr(jobs_router, "_snapshot", snapshot)
    body = app_client.get(f"/jobs/{job.id}/events").text
    assert len(frames(body)) == 1
