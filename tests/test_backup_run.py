"""run(): the restore thread's reporting. Before the commit a failure changed nothing; after
it, a failure is a warning on a successful restore."""

from contextlib import contextmanager
from pathlib import Path

import pytest

from api.backup import crypto, export, restore, state
from api.backup.crypto import WRONG_PASSPHRASE, WrongPassphrase

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


class _Engine:
    """Stands in for api.db.engine: apply is monkeypatched, so it never sees the database."""

    def __init__(self) -> None:
        self.disposed = False

    @contextmanager
    def begin(self):
        yield object()

    def dispose(self) -> None:
        self.disposed = True


@pytest.fixture
def fake_engine(monkeypatch):
    engine = _Engine()
    monkeypatch.setattr(restore, "engine", engine)
    return engine


def _backup(db, path: Path, key) -> Path:
    f, kdf = key
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as out:
        export.write(db.connection(), out, f, kdf)
    return path


def _reader(db, tmp_path, key) -> restore.BackupReader:
    return restore.BackupReader.open(_backup(db, tmp_path / "b.zip", key), PASS)


def _staged(data_dir: Path) -> Path:
    staged = data_dir / "dict.restore"
    staged.mkdir()
    (staged / "edict2").write_bytes(b"x")
    return staged


def test_run_failure_reports_generic_and_cleans_up(db, tmp_path, key, data_dir, fake_engine,
                                                   monkeypatch):
    reader = _reader(db, tmp_path, key)
    staged = _staged(data_dir)
    monkeypatch.setattr(restore, "stage_dictionaries", lambda r: staged)

    def boom(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(restore, "apply", boom)

    restore.run(reader, from_setup=False)

    assert state.snapshot() == state.Status(phase="failed", error=restore.GENERIC)
    assert not staged.exists() and not reader.path.exists()
    assert not fake_engine.disposed


def test_run_restore_error_is_verbatim(db, tmp_path, key, data_dir, fake_engine, monkeypatch):
    reader = _reader(db, tmp_path, key)
    monkeypatch.setattr(restore, "stage_dictionaries", lambda r: None)

    def boom(*args, **kwargs):
        raise restore.RestoreError("Try something else.")

    monkeypatch.setattr(restore, "apply", boom)

    restore.run(reader, from_setup=True)

    assert state.snapshot().phase == "failed"
    assert state.snapshot().error == "Try something else."


def test_run_wrong_passphrase_copy_is_never_empty(db, tmp_path, key, data_dir, fake_engine,
                                                  monkeypatch):
    reader = _reader(db, tmp_path, key)
    monkeypatch.setattr(restore, "stage_dictionaries", lambda r: None)

    def boom(*args, **kwargs):
        raise WrongPassphrase()

    monkeypatch.setattr(restore, "apply", boom)

    restore.run(reader, from_setup=False)

    assert state.snapshot().phase == "failed"
    assert state.snapshot().error == WRONG_PASSPHRASE


def test_run_swap_failure_is_reported_after_commit(db, tmp_path, key, data_dir, fake_engine,
                                                   monkeypatch):
    reader = _reader(db, tmp_path, key)
    staged = _staged(data_dir)
    monkeypatch.setattr(restore, "stage_dictionaries", lambda r: staged)
    monkeypatch.setattr(restore, "apply", lambda *args, **kwargs: None)

    def boom() -> None:
        raise OSError("busy")

    monkeypatch.setattr(restore, "swap_dictionaries", boom)

    restore.run(reader, from_setup=False)

    snapshot = state.snapshot()
    assert (snapshot.phase, snapshot.error) == ("done", restore.DICT_SWAP_FAILED)
    assert (data_dir / "dict.ready").exists()  # the next start completes the swap
    assert fake_engine.disposed


def test_run_uploads_cleanup_failure_is_a_warning(db, tmp_path, key, data_dir, fake_engine,
                                                  monkeypatch):
    reader = _reader(db, tmp_path, key)
    swapped = []
    monkeypatch.setattr(restore, "stage_dictionaries", lambda r: _staged(data_dir))
    monkeypatch.setattr(restore, "apply", lambda *args, **kwargs: None)
    monkeypatch.setattr(restore, "swap_dictionaries", lambda: swapped.append(True))
    monkeypatch.setattr(restore, "clear_uploads", lambda keep: False)

    restore.run(reader, from_setup=False)

    snapshot = state.snapshot()
    assert (snapshot.phase, snapshot.error) == ("done", restore.UPLOADS_LEFT)
    assert swapped == [True]  # the dictionaries were still swapped


def test_run_keeps_the_open_zip_while_clearing_uploads(db, tmp_path, key, data_dir, fake_engine,
                                                       monkeypatch):
    uploads = data_dir / "uploads"
    other = uploads / "restore" / "old.zip"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"old")
    pending = uploads / "7" / "a.db"
    pending.parent.mkdir()
    pending.write_bytes(b"x")
    path = _backup(db, uploads / "restore" / "new.zip", key)
    reader = restore.BackupReader.open(path, PASS)
    monkeypatch.setattr(restore, "stage_dictionaries", lambda r: _staged(data_dir))
    monkeypatch.setattr(restore, "apply", lambda *args, **kwargs: None)
    monkeypatch.setattr(restore, "swap_dictionaries", lambda: None)
    seen = {}
    real_clear = restore.clear_uploads

    def checking(keep):
        seen["zip_present"] = keep.exists()
        return real_clear(keep)

    monkeypatch.setattr(restore, "clear_uploads", checking)

    restore.run(reader, from_setup=False)

    assert seen["zip_present"] is True  # the open upload is not pulled out from under the zip
    assert not other.exists() and not pending.exists()
    assert not path.exists()  # deleted only after the reader closed it
    assert state.snapshot().phase == "done"
