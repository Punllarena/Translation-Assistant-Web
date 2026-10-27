"""Restore: validated before anything changes, and all or nothing inside the transaction."""

import csv
import io
import json
import shutil
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
import sqlalchemy as sa
from psycopg import sql

from api import dictionary, security
from api.backup import crypto, export, manifest, restore, schema
from api.backup.crypto import WRONG_PASSPHRASE, WrongPassphrase
from api.backup.manifest import BackupInvalid
from api.config import get_settings
from api.models import (
    ApiCredential,
    CustomWord,
    Dictionary,
    DictionaryTerm,
    Document,
    DocumentImage,
    GlossaryEntry,
    Invite,
    Job,
    Line,
    MtCache,
    OllamaChunk,
    OllamaQueueItem,
    OllamaSuggestion,
    Series,
    ServerSetting,
    Shortcut,
    UserSetting,
    Volume,
    VolumeCover,
    WorkSession,
)
from api.models import (
    Session as SessionRow,
)
from api.security import decrypt_secret, encrypt_secret

PASS = "correct horse battery"
FX = Path(__file__).parent / "fixtures" / "mt"
EDICT = (FX / "edict2_sample").read_bytes()


@pytest.fixture
def key():
    kdf = crypto.new_kdf()
    return crypto.derive(PASS, kdf), kdf


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "edict_path", "")
    monkeypatch.setattr(get_settings(), "conjugations_path", "")
    monkeypatch.setattr(dictionary, "MIN_EDICT_ENTRIES", 1)  # the sample is a few lines
    return tmp_path


def _write_backup(db, path, key) -> Path:
    f, kdf = key
    with path.open("wb") as out:
        export.write(db.connection(), out, f, kdf)
    return path


def _rewrite(path: Path, changes: dict[str, bytes | None]) -> Path:
    """Copy the zip, replacing or dropping members: a tampered backup."""
    with zipfile.ZipFile(path) as src:
        members = {name: src.read(name) for name in src.namelist()}
    for name, data in changes.items():
        if data is None:
            members.pop(name, None)
        else:
            members[name] = data
    out = path.with_name("tampered-" + path.name)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return out


def _member(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path) as zf:
        return zf.read(name)


def _apply(db, reader, from_setup: bool = False) -> None:
    conn = db.connection()
    with conn.begin_nested():  # the restore's transaction: an error rolls back to here
        restore.apply(conn, reader, from_setup=from_setup, progress=lambda *args: None)


def _dump(conn) -> tuple[dict[str, list[tuple]], dict[str, list[str]]]:
    tables = {table.name: table for table in schema.reflect_app_tables(conn)}
    raw = conn.connection.driver_connection
    rows, columns = {}, {}
    for name, table in tables.items():
        columns[name] = [column.name for column in table.columns]
        order = sql.SQL(", ").join(sql.Identifier(c.name) for c in table.primary_key)
        with raw.cursor() as cur:
            cur.execute(sql.SQL("SELECT * FROM {} ORDER BY {}").format(
                sql.Identifier(name), order))
            rows[name] = cur.fetchall()
    return rows, columns


def _seed(db, make_user):
    """One row of every kind the backup has to carry."""
    user = make_user(email="seed@example.com", is_admin=True)
    now = datetime.now(UTC)
    series = Series(user_id=user.id, title="Seed series", wp_summary="a\n\nb", source="syosetu")
    db.add(series)
    db.flush()
    volume = Volume(series_id=series.id, kind="Volume", subtitle="First")
    db.add(volume)
    db.flush()
    volume.is_series_cover = True
    doc = Document(user_id=user.id, series_id=series.id, volume_id=volume.id, title="Ch",
                   chapter_title="Chapter 1", series_order=0)
    db.add(doc)
    db.flush()
    line = Line(document_id=doc.id, line_number=0, prefix="%", raw_text="一行目",
                translated_text="one", translated_at=now)
    db.add(line)
    db.add(DocumentImage(document_id=doc.id, anchor_position=0, src_path="a.png",
                         data=b"\x00\xffimg"))
    db.add(VolumeCover(volume_id=volume.id, src_path="c.png", data=b"cover\x00"))
    db.add(GlossaryEntry(series_id=series.id, phrase="太郎", translation="Taro", sort_order=1))
    db.add(CustomWord(user_id=user.id, series_id=series.id, word="Rimuru"))
    db.add(CustomWord(user_id=user.id, series_id=None, word="senpai"))
    db.add(UserSetting(user_id=user.id, key="ui_theme", value_json="dark"))
    db.add(Shortcut(user_id=user.id, action_key="save", binding="Ctrl+S"))
    db.add(ApiCredential(user_id=user.id, kind="deepl", name="", endpoint_url="",
                         secret_enc=encrypt_secret("s3cret")))
    db.add(ServerSetting(key="libretranslate_url", value="http://lt:5000"))
    db.add(Invite(token_hash="invite", email="invitee@example.com", created_by=user.id,
                  expires_at=now + timedelta(days=1)))
    dictionary_row = Dictionary(identity_key="k", title="T", revision="1", attribution="",
                                author="", url="", entry_count=1, updated_at=now)
    db.add(dictionary_row)
    db.flush()
    db.add(DictionaryTerm(dictionary_id=dictionary_row.id, key="猫", headwords=["猫"],
                          reading="ねこ", pos=["n"], gloss="cat"))
    db.add(MtCache(backend="deepl", source_lang="ja", target_lang="en",
                   source_sha256="a" * 64, result_text="one"))
    db.add(OllamaQueueItem(user_id=user.id, kind="documents", series_id=series.id,
                           document_ids=[doc.id], position=0))
    done = Job(user_id=user.id, kind="tadb_import", state="done", params_json={"x": 1},
               result_json={"ok": True, "chapters": [{"password": "hunter2"}]})
    cancelled = Job(user_id=user.id, kind="tadb_import", state="cancelled", params_json={})
    running = Job(user_id=user.id, kind="tadb_import", state="running", params_json={})
    db.add_all([done, cancelled, running])
    db.flush()

    def chunk(job_id):
        row = OllamaChunk(
            user_id=user.id, series_id=series.id, document_id=doc.id, job_id=job_id,
            source="run", ok=True, clamped=False, depth=0, model="m", preset="small",
            chunk_lines=2, context_lines=1, first_line=0, last_line=0, asked=1,
            prompt_tokens=1, output_tokens=1, total_ms=1, reasoning="why", prompt="[]",
        )
        db.add(row)
        db.flush()
        return row

    kept = chunk(done.id)
    dropped = chunk(running.id)
    db.add(OllamaSuggestion(line_id=line.id, chunk_id=kept.id, text="one",
                            raw_sha="x" * 64, scored=False))
    db.add(WorkSession(user_id=user.id, started_at=now, ended_at=now, lines_translated=2,
                       words_translated=4))
    db.add(SessionRow(token_hash="tok", user_id=user.id, expires_at=now + timedelta(days=1)))
    db.flush()
    return SimpleNamespace(user=user, series=series, doc=doc, line=line, dropped=dropped)


def test_round_trip_restores_every_kind_of_row(db, make_user, tmp_path, key):
    seed = _seed(db, make_user)
    path = _write_backup(db, tmp_path / "b.zip", key)
    before, columns = _dump(db.connection())

    # the server moves on while the file is on its way to the new machine
    db.execute(sa.text("INSERT INTO users (email, username, password_hash, is_admin)"
                       " VALUES ('new@example.com', 'new', 'x', false)"))
    db.execute(sa.text("DELETE FROM series WHERE id = :i"), {"i": seed.series.id})
    db.expire_all()

    reader = restore.BackupReader.open(path, PASS)
    _apply(db, reader)
    reader.close()

    after, _ = _dump(db.connection())
    state_at = columns["jobs"].index("state")
    assert after["jobs"] == [r for r in before["jobs"] if r[state_at] != "running"]
    assert after["sessions"] == []
    chunk_cols = columns["ollama_chunks"]
    id_at, job_at = chunk_cols.index("id"), chunk_cols.index("job_id")
    assert after["ollama_chunks"] == [
        row if row[id_at] != seed.dropped.id
        else (*row[:job_at], None, *row[job_at + 1:])
        for row in before["ollama_chunks"]
    ]
    for name in before:
        if name not in ("sessions", "jobs", "ollama_chunks", "api_credentials"):
            assert after[name] == before[name], name
    # credentials are re-encrypted with this server's key: the token is new, the secret is not
    cred_cols = columns["api_credentials"]
    secret_at = cred_cols.index("secret_enc")

    def without_secret(rows):
        return [[value for i, value in enumerate(row) if i != secret_at] for row in rows]

    assert without_secret(after["api_credentials"]) == without_secret(before["api_credentials"])
    assert [decrypt_secret(row[secret_at]) for row in after["api_credentials"]] == [
        decrypt_secret(row[secret_at]) for row in before["api_credentials"]]
    assert b"hunter2" in _member(path, "tables/jobs.csv")  # the spec's password exception


def test_restore_with_a_new_secret_key(db, make_user, tmp_path, key, monkeypatch):
    user = make_user()
    db.add(ApiCredential(user_id=user.id, kind="deepl", name="", endpoint_url="",
                         secret_enc=encrypt_secret("s3cret")))
    db.flush()
    path = _write_backup(db, tmp_path / "b.zip", key)
    monkeypatch.setattr(
        security, "get_settings",
        lambda: SimpleNamespace(secret_key="a-different-secret-key-at-least-32-chars"),
    )

    reader = restore.BackupReader.open(path, PASS)
    _apply(db, reader)
    reader.close()

    name, endpoint_url, blob = db.execute(
        sa.text("SELECT name, endpoint_url, secret_enc FROM api_credentials")
    ).one()
    assert name == "" and endpoint_url == ""  # blank stays "", not NULL
    assert decrypt_secret(blob) == "s3cret"


def test_sequences_continue_after_restore(db, make_user, tmp_path, key):
    _seed(db, make_user)
    path = _write_backup(db, tmp_path / "b.zip", key)
    reader = restore.BackupReader.open(path, PASS)
    _apply(db, reader)
    reader.close()

    conn = db.connection()
    for max_sql, insert, param in (
        ("SELECT max(id) FROM users",
         "INSERT INTO users (email, username, password_hash, is_admin)"
         " VALUES (:v, 'newbie', 'x', false) RETURNING id", "new@example.com"),
        ("SELECT max(id) FROM series",
         "INSERT INTO series (user_id, title, syosetu_url, wp_series_slug,"
         " wp_series_title_short) VALUES ((SELECT min(id) FROM users), :v, '', '', '')"
         " RETURNING id", "Second"),
        ("SELECT max(id) FROM lines",
         "INSERT INTO lines (document_id, line_number, prefix, raw_text, translated_text)"
         " VALUES ((SELECT min(id) FROM documents), 9, '%', :v, '') RETURNING id", "next"),
    ):
        top = conn.scalar(sa.text(max_sql))
        assert conn.scalar(sa.text(insert), {"v": param}) == top + 1


def test_wrong_passphrase_is_refused_before_anything(db, make_user, tmp_path, key):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)

    with pytest.raises(WrongPassphrase) as exc:
        restore.BackupReader.open(path, "not the passphrase")

    assert str(exc.value) == WRONG_PASSPHRASE
    assert db.scalar(sa.text("SELECT count(*) FROM users")) == 1


def test_newer_revision_is_refused(db, make_user, tmp_path, key):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)
    m = json.loads(_member(path, "manifest.json"))
    m["revision"] = "ffffffffffff"
    bad = _rewrite(path, {"manifest.json": json.dumps(m).encode()})

    with pytest.raises(BackupInvalid, match="newer version of Translation Assistant"):
        restore.BackupReader.open(bad, PASS)


def test_stray_member_is_refused(db, make_user, tmp_path, key):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)
    bad = _rewrite(path, {"evil.txt": b"nope"})

    with pytest.raises(BackupInvalid, match="not a backup"):
        restore.BackupReader.open(bad, PASS)


def test_truncated_zip_is_refused(db, make_user, tmp_path, key):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)
    data = path.read_bytes()
    cut = path.with_name("cut.zip")
    cut.write_bytes(data[: len(data) // 2])

    with pytest.raises(BackupInvalid, match="not a backup"):
        restore.BackupReader.open(cut, PASS)


def test_oversized_manifest_is_refused(db, make_user, tmp_path, key):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)
    bad = _rewrite(path, {"manifest.json": b" " * (manifest.MAX_MANIFEST + 1)})

    with pytest.raises(BackupInvalid, match="not a backup"):
        restore.BackupReader.open(bad, PASS)


def test_missing_table_is_refused(db, make_user, tmp_path, key):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)
    m = json.loads(_member(path, "manifest.json"))
    m["tables"].pop("mt_cache")
    bad = _rewrite(path, {"tables/mt_cache.csv": None,
                          "manifest.json": json.dumps(m).encode()})

    reader = restore.BackupReader.open(bad, PASS)  # the file agrees with its manifest

    with pytest.raises(BackupInvalid, match="incomplete"):
        _apply(db, reader)
    assert db.scalar(sa.text("SELECT count(*) FROM users")) == 1


def test_wrong_header_is_refused(db, make_user, tmp_path, key):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)
    header = _member(path, "tables/users.csv").decode()
    bad = _rewrite(path, {"tables/users.csv": header.replace("email", "e_mail", 1).encode()})

    reader = restore.BackupReader.open(bad, PASS)

    with pytest.raises(BackupInvalid, match="does not match its recorded version"):
        _apply(db, reader)
    assert db.scalar(sa.text("SELECT count(*) FROM users")) == 1


def test_corrupt_member_rolls_back(db, make_user, tmp_path, key):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)
    data = _member(path, "tables/lines.csv")
    bad = _rewrite(path, {"tables/lines.csv": data + b"not,a,row\n"})

    reader = restore.BackupReader.open(bad, PASS)

    with pytest.raises(psycopg.Error):
        _apply(db, reader)
    assert db.scalar(sa.text("SELECT count(*) FROM users")) == 1


def test_failure_mid_load_changes_nothing(db, make_user, tmp_path, key, monkeypatch):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)
    real = restore._load
    calls = []

    def failing(conn, reader, table, cur):
        calls.append(table.name)
        if len(calls) == 3:
            raise ValueError("boom")
        return real(conn, reader, table, cur)

    monkeypatch.setattr(restore, "_load", failing)
    reader = restore.BackupReader.open(path, PASS)

    with pytest.raises(ValueError):
        _apply(db, reader)
    assert calls and calls[-1] not in ("api_credentials",)
    assert db.scalar(sa.text("SELECT count(*) FROM users")) == 1
    assert schema.current_revision(db.connection()) == schema.head()


def test_setup_restore_refuses_when_a_user_exists(db, make_user, tmp_path, key):
    make_user()
    path = _write_backup(db, tmp_path / "b.zip", key)

    reader = restore.BackupReader.open(path, PASS)

    with pytest.raises(restore.RestoreError, match="Setup is already complete"):
        _apply(db, reader, from_setup=True)
    assert db.scalar(sa.text("SELECT count(*) FROM users")) == 1


def test_credentials_revision_backup_lands_at_head(db, tmp_path, key, monkeypatch):
    monkeypatch.delenv("TA_OLLAMA_URL", raising=False)
    conn = db.connection()
    schema.drop_app_tables(conn)
    schema.upgrade(conn, "59648cda8d6e")  # the parent of 7bb38754e763 (ollama own server)
    user_id = conn.scalar(sa.text(
        "INSERT INTO users (email, username, password_hash, is_admin)"
        " VALUES ('old@example.com', 'old', 'x', false) RETURNING id"))
    conn.execute(sa.text(
        "INSERT INTO user_settings (user_id, key, value_json)"
        " VALUES (:u, 'mt_enabled', CAST('[\"ollama\"]' AS jsonb))"), {"u": user_id})
    path = _write_backup(db, tmp_path / "b.zip", key)

    reader = restore.BackupReader.open(path, PASS)
    _apply(db, reader)
    reader.close()

    assert schema.current_revision(conn) == schema.head()
    assert conn.scalar(sa.text(
        "SELECT endpoint_url FROM api_credentials WHERE kind = 'ollama'")) == (
        "http://localhost:11434")


def test_structural_old_backup_lands_at_head(db, tmp_path, key):
    conn = db.connection()
    schema.drop_app_tables(conn)
    schema.upgrade(conn, "dc0385482445")  # before volume covers and series archive/status
    user_id = conn.scalar(sa.text(
        "INSERT INTO users (email, username, password_hash, is_admin)"
        " VALUES ('old@example.com', 'old', 'x', false) RETURNING id"))
    series_id = conn.scalar(sa.text(
        "INSERT INTO series (user_id, title, syosetu_url, wp_series_slug,"
        " wp_series_title_short) VALUES (:u, 'S', '', '', '') RETURNING id"), {"u": user_id})
    volume_id = conn.scalar(sa.text(
        "INSERT INTO volumes (series_id, volume_order, epub_title, epub_author, epub_language,"
        " epub_description, epub_illustrator, epub_publisher, epub_identifier)"
        " VALUES (:s, 0, '', '', 'en', '', '', '', '') RETURNING id"), {"s": series_id})
    document_id = conn.scalar(sa.text(
        "INSERT INTO documents (user_id, series_id, volume_id, title, chapter_title,"
        " source_language, series_order, source_url, last_position, wp_post_url, wp_status)"
        " VALUES (:u, :s, :v, 'Ch', 'Ch', 'ja', 0, '', 0, '', '') RETURNING id"),
        {"u": user_id, "s": series_id, "v": volume_id})
    conn.execute(sa.text(
        "INSERT INTO lines (document_id, line_number, prefix, raw_text, translated_text)"
        " VALUES (:d, 0, '%', 'raw', '')"), {"d": document_id})
    conn.execute(sa.text(
        "INSERT INTO document_images (document_id, anchor_position, is_cover, src_path, data,"
        " exclude_export) VALUES (:d, 0, true, 'c.png', :data, false)"),
        {"d": document_id, "data": b"cover"})
    path = _write_backup(db, tmp_path / "b.zip", key)

    reader = restore.BackupReader.open(path, PASS)
    _apply(db, reader)
    reader.close()

    assert schema.current_revision(conn) == schema.head()
    assert conn.execute(sa.text("SELECT status, archived_at FROM series")).one() == (
        "ongoing", None)
    assert conn.scalar(sa.text("SELECT data FROM volume_covers")) == b"cover"
    assert conn.scalar(sa.text("SELECT count(*) FROM document_images")) == 0
    assert conn.scalar(sa.text("SELECT count(*) FROM lines")) == 1


def test_stray_table_is_neither_exported_nor_dropped(db, make_user, tmp_path, key):
    make_user()
    conn = db.connection()
    conn.execute(sa.text("CREATE TABLE stray_notes (id int)"))
    conn.execute(sa.text("INSERT INTO stray_notes VALUES (7)"))
    path = _write_backup(db, tmp_path / "b.zip", key)
    with zipfile.ZipFile(path) as zf:
        assert "tables/stray_notes.csv" not in zf.namelist()

    reader = restore.BackupReader.open(path, PASS)
    _apply(db, reader)
    reader.close()

    assert conn.scalar(sa.text("SELECT id FROM stray_notes")) == 7


def test_damaged_credential_reports_the_wrong_passphrase_copy(db, make_user, tmp_path, key):
    user = make_user()
    db.add(ApiCredential(user_id=user.id, kind="deepl", name="",
                         secret_enc=encrypt_secret("x")))
    db.flush()
    path = _write_backup(db, tmp_path / "b.zip", key)
    rows = list(csv.reader(io.StringIO(_member(path, "tables/api_credentials.csv").decode())))
    rows[1][rows[0].index("secret_enc")] = "\\x" + (b"0" * 80).hex()
    out = io.StringIO()
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)
    bad = _rewrite(path, {"tables/api_credentials.csv": out.getvalue().encode()})

    reader = restore.BackupReader.open(bad, PASS)

    with pytest.raises(WrongPassphrase) as exc:
        _apply(db, reader)
    assert str(exc.value) == WRONG_PASSPHRASE
    assert db.scalar(sa.text("SELECT count(*) FROM users")) == 1


def test_corrupt_dictionary_fails_before_commit(db, data_dir, key):
    path = _write_backup(db, data_dir / "b.zip", key)
    bad = _rewrite(path, {"dict/edict": b"not a dictionary\n"})

    reader = restore.BackupReader.open(bad, PASS)

    with pytest.raises(BackupInvalid, match="edict dictionary is damaged"):
        restore.stage_dictionaries(reader)


def test_staging_without_edict_removes_the_old_file(db, data_dir, key):
    path = _write_backup(db, data_dir / "b.zip", key)  # no dict members
    dictionary.install("edict", EDICT)  # the old server's file

    reader = restore.BackupReader.open(path, PASS)
    staged = restore.stage_dictionaries(reader)
    assert staged is not None
    restore.mark_committed(staged)
    restore.swap_dictionaries()

    assert (data_dir / "dict").exists()
    assert not (data_dir / "dict" / dictionary.FILENAMES["edict"]).exists()


def test_swap_without_an_existing_dict_dir(db, data_dir, key):
    dictionary.install("edict", EDICT)  # so the backup has a dict member
    path = _write_backup(db, data_dir / "b.zip", key)
    shutil.rmtree(data_dir / "dict")  # a fresh install has none

    reader = restore.BackupReader.open(path, PASS)
    staged = restore.stage_dictionaries(reader)
    restore.mark_committed(staged)
    restore.swap_dictionaries()

    assert (data_dir / "dict" / dictionary.FILENAMES["edict"]).read_bytes() == EDICT
    assert not (data_dir / "dict.old").exists()


def test_swap_survives_old_dir_cleanup_failure(data_dir, monkeypatch):
    (data_dir / "dict").mkdir()
    (data_dir / "dict" / "edict2").write_bytes(b"old")
    (data_dir / "dict.ready").mkdir()
    (data_dir / "dict.ready" / "edict2").write_bytes(b"new")
    real = shutil.rmtree

    def failing(path, *args, **kwargs):
        if Path(path).name == "dict.old":
            raise OSError("busy")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(restore.shutil, "rmtree", failing)
    restore.swap_dictionaries()

    assert (data_dir / "dict" / "edict2").read_bytes() == b"new"
    assert not (data_dir / "dict.ready").exists()


@pytest.mark.parametrize("left,kept", [
    ("restore+dict", "dict"),   # crashed before the commit: the staged copy is dropped
    ("ready+dict", "ready"),    # crashed after it: the swap completes
    ("ready+old", "ready"),     # crashed between the two renames
    ("dict+old", "dict"),       # crashed before the old copy was cleaned up
    ("old", "old"),             # only the replaced copy is left: put it back
])
def test_recover_dictionaries_leaves_exactly_one_copy(data_dir, left, kept):
    for name in left.split("+"):
        folder = data_dir / ({"dict": "dict"}.get(name, f"dict.{name}"))
        folder.mkdir()
        (folder / "marker").write_text(name)

    restore.recover_dictionaries()

    assert [p.name for p in data_dir.iterdir()] == ["dict"]
    assert (data_dir / "dict" / "marker").read_text() == kept
