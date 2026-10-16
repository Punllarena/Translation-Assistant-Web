import os
import sqlite3
import time
from contextlib import contextmanager

import pytest

from api import jobs, tadb_uploads
from api.config import get_settings
from api.models import Document
from tests.fixtures.tadb import add_chapter, desktop_db


@pytest.fixture
def env(tmp_path, monkeypatch, db):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path / "data"))

    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    return tmp_path


def upload(client, path):
    with open(path, "rb") as f:
        return client.post("/import/tadb", files={"file": ("ta.db", f)})


def job(client, job_id):
    assert jobs.run_next() is True
    return client.get(f"/jobs/{job_id}").json()


def uploads(env):
    return list((env / "data" / "uploads").glob("*/*.db"))


def test_upload_dry_run_then_import(app_client, me, env, db):
    r = upload(app_client, desktop_db(env / "src"))
    assert r.status_code == 202
    dry = job(app_client, r.json()["job_id"])
    assert dry["state"] == "done"
    assert dry["result"]["dry_run"] is True and dry["result"]["refused"] is None
    assert dry["result"]["written"]["documents"] == 1
    assert db.query(Document).filter_by(user_id=me.id).count() == 0
    run = app_client.post(f"/import/tadb/{r.json()['upload_id']}/run", json={"force": False})
    assert run.status_code == 202
    assert job(app_client, run.json()["id"])["state"] == "done"
    assert db.query(Document).filter_by(user_id=me.id).count() == 1
    assert uploads(env) == []


def test_refusal_is_reported_and_force_overrides(app_client, me, env, db):
    src = desktop_db(env / "src")
    r = upload(app_client, src)
    job(app_client, r.json()["job_id"])
    app_client.post(f"/import/tadb/{r.json()['upload_id']}/run", json={})
    jobs.run_next()
    again = upload(app_client, src)
    dry = job(app_client, again.json()["job_id"])["result"]
    assert "already imported" in dry["refused"]
    plain = app_client.post(f"/import/tadb/{again.json()['upload_id']}/run", json={"force": False})
    assert job(app_client, plain.json()["id"])["state"] == "failed"
    again = upload(app_client, src)
    job(app_client, again.json()["job_id"])
    forced = app_client.post(f"/import/tadb/{again.json()['upload_id']}/run", json={"force": True})
    assert job(app_client, forced.json()["id"])["state"] == "done"


def test_non_empty_account_dry_run_offers_import_anyway(app_client, me, env, db):
    first = upload(app_client, desktop_db(env / "first"))
    job(app_client, first.json()["job_id"])
    app_client.post(f"/import/tadb/{first.json()['upload_id']}/run", json={"force": False})
    jobs.run_next()
    changed = desktop_db(env / "changed")
    add_chapter(changed, "Chapter 2")
    r = upload(app_client, changed)
    dry = job(app_client, r.json()["job_id"])["result"]
    assert dry["refused"].startswith("Your account already has 1 chapter(s)")
    assert dry["written"]["documents"] == 1 and dry["already_present"]["documents"] == 1
    assert not any("force" in m for m in [dry["refused"], *dry["messages"]])
    assert str(env) not in dry["refused"]
    forced = app_client.post(f"/import/tadb/{r.json()['upload_id']}/run", json={"force": True})
    assert job(app_client, forced.json()["id"])["state"] == "done"
    titles = sorted(d.title for d in db.query(Document).filter_by(user_id=me.id))
    assert titles == ["Chapter 1", "Chapter 2"]


def test_already_imported_refusal_has_counts_and_no_server_path(app_client, me, env):
    src = desktop_db(env / "src")
    r = upload(app_client, src)
    job(app_client, r.json()["job_id"])
    app_client.post(f"/import/tadb/{r.json()['upload_id']}/run", json={})
    jobs.run_next()
    again = upload(app_client, src)
    dry = job(app_client, again.json()["job_id"])["result"]
    assert dry["refused"] == "This library was already imported into your account."
    assert dry["already_present"]["documents"] == 1


def test_a_new_upload_replaces_the_pending_one(app_client, me, env):
    first = upload(app_client, desktop_db(env / "a"))
    jobs.run_next()
    second = upload(app_client, desktop_db(env / "b"))
    assert [p.stem for p in uploads(env)] == [second.json()["upload_id"]]
    assert first.json()["upload_id"] != second.json()["upload_id"]


def test_not_sqlite_is_422_and_nothing_is_kept(app_client, me, env):
    bogus = env / "bogus.db"
    bogus.write_bytes(b"hello")
    r = upload(app_client, bogus)
    assert r.status_code == 422
    assert uploads(env) == []


def test_another_sqlite_db_fails_the_dry_run_and_is_deleted(app_client, me, env):
    other = env / "other.db"
    sqlite3.connect(other).executescript("CREATE TABLE t (x); INSERT INTO t VALUES (1);")
    r = upload(app_client, other)
    dry = job(app_client, r.json()["job_id"])
    assert dry["state"] == "failed" and "not a desktop ta.db" in dry["message"]
    assert uploads(env) == []


def test_too_large_is_413_with_no_partial_file(app_client, me, env, monkeypatch):
    monkeypatch.setattr(tadb_uploads, "MAX_TADB_BYTES", 100)
    r = upload(app_client, desktop_db(env / "src"))
    assert r.status_code == 413
    assert uploads(env) == []


def test_second_upload_while_a_job_is_active_is_409(app_client, me, env):
    src = desktop_db(env / "src")
    assert upload(app_client, src).status_code == 202
    assert upload(app_client, src).status_code == 409


def test_another_users_upload_is_404(app_client, make_user, login, env):
    make_user(email="a@example.com")
    make_user(email="b@example.com")
    login(app_client, "a@example.com")
    r = upload(app_client, desktop_db(env / "src"))
    jobs.run_next()
    app_client.post("/auth/logout")
    login(app_client, "b@example.com")
    uid = r.json()["upload_id"]
    assert app_client.post(f"/import/tadb/{uid}/run", json={}).status_code == 404
    assert app_client.post("/import/tadb/not-a-uuid/run", json={}).status_code == 404


def test_discard_deletes_the_file(app_client, me, env):
    r = upload(app_client, desktop_db(env / "src"))
    jobs.run_next()
    assert app_client.delete(f"/import/tadb/{r.json()['upload_id']}").status_code == 204
    assert uploads(env) == []
    assert app_client.delete(f"/import/tadb/{r.json()['upload_id']}").status_code == 204


def test_sweep_removes_only_old_uploads(env):
    d = env / "data" / "uploads" / "1"
    d.mkdir(parents=True)
    old, new = d / "a.db", d / "b.db"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    past = time.time() - 25 * 3600
    os.utime(old, (past, past))
    assert tadb_uploads.sweep() == 1
    assert not old.exists() and new.exists()


def test_job_result_messages_are_capped(app_client, me, env, monkeypatch):
    from api import tadb_job

    monkeypatch.setattr(tadb_job, "MAX_MESSAGES", 1)
    src = desktop_db(env / "src")
    sqlite3.connect(src).executescript(
        "INSERT INTO lines (document_id, line_number, prefix, raw_text) VALUES (99, 0, '%', 'a');"
        "INSERT INTO lines (document_id, line_number, prefix, raw_text) VALUES (99, 1, '%', 'b');"
    )
    r = upload(app_client, src)
    messages = job(app_client, r.json()["job_id"])["result"]["messages"]
    assert len(messages) == 2 and messages[-1] == "…and 1 more"
