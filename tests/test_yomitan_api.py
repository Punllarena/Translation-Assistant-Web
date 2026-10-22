import os
import time
from contextlib import contextmanager
from datetime import timedelta

import pytest

from api import jobs, yomitan_job, yomitan_store
from api.config import get_settings
from tests.fixtures.yomitan import JMDICT_INDEX, JMDICT_ROWS, JMDICT_TAGS, make_zip


@pytest.fixture
def env(tmp_path, monkeypatch, db, app_client, make_user, login):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))

    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    make_user(email="admin@example.com", is_admin=True)
    login(app_client, "admin@example.com")
    return tmp_path


def zip_bytes(tmp_path, index=None, banks=None, name="d.zip"):
    banks = banks or {"term_bank_1.json": JMDICT_ROWS, "tag_bank_1.json": JMDICT_TAGS}
    return make_zip(tmp_path / name, index or JMDICT_INDEX, banks).read_bytes()


def post(client, data, name="d.zip"):
    return client.post("/admin/dictionary/yomitan", files={"file": (name, data)})


def run(client, data):
    r = post(client, data)
    assert r.status_code == 202, r.text
    assert jobs.run_next() is True
    return client.get(f"/jobs/{r.json()['id']}").json()


def test_upload_installs_and_lists_with_order(app_client, env):
    job = run(app_client, zip_bytes(env))
    assert job["state"] == "done"
    assert job["result"]["message"] == "Installed JMdict [2026-10-21] (2 entries)"
    body = app_client.get("/admin/dictionary").json()
    d = body["yomitan"][0]
    assert d["title"] == "JMdict [2026-10-21]" and d["entries"] == 2
    assert body["order"] == ["edict", f"yomitan:{d['id']}"]
    assert list(yomitan_job.upload_dir().glob("*.zip")) == []


def test_second_upload_of_same_dictionary_updates(app_client, env):
    run(app_client, zip_bytes(env))
    newer = {**JMDICT_INDEX, "revision": "JMdict.2026-11-01"}
    job = run(app_client, zip_bytes(env, index=newer, name="n.zip"))
    assert job["result"]["message"] == (
        "Updated JMdict [2026-10-21] from JMdict.2026-10-21 to JMdict.2026-11-01")
    assert len(app_client.get("/admin/dictionary").json()["yomitan"]) == 1


def test_kanji_zip_fails_with_the_refusal_message(app_client, env):
    index = {"title": "KANJIDIC", "format": 3, "revision": "k1"}
    job = run(app_client, zip_bytes(env, index=index, banks={"kanji_bank_1.json": [["日"]]}))
    assert job["state"] == "failed" and job["message"]
    assert list(yomitan_job.upload_dir().glob("*.zip")) == []


def test_not_a_zip_is_422_before_any_job(app_client, env):
    r = post(app_client, b"hello there")
    assert r.status_code == 422
    assert r.json()["detail"] == "This is not a zip file; upload the Yomitan dictionary .zip."
    assert list(yomitan_job.upload_dir().glob("*.zip")) == []
    assert app_client.get("/jobs?active=true").json() == []


def test_oversize_is_413(app_client, env, monkeypatch):
    monkeypatch.setattr(yomitan_job, "MAX_UPLOAD", 10)
    assert post(app_client, b"PK\x03\x04" + b"x" * 20).status_code == 413
    assert list(yomitan_job.upload_dir().glob("*.zip")) == []


def test_cancel_leaves_nothing_installed(app_client, env, monkeypatch, db):
    calls = []

    def report(self, done, total, message=""):
        calls.append(message)
        if len(calls) == 2:
            raise jobs.Cancelled
    monkeypatch.setattr(jobs.JobContext, "report", report)
    data = zip_bytes(env, banks={"term_bank_1.json": JMDICT_ROWS, "term_bank_2.json": JMDICT_ROWS})
    job = run(app_client, data)
    assert job["state"] == "cancelled"
    assert yomitan_store.installed(db) == []
    assert list(yomitan_job.upload_dir().glob("*.zip")) == []


def test_single_entry_message_is_singular(app_client, env):
    job = run(app_client, zip_bytes(env, banks={"term_bank_1.json": [JMDICT_ROWS[0]]}))
    assert job["result"]["message"] == "Installed JMdict [2026-10-21] (1 entry)"


def test_cancel_during_saving_leaves_nothing_installed(app_client, env, monkeypatch, db):
    monkeypatch.setattr(yomitan_store, "BATCH", 1)
    saves = []

    def report(self, done, total, message=""):
        if message == "Saving":
            saves.append(done)
            if len(saves) == 3:  # the job's own report, then batches 0 and 1
                raise jobs.Cancelled
    monkeypatch.setattr(jobs.JobContext, "report", report)
    job = run(app_client, zip_bytes(env))
    assert job["state"] == "cancelled"
    assert len(saves) == 3
    assert yomitan_store.installed(db) == []


def test_one_upload_at_a_time(app_client, env):
    assert post(app_client, zip_bytes(env)).status_code == 202
    assert post(app_client, zip_bytes(env)).status_code == 409


def test_order_put_and_validation(app_client, env):
    run(app_client, zip_bytes(env))
    token = app_client.get("/admin/dictionary").json()["order"][1]
    r = app_client.put("/admin/dictionary/order", json={"order": [token, "edict"]})
    assert r.status_code == 200 and r.json() == {"order": [token, "edict"]}
    assert app_client.get("/admin/dictionary").json()["order"] == [token, "edict"]
    assert app_client.put("/admin/dictionary/order", json={"order": ["edict"]}).status_code == 422


def test_delete_unknown_is_404_and_non_admin_is_refused(app_client, env, make_user, login):
    assert app_client.delete("/admin/dictionary/yomitan/999").status_code == 404
    run(app_client, zip_bytes(env))
    did = app_client.get("/admin/dictionary").json()["yomitan"][0]["id"]
    assert app_client.delete(f"/admin/dictionary/yomitan/{did}").status_code == 204
    assert app_client.get("/admin/dictionary").json()["yomitan"] == []
    app_client.post("/auth/logout")
    make_user(email="user@example.com")
    login(app_client, "user@example.com")
    assert app_client.delete("/admin/dictionary/yomitan/1").status_code == 403
    assert app_client.put("/admin/dictionary/order", json={"order": []}).status_code == 403
    assert post(app_client, b"PK\x03\x04").status_code == 403


def test_sweep_removes_old_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    d = yomitan_job.upload_dir()
    d.mkdir(parents=True)
    old, new = d / "a.zip", d / "b.zip"
    old.write_bytes(b"x")
    new.write_bytes(b"x")
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))
    assert yomitan_job.sweep(timedelta(hours=24)) == 1
    assert not old.exists() and new.exists()
