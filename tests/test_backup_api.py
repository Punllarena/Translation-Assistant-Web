"""The backup, restore and status routes: admin only, busy-aware, and 422 before anything."""

import io
import zipfile
from datetime import date

import pytest

from api import jobs
from api.backup import crypto, export, manifest, restore, state, uploads
from api.backup.crypto import WRONG_PASSPHRASE

PASS = "correct horse battery"


@pytest.fixture
def key():
    kdf = crypto.new_kdf()
    return crypto.derive(PASS, kdf), kdf


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "edict_path", "")
    monkeypatch.setattr(get_settings(), "conjugations_path", "")
    return tmp_path


@pytest.fixture
def admin_login(app_client, make_user, login):
    user = make_user(email="admin@example.com", is_admin=True)
    login(app_client, "admin@example.com")
    return user


@pytest.fixture
def backup_file(db, tmp_path, key):
    f, kdf = key
    path = tmp_path / "b.zip"
    with path.open("wb") as out:
        export.write(db.connection(), out, f, kdf)
    return path


@pytest.fixture
def started(monkeypatch):
    """restore.start is the seam: the thread itself is Task 5's tests' business."""
    calls = []
    monkeypatch.setattr(restore, "start", lambda reader, from_setup: calls.append(from_setup))
    return calls


def _upload(app_client, path, passphrase=PASS, confirm="RESTORE", endpoint="/admin/restore"):
    data = {"passphrase": passphrase}
    if endpoint == "/admin/restore":
        data["confirm"] = confirm
    return app_client.post(endpoint, files={"file": ("b.zip", path.read_bytes())}, data=data)


def _restore_uploads(data_dir):
    return list((data_dir / "uploads" / "restore").glob("*"))


def test_backup_requires_admin(app_client, make_user, login):
    assert app_client.post("/admin/backup", data={"passphrase": PASS}).status_code == 401
    make_user(email="plain@example.com")
    login(app_client, "plain@example.com")
    assert app_client.post("/admin/backup", data={"passphrase": PASS}).status_code == 403


def test_backup_downloads_a_zip_with_a_manifest(app_client, admin_login, db, monkeypatch):
    def fake_stream(f, kdf):
        out = io.BytesIO()
        export.write(db.connection(), out, f, kdf)
        return iter([out.getvalue()])

    monkeypatch.setattr(export, "stream", fake_stream)

    r = app_client.post("/admin/backup", data={"passphrase": PASS})

    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert f"ta-backup-{date.today().isoformat()}.zip" in r.headers["content-disposition"]
    m = manifest.parse(zipfile.ZipFile(io.BytesIO(r.content)).read("manifest.json"))
    crypto.verify(crypto.derive(PASS, m.kdf), m.check)


def test_short_passphrase_is_422(app_client, admin_login):
    r = app_client.post("/admin/backup", data={"passphrase": "short"})
    assert r.status_code == 422 and "12 characters" in r.json()["detail"]


def test_admin_restore_requires_admin(app_client, make_user, login, backup_file, started):
    assert _upload(app_client, backup_file).status_code == 401
    make_user(email="plain@example.com")
    login(app_client, "plain@example.com")
    assert _upload(app_client, backup_file).status_code == 403
    assert started == []


def test_restore_needs_the_confirm_word(app_client, admin_login, backup_file, started):
    r = _upload(app_client, backup_file, confirm="restore")
    assert r.status_code == 422 and "Type RESTORE" in r.json()["detail"]
    assert started == []


def test_restore_refused_while_a_job_is_queued(app_client, admin_login, backup_file, db, started):
    jobs.enqueue(db, admin_login.id, "tadb_import", {})
    db.flush()

    r = _upload(app_client, backup_file)

    assert r.status_code == 409 and r.json()["detail"] == state.BUSY
    assert started == []


def test_job_started_during_upload_blocks_restore(
    app_client, admin_login, backup_file, db, data_dir, started, monkeypatch
):
    real_save = uploads.save

    def save_and_queue(upload):
        path = real_save(upload)
        jobs.enqueue(db, admin_login.id, "tadb_import", {})  # started while the file arrived
        db.flush()
        return path

    monkeypatch.setattr(uploads, "save", save_and_queue)

    r = _upload(app_client, backup_file)

    assert r.status_code == 409 and r.json()["detail"] == state.BUSY
    assert started == [] and state.snapshot().phase == "idle"
    assert _restore_uploads(data_dir) == []


def test_work_in_flight_during_upload_blocks_restore(
    app_client, admin_login, backup_file, data_dir, started, monkeypatch
):
    held = []
    real_open = restore.BackupReader.open

    def holding_open(cls, path, passphrase):
        gate = state.work()
        gate.__enter__()
        held.append(gate)
        return real_open.__func__(cls, path, passphrase)

    monkeypatch.setattr(restore.BackupReader, "open", classmethod(holding_open))
    try:
        r = _upload(app_client, backup_file)
    finally:
        for gate in held:
            gate.__exit__(None, None, None)

    assert r.status_code == 409 and r.json()["detail"] == state.BUSY
    assert started == [] and _restore_uploads(data_dir) == []


def test_restore_wrong_passphrase_is_422_and_nothing_starts(
    app_client, admin_login, backup_file, data_dir, started
):
    r = _upload(app_client, backup_file, passphrase="not the passphrase")

    assert r.status_code == 422 and r.json()["detail"] == WRONG_PASSPHRASE
    assert started == [] and _restore_uploads(data_dir) == []


@pytest.mark.parametrize("endpoint", ["/admin/restore", "/setup/restore"])
def test_short_restore_passphrase_is_422_not_500(
    app_client, make_user, login, backup_file, data_dir, started, endpoint
):
    if endpoint == "/admin/restore":
        make_user(email="admin@example.com", is_admin=True)
        login(app_client, "admin@example.com")

    r = _upload(app_client, backup_file, passphrase="short", endpoint=endpoint)

    assert r.status_code == 422 and r.json()["detail"] == WRONG_PASSPHRASE
    assert started == [] and _restore_uploads(data_dir) == []


def test_second_restore_while_restoring_is_409(
    app_client, admin_login, backup_file, db, started, monkeypatch
):
    assert state.try_begin(db) is None  # a restore is already running
    monkeypatch.setattr(state, "active", lambda: False)  # the race past the early answer

    r = _upload(app_client, backup_file)

    assert r.status_code == 409 and r.json()["detail"] == state.RESTORING
    assert started == []


def test_restore_corrupt_zip_is_422(app_client, admin_login, tmp_path, data_dir, started):
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip at all")

    r = _upload(app_client, junk)

    assert r.status_code == 422 and "not a backup" in r.json()["detail"]
    assert started == [] and _restore_uploads(data_dir) == []


def test_restore_starts_and_answers_202(app_client, admin_login, backup_file, started):
    r = _upload(app_client, backup_file)

    assert r.status_code == 202
    assert started == [False]
    assert r.json()["phase"] == "restoring"


def test_setup_restore_only_without_users(app_client, make_user, backup_file, started):
    make_user(email="someone@example.com")

    r = _upload(app_client, backup_file, endpoint="/setup/restore")

    assert r.status_code == 409 and "Setup is already complete" in r.json()["detail"]
    assert started == []


def test_setup_restore_starts_without_users(app_client, backup_file, started):
    r = _upload(app_client, backup_file, endpoint="/setup/restore")

    assert r.status_code == 202 and started == [True]


def test_status_needs_no_login_and_works_during_maintenance(app_client, db):
    assert app_client.get("/restore/status").json()["phase"] == "idle"
    state.try_begin(db)

    r = app_client.get("/restore/status")

    assert r.status_code == 200 and r.json()["phase"] == "restoring"
    assert app_client.get("/series").status_code == 503
