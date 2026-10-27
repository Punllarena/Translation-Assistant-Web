"""Export: a whole-server zip of COPY CSV members plus the manifest and the dict files."""

import csv
import io
import zipfile
from datetime import UTC, date, datetime, timedelta

import pytest

from api.backup import crypto, export, manifest, schema
from api.config import get_settings
from api.models import ApiCredential, Job, OllamaChunk, Series
from api.models import Session as SessionRow
from api.security import encrypt_secret

PASS = "correct horse battery"


@pytest.fixture
def key():
    kdf = crypto.new_kdf()
    return crypto.derive(PASS, kdf), kdf


def _export(db, key):
    f, kdf = key
    out = io.BytesIO()
    m = export.write(db.connection(), out, f, kdf)
    return m, zipfile.ZipFile(io.BytesIO(out.getvalue()))


def _csv(zf, name):
    return list(csv.reader(io.StringIO(zf.read(name).decode("utf-8")),
                           quoting=csv.QUOTE_NOTNULL))


def _job(db, user, state):
    job = Job(user_id=user.id, kind="tadb_import", state=state, params_json={})
    db.add(job)
    db.flush()
    return job


def _chunk(db, user, job_id):
    chunk = OllamaChunk(
        user_id=user.id, series_id=None, document_id=None, job_id=job_id, source="run",
        ok=True, clamped=False, depth=0, model="m", preset="small", chunk_lines=12,
        context_lines=5, first_line=0, last_line=1, asked=2, prompt_tokens=10,
        output_tokens=5, total_ms=900, reasoning="why", prompt="[]",
    )
    db.add(chunk)
    db.flush()
    return chunk


def test_sessions_and_unfinished_jobs_are_left_out(db, make_user, key):
    user = make_user()
    db.add(SessionRow(token_hash="t", user_id=user.id,
                      expires_at=datetime.now(UTC) + timedelta(days=1)))
    done, cancelled = _job(db, user, "done"), _job(db, user, "cancelled")
    running = _job(db, user, "running")
    kept = _chunk(db, user, done.id)
    dropped = _chunk(db, user, running.id)
    db.flush()

    m, zf = _export(db, key)

    assert "tables/sessions.csv" not in zf.namelist()
    rows = _csv(zf, "tables/jobs.csv")
    header, body = rows[0], rows[1:]
    assert sorted(row[header.index("state")] for row in body) == ["cancelled", "done"]
    assert m.tables["jobs"] == 2
    chunks = _csv(zf, "tables/ollama_chunks.csv")
    h = chunks[0]
    by_id = {int(row[h.index("id")]): row[h.index("job_id")] for row in chunks[1:]}
    assert by_id[dropped.id] is None
    assert int(by_id[kept.id]) == done.id
    assert m.tables["ollama_chunks"] == 2
    assert cancelled.id and running.id  # both exist; only the finished one is exported


def test_every_foreign_key_to_jobs_is_nulled(db):
    conn = db.connection()
    checked = []
    for table in schema.reflect_app_tables(conn):
        for fk in table.foreign_keys:
            if fk.column.table.name == "jobs":
                checked.append(f"{table.name}.{fk.parent.name}")
                rendered = export.table_query(table).as_string(
                    conn.connection.driver_connection
                )
                assert "CASE WHEN" in rendered
    assert checked == ["ollama_chunks.job_id"]


def test_credentials_are_relocked(db, make_user, key):
    user = make_user()
    db.add(ApiCredential(user_id=user.id, kind="deepl", name="",
                         secret_enc=encrypt_secret("s3cret")))
    db.flush()
    f, _ = key

    m, zf = _export(db, key)

    data = zf.read("tables/api_credentials.csv")
    assert b"s3cret" not in data and m.tables["api_credentials"] == 1
    rows = _csv(zf, "tables/api_credentials.csv")
    header, row = rows[0], rows[1]
    locked = bytes.fromhex(row[header.index("secret_enc")][2:])
    assert f.decrypt(locked) == b"s3cret"
    assert m.skipped_credentials == []


def test_counts_are_rows_not_lines(db, make_user, key):
    user = make_user()
    db.add(Series(user_id=user.id, title="S", wp_summary="a\n\nb"))
    db.flush()

    m, zf = _export(db, key)

    assert m.tables["series"] == 1
    assert len(_csv(zf, "tables/series.csv")) == 2  # the header and one row


def test_publish_passwords_stay_as_they_are(db, make_user, key):
    """The spec's exception: chapter passwords in a finished job are content, not secrets."""
    user = make_user()
    job = _job(db, user, "done")
    job.result_json = {"chapters": [{"password": "hunter2"}]}
    db.flush()

    _, zf = _export(db, key)

    assert b"hunter2" in zf.read("tables/jobs.csv")


def test_dict_files_from_data_dir_are_included(db, tmp_path, monkeypatch, key):
    from api import dictionary

    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "edict_path", "")
    monkeypatch.setattr(get_settings(), "conjugations_path", "")
    (tmp_path / "dict").mkdir()
    (tmp_path / "dict" / dictionary.FILENAMES["edict"]).write_bytes(b"edict data")

    _, zf = _export(db, key)

    assert zf.read("dict/edict") == b"edict data"
    assert "dict/conjugations" not in zf.namelist()
    assert zf.namelist()[-1] == "manifest.json"


def test_the_manifest_records_the_head_revision_and_the_closed_passphrase(db, key):
    _, zf = _export(db, key)

    m = manifest.parse(zf.read("manifest.json"))

    assert m.revision == schema.head()
    crypto.verify(crypto.derive(PASS, m.kdf), m.check)  # no WrongPassphrase
    with pytest.raises(crypto.WrongPassphrase):
        crypto.verify(crypto.derive("another passphrase", m.kdf), m.check)
    assert m.tables["users"] == 0


def test_filename():
    assert export.filename(date(2026, 10, 27)) == "ta-backup-2026-10-27.zip"
