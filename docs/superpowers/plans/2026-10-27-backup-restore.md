# Backup and Restore Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A one-file whole-server backup from Admin, and a restore from Admin or the setup wizard whose database part is all or nothing (the file-system steps after the commit finish with a warning on failure, and an interrupted dictionary swap completes at the next start). The restore survives a new `TA_SECRET_KEY`, a newer app and another Postgres version.

**Architecture:** A new package `api/backup/` writes a zip holding:
- per-table CSV (Postgres `COPY`) of the reflected schema;
- a manifest;
- the data-dir dictionary files.

Credentials are re-locked under a passphrase. Restore validates the file, waits for an empty admission gate and turns maintenance on. Then, in one transaction, it:
1. drops the app tables;
2. migrates an empty schema to the backup's revision;
3. checks that the tables match exactly, then `COPY`s the rows in;
4. re-encrypts the credentials;
5. resets the sequences;
6. upgrades to head.

Dictionary files are staged before the commit and swapped in after it. The whole restore runs in a background thread, because the `jobs` table itself is replaced.

**Tech Stack:** FastAPI, SQLAlchemy 2 Core, psycopg 3 (`cursor.copy`, `psycopg.sql`), Alembic command API, `cryptography` (Scrypt, Fernet), `zipfile`, `csv` (`QUOTE_NOTNULL`, Python ≥ 3.12), React + TanStack Query, Vitest, Playwright, Caddy.

**Spec:** `docs/superpowers/specs/2026-10-27-backup-restore-design.md`

## Global Constraints

- Whole server only; restore replaces everything. No partial restore, no merge.
- Passphrase minimum 12 characters (`api.accounts.MIN_PASSWORD`), enforced only when **creating** a backup (`POST /admin/backup`). Restore never checks the length: a short passphrase fails `crypto.verify` as `WrongPassphrase`.
- App tables = `Base.metadata` tables ∪ `schema.RETIRED_TABLES` (`{"profiles"}`: created by an old revision, dropped by `c5af30ce0a6b`). Export, drop, reflect and the table-set checks use app tables only; any other table is ignored.
- The passphrase never reaches the database (no `jobs.params`), logs or the status endpoint.
- Only `api_credentials.secret_enc` is passphrase-locked. Reader-facing chapter passwords in finished `wp_publish` job results stay as they are (spec exception).
- Left out of a backup: `sessions`; jobs whose state is not in `jobs.TERMINAL` (`done`, `failed`, `cancelled`); `uploads/`. References to left-out jobs (any FK to `jobs.id`, today `ollama_chunks.job_id`) become NULL.
- Included: everything else, among it `ollama_queue_items`, `mt_cache`, `dictionaries`/`dictionary_terms` and finished job history.
- Restore upload cap 4 GiB (API and Caddy). Manifest member ≤ 1 MiB, `api_credentials` member ≤ 16 MiB, each `dict/` member ≤ `dictionary.MAX_EDICT_BYTES` (128 MiB), declared uncompressed total ≤ 32 GiB.
- KDF accepted only as `{"name": "scrypt", "salt": <b64 of 16 bytes>, "n": 2**15, "r": 8, "p": 1}` exactly (the only parameters this server writes); anything else is `BackupInvalid`.
- Restore is refused (409) while any job is `queued`/`running` or the admission gate counts work in flight. The check runs again after the upload, atomically with switching maintenance on.
- Restore transaction: `SET LOCAL lock_timeout = '30s'`; drops only `Base.metadata` tables plus `alembic_version`.
- Copy, verbatim:
  - newer revision: `This backup comes from a newer version of Translation Assistant; upgrade this server first.`
  - busy: `A job or translation is running; cancel it or wait, then try again.`
  - already restoring: `A restore is already in progress.`
  - wrong passphrase: `The passphrase is wrong.`
  - generic failure (only before the commit): `The restore failed; the server was not changed.`
  - dictionary swap failure: `The database was restored, but the dictionary files could not be replaced; download EDICT2 again in Admin → Dictionary.`
  - uploads clean-up failure: `The database was restored, but some pending uploads could not be removed; delete the files under the data directory's uploads/ folder.`
- After the commit, nothing may report the generic "not changed" copy. Post-commit failures become warnings on a `done` status (both warnings joined with a space when both happen).
- During a restore every route except `GET /restore/status` and `GET /healthz` answers 503 `{"detail": "Restore in progress"}`.
- Project rules:
  - build routers with `api_router()`;
  - handlers never `commit()`;
  - no module over ~400 lines;
  - SPA styles use tokens only;
  - regenerate `web/src/api/schema.d.ts` after API changes;
  - E2E seeds follow the CLAUDE.md conventions.

## Review Focus

1. **Work that slips in while the upload runs:** a job, an Ollama run or an MT stream that starts after the first busy check must make the restore answer 409, not commit into the new database. Task 6: `test_job_started_during_upload_blocks_restore`. Task 3: `test_gate_refuses_work_while_maintenance`.
2. **Credentials after a key change, with blank fields:** export under key A, restore under key B → every credential decrypts, and blank `name` / `endpoint_url` stay `""` (not NULL). Task 2: `test_relock_unlock_keeps_blank_strings_through_copy`. Task 5: `test_restore_with_a_new_secret_key`.
3. **Sequences after restore:** new rows get ids above the restored max. Task 5: `test_sequences_continue_after_restore`.
4. **A partial or corrupt archive:** a missing table, a wrong header, a truncated zip or a corrupt dictionary rolls back with the old data intact. Task 5: `test_missing_table_is_refused`, `test_corrupt_member_rolls_back`, `test_corrupt_dictionary_fails_before_commit`.
5. **Reloading `/restore` during maintenance:** the progress page still renders and polls while every other API call answers 503. Task 7: `restore-page.spec.ts`.

---

## File Structure

| File | Responsibility |
|---|---|
| `migrations/env.py` (modify) | Use a connection passed in `config.attributes["connection"]` when present |
| `api/backup/__init__.py` | Empty |
| `api/backup/schema.py` | Alembic and table helpers: config, head, known revision, upgrade on a connection, drop app tables, reflect app tables, reset sequences |
| `api/backup/crypto.py` | KDF (strictly validated), check value, NULL-faithful CSV credential re-lock and unlock |
| `api/backup/manifest.py` | `Manifest`, `FORMAT_VERSION`, parse and validate |
| `api/backup/state.py` | Restore status, the admission gate, maintenance |
| `api/backup/export.py` | Snapshot → zip |
| `api/backup/restore.py` | `BackupReader`, `apply()`, dictionary staging and swap, `run()`, `start()` |
| `api/backup/uploads.py` | Stream a restore upload to `TA_DATA_DIR/uploads/restore/` |
| `api/routers/backup.py`, `api/schemas/backup.py` | Routes |
| `api/main.py`, `api/jobs.py`, `api/ollama/runner.py`, `api/ollama/schedule.py`, `api/routers/ollama_editor.py`, `api/routers/mt.py` (modify) | Gate every out-of-request writer; middleware; startup clean-up |
| `web/Caddyfile` (modify) | 4 GiB route for the two restore endpoints |
| `web/src/admin/backupForm.ts` (+test), `web/src/admin/BackupPanel.tsx`, `web/src/restore/RestoreForm.tsx`, `web/src/restore/RestorePage.tsx` | SPA |
| `web/src/setup/SetupPage.tsx`, `web/src/admin/AdminPage.tsx`, `web/src/App.tsx` (modify) | Wiring |
| `web/e2e/setup.spec.ts` (modify), `web/e2e/backup.spec.ts`, `web/e2e/restore-page.spec.ts` | E2E |
| `CLAUDE.md` (modify) | Backup and restore paragraph; sanctioned-commit list |

---

### Task 1: Alembic on a passed connection, and the schema helpers

**Files:**
- Modify: `migrations/env.py`
- Create: `api/backup/__init__.py`, `api/backup/schema.py`
- Test: `tests/test_backup_schema.py`

**Interfaces:**
- Produces (`api/backup/schema.py`):
  - `alembic_config(conn: Connection | None = None) -> alembic.config.Config`: built from `<repo root>/alembic.ini` with an absolute `script_location`; `conn` is stored in `cfg.attributes["connection"]`.
  - `head() -> str`; `is_known(rev: str) -> bool`; `current_revision(conn: Connection) -> str | None`.
  - `upgrade(conn: Connection, rev: str) -> None`: `alembic.command.upgrade` on `conn`.
  - `RETIRED_TABLES = frozenset({"profiles"})`; `app_table_names() -> frozenset[str]`: `Base.metadata.tables` names ∪ `RETIRED_TABLES`.
  - `drop_app_tables(conn: Connection) -> None`: `DROP TABLE IF EXISTS <t> CASCADE` (identifiers quoted) for every name in `app_table_names()`, then `alembic_version`.
  - `reflect_app_tables(conn: Connection) -> list[Table]`: reflect only the live tables whose names are in `app_table_names()` (`MetaData.reflect(only=...)`); return them in that metadata's `sorted_tables` order. `alembic_version` and stray tables are never returned.
  - `reset_sequences(conn: Connection) -> None`: for every column with a non-null `pg_get_serial_sequence`, `setval` to `max(col)`, or to 1 with `is_called = false` when the table is empty.

- [ ] **Step 1: Write the failing tests.** All of them run inside the `db` fixture's rolled-back transaction, on `db.connection()`.

```python
def test_drop_then_upgrade_to_head_rebuilds_every_table(db):
    conn = db.connection()
    schema.drop_app_tables(conn)
    assert "users" not in inspect(conn).get_table_names()
    schema.upgrade(conn, schema.head())
    assert {t.name for t in Base.metadata.sorted_tables} <= set(inspect(conn).get_table_names())
    assert schema.current_revision(conn) == schema.head()

def test_upgrade_to_an_older_revision_stops_there(db):
    conn = db.connection(); schema.drop_app_tables(conn); schema.upgrade(conn, "fc7f71015e51")
    assert schema.current_revision(conn) == "fc7f71015e51"
    assert "volume_covers" not in {t.name for t in schema.reflect_app_tables(conn)}  # added later

def test_every_table_any_revision_creates_is_an_app_table(db):
    # walk the history one revision at a time (ScriptDirectory.walk_revisions, base → head);
    # after each upgrade, every live table except alembic_version is in app_table_names().
    # Fails when a future migration retires a table without adding it to RETIRED_TABLES.
    ...

def test_stray_tables_are_ignored(db):
    conn = db.connection(); conn.execute(text("CREATE TABLE stray_notes (id int)"))
    assert "stray_notes" not in {t.name for t in schema.reflect_app_tables(conn)}
    schema.drop_app_tables(conn)
    assert "stray_notes" in inspect(conn).get_table_names()

def test_unknown_revision_is_not_known():
    assert schema.is_known(schema.head()) and not schema.is_known("ffffffffffff")

def test_reset_sequences_continues_after_max(db, make_user):
    u = make_user(); conn = db.connection()
    conn.execute(text("UPDATE users SET id = id + 1000 WHERE id = :i"), {"i": u.id})
    schema.reset_sequences(conn)
    assert make_user(email="b@example.com").id == u.id + 1001
```

(If `volume_covers` is not created after `fc7f71015e51`, pick any table the history shows was added later. Check `migrations/versions/` for the order.)

- [ ] **Step 2: Run `pytest tests/test_backup_schema.py -v`; it fails** with an ImportError.
- [ ] **Step 3: Change `migrations/env.py`.** When `context.config.attributes.get("connection")` is set, configure with it and run in `context.begin_transaction()` without creating an engine. Otherwise keep today's path, because the pytest `engine` fixture's subprocess `alembic upgrade head` must keep working.
- [ ] **Step 4: Implement `schema.py`.** Use `ScriptDirectory.from_config`, `get_current_head()` and `get_revision()`; `CommandError`/`ResolutionError` → False.
- [ ] **Step 5: Run the new tests and `pytest tests/test_migration_*.py`; all pass.**
- [ ] **Step 6: Commit** `feat(backup): alembic on a passed connection; schema helpers`

---

### Task 2: Passphrase crypto and the manifest

**Files:**
- Create: `api/backup/crypto.py`, `api/backup/manifest.py`
- Test: `tests/test_backup_crypto.py`

**Interfaces:**
- Produces (`crypto.py`):
  - `WRONG_PASSPHRASE = "The passphrase is wrong."`; `class WrongPassphrase(Exception)`, raised everywhere as `WrongPassphrase(WRONG_PASSPHRASE)` so `str(exc)` is never empty.
  - `KDF_N, KDF_R, KDF_P = 2**15, 8, 1`.
  - `new_kdf() -> dict`.
  - `check_kdf(kdf: object) -> dict`: returns it, or raises `manifest.BackupInvalid("This backup's key settings are not valid.")` unless it is exactly the Global Constraints shape (types checked; salt base64 decodes to 16 bytes).
  - `derive(passphrase: str, kdf: dict) -> Fernet`: calls `check_kdf`. It does **not** check the passphrase length (that is the backup route's job), so restore never raises anything but `BackupInvalid` / `WrongPassphrase` for a bad passphrase.
  - `check_value(f: Fernet) -> str` (encrypts `CHECK = b"ta-web backup v1"`); `verify(f, check: str) -> None`, which raises `WrongPassphrase`.
  - `relock_csv(data: bytes, f: Fernet) -> tuple[bytes, list[int]]` and `unlock_csv(data: bytes, f: Fernet) -> bytes`: read and write with `csv.QUOTE_NOTNULL`, so an unquoted empty field is NULL (`None`) and `""` is an empty string, exactly as Postgres CSV `COPY` does. Only `secret_enc` (hex bytea `\x…`) changes. In `relock`, rows that `decrypt_secret` can't read are dropped and their `id`s returned. In `unlock`, an `InvalidToken` → `WrongPassphrase`.
- Produces (`manifest.py`):
  - `FORMAT_VERSION = 1`; `MAX_MANIFEST = 1 << 20`; `class BackupInvalid(Exception)` (its message is shown to the user).
  - `@dataclass Manifest: format: int; revision: str; created_at: str; app_version: str | None; tables: dict[str, int]; kdf: dict; check: str; skipped_credentials: list[int]`.
  - `to_json() -> bytes`.
  - `parse(raw: bytes) -> Manifest` raises `BackupInvalid`:
    - `"This is not a Translation Assistant backup."` for bad JSON, missing keys or wrong types (each field type checked; `tables` values are non-negative ints);
    - `"This backup was made by a newer backup format; upgrade this server first."` when `format != FORMAT_VERSION`.

    It also calls `crypto.check_kdf`.

- [ ] **Step 1: Write the failing tests**

```python
def test_relock_unlock_keeps_blank_strings_through_copy(db, make_user):
    # ApiCredential(name="", endpoint_url="", secret_enc=encrypt_secret("s3cret"))
    # COPY api_credentials TO STDOUT (FORMAT csv, HEADER) → bytes
    # locked, skipped = relock_csv(...); assert skipped == [] and b"s3cret" not in locked
    # DELETE the row; COPY api_credentials FROM STDIN with unlock_csv(locked, f)
    # assert row.name == "" and row.endpoint_url == "" and decrypt_secret(row.secret_enc) == "s3cret"
def test_unreadable_credential_is_skipped(db, make_user): ...  # secret_enc=b"garbage" → its id in skipped
def test_wrong_passphrase_fails_verify(): ...  # str(exc) == WRONG_PASSPHRASE
def test_short_passphrase_derives_and_fails_verify(): ...
    # check value made with a 12+ char passphrase; derive("short", kdf) works; verify → WrongPassphrase
@pytest.mark.parametrize("kdf", [
    {"name": "argon2", "salt": "AAAAAAAAAAAAAAAAAAAAAA==", "n": 2**15, "r": 8, "p": 1},
    {"name": "scrypt", "salt": "AAAAAAAAAAAAAAAAAAAAAA==", "n": 2**30, "r": 8, "p": 1},
    {"name": "scrypt", "salt": "AAAAAAAAAAAAAAAAAAAAAA==", "n": "32768", "r": 8, "p": 1},
    {"name": "scrypt", "salt": "not base64!", "n": 2**15, "r": 8, "p": 1},
    {"name": "scrypt", "salt": "AAAA", "n": 2**15, "r": 8, "p": 1},
    [],
])
def test_hostile_kdf_is_backup_invalid(kdf):
    with pytest.raises(BackupInvalid): crypto.check_kdf(kdf)
def test_manifest_round_trip_and_format_check(): ...  # round trip; format 2 → "newer backup format"
def test_manifest_wrong_types_are_invalid(): ...  # tables={"users": -1}, revision=5, not JSON
```

- [ ] **Step 2: Run them; they fail.**
- [ ] **Step 3: Implement both modules.**
- [ ] **Step 4: Run them; they pass.**
- [ ] **Step 5: Commit** `feat(backup): passphrase crypto and manifest`

---

### Task 3: Admission gate and maintenance mode

**Files:**
- Create: `api/backup/state.py`
- Modify: `api/jobs.py` (`run_next`), `api/ollama/runner.py` (each run), `api/ollama/schedule.py` (`_tick_once`), `api/routers/ollama_editor.py` (`_start` / `_work`), `api/routers/mt.py` (`_translate`), `api/main.py` (middleware), `tests/conftest.py` (autouse reset)
- Test: `tests/test_backup_state.py`

**Interfaces:**
- Produces (`state.py`, all under one `threading.Lock`; `# ponytail:` single-process note as in `api/ollama/lane.py`):
  - `@dataclass Status: phase: Literal["idle", "restoring", "done", "failed"]; done: int; total: int; message: str; error: str | None`.
  - `BUSY`, `RESTORING`: the busy and already-restoring copies. (`restore.py` holds `GENERIC`, `DICT_SWAP_FAILED` and `UPLOADS_LEFT`.)
  - `snapshot() -> Status`; `active() -> bool` (phase `restoring`).
  - `class Maintenance(Exception)`.
  - `work() -> ContextManager[None]`: raises `Maintenance` if active, else counts one unit of work in flight until exit. It is a plain `contextlib.contextmanager`, usable from sync code and around `await`s, since it only takes the lock briefly.
  - `try_begin(db: Session) -> str | None`: under the lock, returns `RESTORING` (the already-restoring copy) when the phase is `restoring`, and `BUSY` (the busy copy) when the in-flight count > 0 or any `Job.state in ("queued", "running")`. Otherwise it sets phase `restoring` (done=total=0, error None) and returns None. The phase check is what stops two concurrent uploads that both passed the router's early `active()` check from both starting.
  - `progress(done: int, total: int, message: str)`, `finish(error: str | None = None)` (phase `done`; a non-None `error` is a warning shown with success, used for the dictionary-swap copy), `fail(error: str)`.
  - `reset()` (tests only).
- Gate placement:
  - `jobs.run_next`: claims nothing while `active()`; a claimed job runs inside `with state.work():`. If `Maintenance` is raised before the claim, return False.
  - `runner`: the claim loop skips while `active()`; each run task body runs inside `work()`.
  - `schedule._tick_once`: the tick runs inside `work()`; `Maintenance` → skip silently.
  - `ollama_editor._work`: its body runs inside `work()`. `Maintenance` → emit `("error", {"message": "Restore in progress"})`.
  - `mt._translate`: the whole body (network call and `_put`) runs inside `work()`. `Maintenance` → yield the existing error event shape with "Restore in progress".
- Middleware in `create_app`: while `state.active()`, any path other than `/restore/status` and `/healthz` → `JSONResponse({"detail": "Restore in progress"}, 503)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_gate_refuses_work_while_maintenance(db):
    assert state.try_begin(db) is None
    with pytest.raises(state.Maintenance):
        with state.work(): pass
def test_try_begin_refuses_with_work_in_flight(db):
    with state.work():
        assert state.try_begin(db) == state.BUSY
    assert state.try_begin(db) is None
def test_try_begin_twice_refuses(db):
    assert state.try_begin(db) is None
    assert state.try_begin(db) == state.RESTORING
def test_try_begin_refuses_with_a_queued_job(db, make_user): ...  # jobs.enqueue → BUSY
def test_maintenance_blocks_everything_but_status_and_health(app_client, db):
    state.try_begin(db)
    assert app_client.get("/series").status_code == 503
    assert app_client.get("/healthz").status_code == 200
def test_worker_claims_nothing_while_restoring(db, make_user): ...  # queued job stays queued after run_next()
def test_running_job_counts_as_work(db, make_user, monkeypatch): ...
    # register a handler that calls state.try_begin and records the answer → BUSY
def test_runner_claims_nothing_while_restoring(...): ...  # follow tests/test_ollama_runner.py's harness
def test_tick_enqueues_nothing_while_restoring(...): ...  # follow tests/test_ollama_schedule.py; no new jobs
def test_by_hand_chunk_counts_as_work(...): ...  # follow tests/test_ollama_editor.py; while a fake backend blocks, try_begin → BUSY
def test_mt_stream_counts_as_work(...): ...  # follow tests/test_mt_router.py with a MockTransport that blocks; try_begin → BUSY
def test_mt_stream_during_maintenance_writes_no_cache(...): ...
    # state.try_begin first; call the stream generator directly (bypassing the middleware)
    # → error event "Restore in progress", no mt_cache row, transport never called
```

- [ ] **Step 2: Run them; they fail.**
- [ ] **Step 3: Implement**, with an autouse `state.reset()` fixture in `tests/conftest.py`.
- [ ] **Step 4: Run them, plus `pytest tests/test_jobs.py tests/test_jobs_api.py tests/test_ollama_*.py tests/test_mt_router.py`; all pass.**
- [ ] **Step 5: Commit** `feat(backup): admission gate and maintenance mode`

---

### Task 4: Export

**Files:**
- Create: `api/backup/export.py`
- Test: `tests/test_backup_export.py`

**Interfaces:**
- Consumes: Task 1 `current_revision`, `reflect_app_tables`; Task 2.
- Produces:
  - `EXCLUDED = frozenset({"sessions"})`.
  - `table_query(table: Table) -> sql.Composed` (built with `psycopg.sql.Identifier`):
    - `jobs` keeps only `state IN TERMINAL`;
    - every column with an FK to `jobs.id` is `CASE WHEN col IN (SELECT id FROM jobs WHERE state IN TERMINAL) THEN col END AS col`;
    - otherwise it selects all columns in table order.
  - `write(conn: Connection, out: BinaryIO, f: Fernet, kdf: dict) -> Manifest`. It works from the **reflected** schema (`reflect_app_tables`), not `Base`, so it also exports an old-revision schema for tests. For each table not in `EXCLUDED`:
    1. record `SELECT count(*) FROM (<table_query>) q` in the manifest (minus skipped credentials for `api_credentials`);
    2. stream `COPY (<table_query>) TO STDOUT (FORMAT csv, HEADER)` into `tables/<name>.csv`, sending `api_credentials` through `relock_csv`.

    Then it writes `dict/<kind>` for each kind where `dictionary.resolve(kind)[1] == "data_dir"`, and `manifest.json` last (revision = `current_revision(conn)`). It uses `zipfile.ZipFile(out, "w", ZIP_DEFLATED)` and `zf.open(name, "w", force_zip64=True)`, so `out` may be non-seekable.
  - `stream(f: Fernet, kdf: dict) -> Iterator[bytes]`: its own `api.db.engine` connection with `isolation_level="REPEATABLE READ"` and `postgresql_readonly=True`. It runs `write` into a writer that yields buffered chunks of about 1 MiB, then closes.
  - `filename(today: date) -> str` → `ta-backup-YYYY-MM-DD.zip`.

- [ ] **Step 1: Write the failing tests** (`write` into `BytesIO` on `db.connection()`)

```python
def test_sessions_and_unfinished_jobs_are_left_out(db, make_user): ...
    # a session; done, cancelled and running jobs; ollama_chunk → running job, another → done job
    # no tables/sessions.csv; jobs.csv has done+cancelled only; chunk job_ids: NULL and kept
def test_every_foreign_key_to_jobs_is_nulled(db):
    for t in schema.reflect_app_tables(db.connection()):
        for fk in t.foreign_keys:
            if fk.column.table.name == "jobs":
                assert "CASE WHEN" in export.table_query(t).as_string(db.connection().connection.driver_connection)
def test_credentials_are_relocked(db, make_user): ...
def test_counts_are_rows_not_lines(db, make_user): ...  # a series wp_summary with "\n\n" → manifest count 1
def test_publish_passwords_stay_as_they_are(db, make_user): ...  # documents the spec exception: done wp_publish job with a password in result_json is in jobs.csv
def test_dict_files_from_data_dir_are_included(db, tmp_path, monkeypatch): ...
def test_filename(): ...
```

- [ ] **Step 2: Run them; they fail.**
- [ ] **Step 3: Implement.** Get the psycopg cursor with `conn.connection.driver_connection.cursor()`.
- [ ] **Step 4: Run them; they pass.**
- [ ] **Step 5: Commit** `feat(backup): export a whole-server zip`

---

### Task 5: Restore

**Files:**
- Create: `api/backup/restore.py`
- Modify: `api/main.py` (lifespan: `restore.recover_dictionaries()`)
- Test: `tests/test_backup_restore.py`, `tests/test_backup_run.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `class RestoreError(Exception)`: its message is shown to the user.
  - `BackupReader.open(path: Path, passphrase: str) -> BackupReader` validates synchronously and raises `BackupInvalid` or `WrongPassphrase`:
    - the zip opens; `BadZipFile` → `"This file is not a backup or is damaged."`;
    - every member name matches `manifest.json`, `tables/<[a-z_0-9]+>.csv` or `dict/(edict|conjugations)`;
    - the member size caps and the 32 GiB total hold;
    - `manifest.parse` (read at most `MAX_MANIFEST + 1` bytes) succeeds;
    - `schema.is_known(m.revision)`, else the newer-revision copy;
    - `crypto.verify` passes;
    - the set of `m.tables` names equals the set of `tables/` members.

    Attributes: `manifest`, `fernet`, `path`. Methods: `rows(table: str) -> BinaryIO`, `close()`.
  - `stage_dictionaries(reader: BackupReader) -> Path | None`. It writes every `dict/` member (read with the cap) into a fresh `TA_DATA_DIR/dict.restore/` under `dictionary.FILENAMES` names, validating each with the same check `dictionary.install` applies (reuse its validation; refactor a `validate(kind, data) -> int` out of `install` if needed). A failure → `BackupInvalid("The backup's <kind> dictionary is damaged.")`. It returns the staged dir, or None when no kind resolves to `data_dir` and the backup has no dict members.
  - Dictionary directories under `TA_DATA_DIR`: `dict.restore/` (staged, maybe never committed), `dict.ready/` (committed, waiting to be swapped in), `dict.old/` (the replaced copy).
  - `mark_committed(staged: Path | None) -> None`: right after the commit, `dict.restore` → `dict.ready` (no-op for None). This rename is the only record that the database committed.
  - `swap_dictionaries() -> None`, a no-op without `dict.ready/`:
    1. if `dict.old/` exists, `rmtree` it (a leftover from an earlier run);
    2. if `dict/` exists, rename it to `dict.old/` (a fresh install may have none);
    3. rename `dict.ready/` → `dict/`;
    4. `dictionary._drop_cached()`;
    5. `rmtree(dict.old, ignore_errors=True)` is best-effort cleanup outside the error path; a failure is only logged.

    Steps 1–3 may raise `OSError`; the caller turns it into the swap-failure warning. `dict.ready/` then stays for the next start.
  - `recover_dictionaries() -> None` (lifespan, before the worker starts):
    1. `rmtree(dict.restore, ignore_errors=True)` (never committed);
    2. if `dict.ready/` exists, `swap_dictionaries()` (an `OSError` is logged, not raised, so the app still starts);
    3. if `dict/` exists, `rmtree(dict.old, ignore_errors=True)`. When `dict/` is missing, `dict.old/` is the only copy left: rename it back to `dict/`.
  - `apply(conn: Connection, reader: BackupReader, *, from_setup: bool, progress: Callable[[int, int, str], None]) -> None`, in the caller's transaction:
    1. `SET LOCAL lock_timeout = '30s'`.
    2. If `from_setup`: `pg_advisory_xact_lock(accounts.SETUP_LOCK)`, and if not `accounts.needs_setup` raise `RestoreError("Setup is already complete; sign in instead.")`.
    3. `drop_app_tables`, then `upgrade(conn, m.revision)`.
    4. `tables = reflect_app_tables(conn)`. The set of `{t.name} - {"sessions"}` must equal `set(m.tables)`, else `BackupInvalid("This backup is incomplete.")`.
    5. For each table in order: read the member's header row (`csv.reader` on the first line); the header columns must equal the table's column set, else `BackupInvalid("This backup does not match its recorded version.")`. Then `COPY {table} ({cols}) FROM STDIN (FORMAT csv, HEADER)` built with `sql.Identifier`, streaming the member in 1 MiB chunks; `api_credentials` goes through `unlock_csv`. Afterwards `SELECT count(*)` must equal `m.tables[name]`, else the "incomplete" copy. Report `progress(rows_done, rows_total, name)`.
    6. `reset_sequences`, then `upgrade(conn, schema.head())`.
  - `clear_uploads(keep: Path) -> bool`: deletes everything under `TA_DATA_DIR/uploads/` except `keep`, carrying on past a file it can't delete (logged). Returns False when anything was left behind.
  - `run(reader: BackupReader, from_setup: bool) -> None`, the thread body, in two separate `try` blocks so no post-commit error can reach the pre-commit handlers:
    1. **Before the commit:** `staged = stage_dictionaries(reader)`, then `with engine.begin() as conn: apply(..., progress=state.progress)`. Handlers:
       - `RestoreError`/`BackupInvalid` → `state.fail(str(exc))`; `WrongPassphrase` → `state.fail(WRONG_PASSPHRASE)`;
       - `OperationalError` with SQLSTATE `55P03` → `state.fail("The database was busy; try again when nothing is running.")`;
       - anything else → `log.exception`, then `state.fail(GENERIC)`.

       In each case delete the staged dir and return.
    2. **After the commit** (each step catches its own errors, logs them and adds a warning; none calls `state.fail`):
       1. `mark_committed(staged)` and `swap_dictionaries()`; an `OSError` adds `DICT_SWAP_FAILED`;
       2. `clear_uploads(keep=reader.path)`; False adds `UPLOADS_LEFT`;
       3. `engine.dispose()`;
       4. `state.finish(" ".join(warnings) or None)`.
    3. `finally`: `reader.close()`, then delete `reader.path` (an `OSError` there is logged only).
  - `start(reader: BackupReader, from_setup: bool) -> None`: starts a daemon `threading.Thread(target=run, ...)`. The caller has already won `state.try_begin`. It is the router's seam.

- [ ] **Step 1: Write the failing tests.** `apply` runs inside `with conn.begin_nested():` on `db.connection()`. Backups are built with `export.write` into `tmp_path`.

```python
def test_round_trip_restores_every_kind_of_row(db, make_user, tmp_path): ...
    # seed: users, series, volume, documents, lines, image, cover, glossary, custom words,
    #   user settings, shortcuts, credentials (blank name), server_settings, invites,
    #   dictionaries + dictionary_terms (ARRAY headwords/pos), mt_cache, ollama_queue_items,
    #   ollama_chunks/suggestions, work_sessions, done/cancelled and running jobs, a session
    # export; add a user and delete a series; apply
    # compare every seeded table row-for-row (SELECT * ORDER BY pk) with the pre-export snapshot,
    #   except: sessions empty, running job gone, its chunk's job_id NULL
def test_restore_with_a_new_secret_key(db, make_user, tmp_path, monkeypatch): ...
def test_sequences_continue_after_restore(db, make_user, tmp_path): ...  # users, series, lines
def test_wrong_passphrase_is_refused_before_anything(db, tmp_path): ...
def test_newer_revision_is_refused(db, tmp_path): ...
def test_stray_member_is_refused(db, tmp_path): ...
def test_truncated_zip_is_refused(db, tmp_path): ...  # cut the file in half → BackupInvalid
def test_oversized_manifest_is_refused(db, tmp_path): ...
def test_missing_table_is_refused(db, make_user, tmp_path): ...
    # rebuild the zip without tables/mt_cache.csv and with mt_cache removed from the manifest;
    # open passes, apply raises BackupInvalid("This backup is incomplete."); old data intact
def test_wrong_header_is_refused(db, make_user, tmp_path): ...  # rename a column in users.csv
def test_corrupt_member_rolls_back(db, make_user, tmp_path): ...  # garbage row in lines.csv; old data intact
def test_failure_mid_load_changes_nothing(db, make_user, tmp_path, monkeypatch): ...
def test_setup_restore_refuses_when_a_user_exists(db, make_user, tmp_path): ...
def test_credentials_revision_backup_lands_at_head(db, tmp_path): ...
    # drop; upgrade to 7bb38754e763's down_revision; raw-SQL rows incl. a user with mt_enabled
    # ["ollama"]; export.write; apply → current_revision == head; user has an ollama credential
def test_structural_old_backup_lands_at_head(db, tmp_path): ...
    # drop; upgrade to dc0385482445 (the parent of 44f4d937ee05_volume_covers, so before both
    # volume covers and 7d5a5cb22308_series_archive_status_source);
    # raw-SQL user, series, volume, document (in that volume), line, and a document_images row
    # with is_cover = true; export.write (it reflects the old schema); apply
    # → head; series.status == "ongoing", series.archived_at is NULL; the rows are there;
    #   the volume has a volume_covers row and the image no longer carries a cover flag
def test_stray_table_is_neither_exported_nor_dropped(db, make_user, tmp_path): ...
    # CREATE TABLE stray_notes + a row; export → no tables/stray_notes.csv; apply succeeds;
    # stray_notes and its row are still there
def test_damaged_credential_reports_the_wrong_passphrase_copy(db, make_user, tmp_path): ...
    # valid check value but a corrupted secret_enc token in api_credentials.csv → apply raises
    # WrongPassphrase with str(exc) == WRONG_PASSPHRASE
def test_corrupt_dictionary_fails_before_commit(tmp_path, monkeypatch): ...  # dict/edict garbage → BackupInvalid from stage_dictionaries
def test_staging_without_edict_removes_the_old_file(tmp_path, monkeypatch): ...
    # data dir has dict/edict; backup has no dict members → after mark_committed + swap, dict/edict is gone
def test_swap_without_an_existing_dict_dir(tmp_path, monkeypatch): ...
    # fresh data dir (no dict/); stage, mark_committed, swap → dict/edict2 present, no dict.old
def test_swap_survives_old_dir_cleanup_failure(tmp_path, monkeypatch): ...
    # rmtree(dict.old) raises → swap returns normally, dict/ is the new copy, caches dropped
@pytest.mark.parametrize("left", [
    "restore+dict",   # crash before the commit → dict.restore deleted, dict kept
    "ready+dict",     # crash after the commit, before any rename → swapped
    "ready+old",      # crash between the two renames → swapped, old deleted
    "dict+old",       # crash before old-dir cleanup → old deleted
    "old",            # only dict.old left → renamed back to dict
])
def test_recover_dictionaries_leaves_exactly_one_copy(tmp_path, monkeypatch, left): ...
```

`tests/test_backup_run.py`, with `apply` monkeypatched:

```python
def test_run_failure_reports_generic_and_cleans_up(tmp_path, monkeypatch): ...  # ValueError → GENERIC; staged dir and zip gone
def test_run_restore_error_is_verbatim(tmp_path, monkeypatch): ...
def test_run_wrong_passphrase_copy_is_never_empty(tmp_path, monkeypatch): ...  # apply raises WrongPassphrase() → error == WRONG_PASSPHRASE
def test_run_swap_failure_is_reported_after_commit(tmp_path, monkeypatch): ...  # swap raises OSError → phase "done", error DICT_SWAP_FAILED, dict.ready kept
def test_run_uploads_cleanup_failure_is_a_warning(tmp_path, monkeypatch): ...
    # clear_uploads returns False → phase "done" (never "failed", never GENERIC), error UPLOADS_LEFT,
    # the dictionaries were still swapped
def test_run_keeps_the_open_zip_while_clearing_uploads(tmp_path, monkeypatch): ...  # other uploads gone; zip deleted only after close
```

- [ ] **Step 2: Run them; they fail.**
- [ ] **Step 3: Implement `restore.py` and the lifespan clean-up.**
- [ ] **Step 4: Run `pytest tests/test_backup_*.py -v`; all pass. Then run the full `pytest` once:** a restore inside the test transaction must not leak into other tests.
- [ ] **Step 5: Commit** `feat(backup): validated, transactional restore`

---

### Task 6: API routes and Caddy

**Files:**
- Create: `api/routers/backup.py`, `api/backup/uploads.py`, `api/schemas/backup.py`
- Modify: `api/main.py` (include the router; call `uploads.sweep` in the lifespan), `web/Caddyfile`
- Test: `tests/test_backup_api.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces:
  - `uploads.save(upload: UploadFile) -> Path`: streams to `TA_DATA_DIR/uploads/restore/<uuid>.zip`, capped at `MAX_BACKUP_BYTES = 4 << 30` (413 over it), following the `api/tadb_uploads.py` pattern. `uploads.sweep()` deletes restore uploads older than 24 h.
  - `RestoreStatusOut`, a mirror of `state.Status`.
  - Routes (one `api_router()`, no prefix):
    - `POST /admin/backup` (`require_admin`, form `passphrase`):
      - 409 if `state.active()`;
      - 409 if `current_revision != head`;
      - 422 on a short passphrase;
      - otherwise a `StreamingResponse(export.stream(f, kdf), media_type="application/zip")` with the `attachment` helper from `api/routers/exports.py` and `export.filename(date.today())`.
    - `POST /admin/restore` (`require_admin`, `file`, form `passphrase`, form `confirm`): 422 unless `confirm == "RESTORE"`, then `_start(from_setup=False)`.
    - `POST /setup/restore` (no auth, `file`, `passphrase`): 409 `"Setup is already complete; sign in instead."` unless `accounts.needs_setup(db)`, then `_start(from_setup=True)`.
    - `_start`:
      1. 409 `RESTORING` if `state.active()` (a cheap early answer; the real guard is step 5);
      2. a cheap busy pre-check (`state.try_begin`'s busy logic without beginning) → 409 BUSY;
      3. `uploads.save`;
      4. `BackupReader.open`; on `BackupInvalid`/`WrongPassphrase` (copy `WRONG_PASSPHRASE`), answer 422. On **any** exception from `open`, delete the file before answering or re-raising, so nothing is left in `uploads/restore/`;
      5. **`state.try_begin(db)`**; if it returns a reason (`RESTORING` or `BUSY`), close the reader, delete the file and answer 409 with it;
      6. `restore.start(reader, from_setup)` → 202 `RestoreStatusOut`.
    - `GET /restore/status` (no auth) → `RestoreStatusOut`.
  - Caddyfile: `@restore path /api/admin/restore /api/setup/restore` with `request_body @restore { max_size 4GiB }`; add both paths to the `@small` exclusions; update the comment.

- [ ] **Step 1: Write the failing tests.** Monkeypatch `restore.start` to record its args; the real load is Task 5's. Fixtures in the file:
  - `admin_login`: `make_user(is_admin=True)` plus `login`;
  - `backup_file`: `export.write` on `db.connection()` into `tmp_path / "b.zip"`, passphrase `"correct horse battery"`.

```python
def test_backup_requires_admin(app_client, make_user, login): ...  # anonymous 401, non-admin 403
def test_backup_downloads_a_zip_with_a_manifest(app_client, admin_login, monkeypatch): ...
    # export.stream patched to write via export.write on the test connection; filename ta-backup-<today>.zip
def test_short_passphrase_is_422(app_client, admin_login): ...
def test_admin_restore_requires_admin(app_client, make_user, login, backup_file): ...  # 401/403, start not called
def test_restore_needs_the_confirm_word(app_client, admin_login, backup_file): ...
def test_restore_refused_while_a_job_is_queued(app_client, admin_login, backup_file, db): ...  # 409 BUSY
def test_job_started_during_upload_blocks_restore(app_client, admin_login, backup_file, db, monkeypatch): ...
    # patch uploads.save to enqueue a job (simulating one that starts mid-upload) then save
    # → 409 BUSY, start not called, phase "idle", upload deleted
def test_work_in_flight_during_upload_blocks_restore(...): ...  # patch BackupReader.open to enter state.work() and hold it → 409
def test_restore_wrong_passphrase_is_422_and_nothing_starts(app_client, admin_login, backup_file): ...
@pytest.mark.parametrize("endpoint", ["/admin/restore", "/setup/restore"])
def test_short_restore_passphrase_is_422_not_500(app_client, make_user, login, backup_file, endpoint): ...
    # passphrase "short" → 422 "The passphrase is wrong.", start not called, uploads/restore/ empty
    # (log in as admin for /admin/restore; no users for /setup/restore)
def test_second_restore_while_restoring_is_409(app_client, admin_login, backup_file, db): ...
    # state.try_begin(db) first (a restore already running) → 409 "A restore is already in progress.";
    # simulate the race by patching state.active to return False for the early check
def test_restore_corrupt_zip_is_422(app_client, admin_login, tmp_path): ...
def test_restore_starts_and_answers_202(app_client, admin_login, backup_file): ...  # phase "restoring", from_setup False
def test_setup_restore_only_without_users(app_client, make_user, backup_file): ...
def test_setup_restore_starts_without_users(app_client, backup_file): ...
def test_status_needs_no_login_and_works_during_maintenance(app_client, db): ...
```

- [ ] **Step 2: Run them; they fail.**
- [ ] **Step 3: Implement**, then run `ruff check .` and `pytest tests/test_commit_boundary.py`.
- [ ] **Step 4: Run `pytest`; all pass.**
- [ ] **Step 5: Run `cd web && npm run gen:api`.**
- [ ] **Step 6: Commit** `feat(backup): backup, restore and status routes; 4 GiB Caddy route`

---

### Task 7: SPA — Admin panel, setup choice, progress page

**Files:**
- Create: `web/src/admin/backupForm.ts`, `web/src/admin/backupForm.test.ts`, `web/src/admin/BackupPanel.tsx`, `web/src/restore/RestoreForm.tsx`, `web/src/restore/RestorePage.tsx`, `web/e2e/backup.spec.ts`, `web/e2e/restore-page.spec.ts`
- Modify: `web/src/admin/AdminPage.tsx`, `web/src/setup/SetupPage.tsx`, `web/src/App.tsx`, `web/e2e/setup.spec.ts`, and a stylesheet under `web/src/styles/` only if needed (tokens only)

**Interfaces:**
- Consumes: Task 6 routes and the regenerated `schema.d.ts`.
- Produces:
  - `backupProblem(pass: string, repeat: string, restoring: boolean): string | null` → `"A restore is in progress."` / `"Use at least 12 characters."` / `"The passphrases do not match."` / null, checked in that order.
  - `BackupPanel` (section "Backup & restore"):
    - It reads `GET /restore/status` with `useQuery` (`refetchInterval` 5 s), so `restoring` = phase `restoring`.
    - Backup half: a native `<form method="post" action="/api/admin/backup">`. The `passphrase` field is posted; the repeat field has no `name`. The submit button is disabled while `backupProblem(...)` is non-null, and the problem text shows beneath it. A hint says the passphrase is needed to restore saved passwords and keys.
    - Restore half: `<RestoreForm endpoint="/api/admin/restore" confirmWord="RESTORE" />`, with copy saying it replaces everything on this server.
  - `RestoreForm({ endpoint, confirmWord? })`: `endpoint` is the full `/api/...` path. It posts `FormData` (`file`, `passphrase`, and `confirm` when `confirmWord` is set) with `fetch(endpoint, { method: "POST", body, credentials: "same-origin" })`. On 202 it navigates to `/restore`; on 4xx it shows `detail`.
  - `RestorePage` at route `/restore`, registered as a **sibling of the `SetupGate` route** in `App.tsx` (outside `SetupGate`, `RequireAuth` and `Shell`). It calls only `/api/restore/status` (raw `fetch` or `api.GET`) and polls every second while the phase is `restoring`, showing a progress bar with `done/total` and `message`.
    - `done`: `queryClient.clear()`, then "Restore finished. Sign in with an account from the backup.", any `error` as a warning, and a link to `/login`.
    - `failed`: shows `error` and "The server was not changed."
    - `idle`: shows "No restore is running." and a link to `/`.
  - `SetupPage` step 0 is a choice between two buttons: **"Start fresh"** (shows today's `CreateAdmin` form, whose submit button stays "Create admin") and **"Restore from a backup"** (shows `<RestoreForm endpoint="/api/setup/restore" />`). The choice button is not called "Create admin", so the submit button's accessible name stays unique.

- [ ] **Step 1: Write the failing Vitest** for `backupProblem`: one case per return value, plus `restoring` winning over a short passphrase.
- [ ] **Step 2: `cd web && npm test`; it fails. Implement `backupForm.ts`; it passes.**
- [ ] **Step 3: Build the components and wire the routes.**
- [ ] **Step 4: Update `web/e2e/setup.spec.ts`:** all three flows click "Start fresh" before filling the form.
- [ ] **Step 5: Write `web/e2e/restore-page.spec.ts`.** `page.route("**/api/**")` answers 503 `{"detail": "Restore in progress"}` for everything except `**/api/restore/status`, which answers `restoring` (done 3 of 10) twice, then `done`. `page.goto("/restore")` shows the progress bar, then the finished message with the login link. A second test answers `failed` with `error: "The restore failed; the server was not changed."` and asserts that text.
- [ ] **Step 6: Write `web/e2e/backup.spec.ts`:** sign in as the e2e admin, open Admin, fill the passphrase twice, click Download backup, `page.waitForEvent("download")`, and check that `suggestedFilename()` matches `/^ta-backup-\d{4}-\d{2}-\d{2}\.zip$/`. No real restore in e2e: it would replace the shared `ta_e2e` database.
- [ ] **Step 7: Run `npm test`, the typecheck, and `npm run e2e` (the full suite); all pass.**
- [ ] **Step 8: Verify in the browser** with `preview_start` on the dev stack. Screenshot the Admin panel, the setup choice, and the form showing "The passphrase is wrong." after a wrong passphrase. The progress and failed states are covered by `restore-page.spec.ts`.
- [ ] **Step 9: Commit** `feat(web): backup & restore panel, setup restore choice, restore progress`

---

### Task 8: Docker round trip and docs

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Manual round trip on the compose stack.**
  1. `docker compose up -d --build`, then download a backup from Admin.
  2. Bring the stack up on a fresh Postgres volume with a **different** `TA_SECRET_KEY`. The setup page offers the choice; restore from the file.
  3. Check that you can sign in with the old account, that the library, images and covers are present, that the saved credentials show as set and decrypt (for example, a DeepL or WordPress test if one is configured), and that EDICT2 is present.
  4. Put the original volume and key back afterwards.
- [ ] **Step 2: Update CLAUDE.md.**
  - Add a "Backup and restore" paragraph covering:
    - `api/backup/` and the file format;
    - the admission gate (every out-of-request writer goes through `state.work()`);
    - maintenance mode;
    - what's left out, and the chapter-password exception;
    - the dictionary staging and swap;
    - the 4 GiB cap;
    - that the passphrase is never stored;
    - a link to the spec.
  - Add the restore transaction (`api/backup/restore.py` `run`) to the sanctioned commits outside the route boundary.
- [ ] **Step 3: Run `ruff check .`, `pytest`, `cd web && npm test && npm run e2e`; all pass.**
- [ ] **Step 4: Commit** `docs: backup and restore`
