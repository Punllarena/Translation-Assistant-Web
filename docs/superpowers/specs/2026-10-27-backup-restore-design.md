# Backup and restore — design

Date: 2026-10-27

## Why

The admin wants to upgrade or move the server (new machine, new Postgres, possibly a new
`TA_SECRET_KEY`) and keep everything: accounts, libraries, images, covers, glossaries,
settings. Today the only way is a hand-run `pg_dump`, which ties the dump to a Postgres
version and leaves saved credentials unreadable when the secret key changes.

All content already lives in Postgres: lines, `document_images.data`, `volume_covers.data`,
Yomitan `dictionary_terms`. `TA_DATA_DIR` holds only `dict/` (EDICT2, Conjugations) and
`uploads/` (pending imports). So "the database and the media" means the database plus the
`dict/` files.

## Goals

- **Backup:** Admin → "Backup & restore" downloads one file holding the whole server.
- **Restore:** upload that file on another (or the same) server. It replaces everything
  there.
- **The setup wizard** (`/setup`, shown while no user exists) offers a choice: "Start fresh"
  (today's Create admin form) or "Restore from a backup". A fresh install never needs a throwaway admin.
- **It survives a key change.** Saved credentials (`api_credentials.secret_enc`, the only
  thing `TA_SECRET_KEY` protects; see `api/security.py`) are re-locked with a passphrase the
  admin types at backup time. Restore unlocks them with that passphrase and re-encrypts them
  with the new server's key.
- **It survives an app upgrade.** A backup from an older schema revision restores onto newer
  code.
- **It survives a Postgres version change.** The file is in the app's own format, not a
  `pg_dump`.

## Non-goals

- Partial restore (one user, one series) or merging into an existing server. Whole server
  only, and everything is replaced.
- Scheduled or automatic backups, and off-site storage.
- Encrypting the whole file. Only the credentials are locked; translations are stored as they
  are (my call; the admin did not ask for full-file encryption).
- Restoring a backup from a *newer* schema than the server runs.

## Anti-goals (a failure even if it "works")

- A failed or cancelled restore leaves the database half-replaced. The database restore is all
  or nothing: on any error before the commit the server keeps its old data, untouched. The
  file-system steps after the commit (the dictionary swap, clearing `uploads/`) can still fail;
  then the restore finishes with a plain warning, never with "the server was not changed".
- A wrong passphrase is found only after the old data is gone. The passphrase is checked
  before anything is changed.
- The backup holds credentials in plain text, or the passphrase lands in the database (for
  example in `jobs.params`) or in logs. "Credentials" means `api_credentials`, the user's own
  keys and passwords for other services. Reader-facing WordPress chapter passwords (generated
  post passwords, already stored in plain text in finished `wp_publish` job results and shown on
  the jobs page) are content and stay as they are. This exception is my call.
- The browser holds a multi-hundred-MB backup in memory.

## What goes in the file

A zip (stored or deflated per member, the builder's call) with:

- `manifest.json`: format version (start at 1), the alembic revision the data matches, the app
  version if known, created-at, the table list with row counts, the credential KDF parameters
  and salt, and a passphrase check value (a known string encrypted with the derived key, so a
  wrong passphrase is caught even when there are no credentials).
- One member per table: its rows, in a layout that round-trips every column type in use
  (bytea, JSONB, Numeric, timestamptz, arrays if any). My call: Postgres
  `COPY ... TO STDOUT (FORMAT csv, HEADER)` through psycopg 3's copy API, since it is
  version-portable and handles bytea as hex. The builder may choose another faithful format.
- `api_credentials` rows have `secret_enc` replaced by the passphrase-locked value. A
  credential that cannot be decrypted with the current key is left out and listed in the
  manifest as skipped.
- `dict/` files that live under `TA_DATA_DIR` (not ones pointed to by `TA_EDICT_PATH` /
  `TA_CONJUGATIONS_PATH`).

**Left out:**

- `sessions`: everyone signs in again after a restore.
- Jobs still `queued` or `running` (finished means succeeded, failed or cancelled; finished job
  history is kept). `ollama_queue_items` are kept: they are the users' waiting requests, and the
  new server's scheduler starts runs for them in the next night window. Any reference to a left-out
  job (for example `ollama_chunks.job_id`) is set to NULL on the way out.
- `uploads/`.
- The `alembic_version` row, which is replaced by the manifest's revision.

Everything else is included, `mt_cache` and Yomitan dictionaries too: "whole server" means
whole.

The export runs in one `REPEATABLE READ`, read-only transaction, so the file is a consistent
snapshot while people keep working.

## Passphrase crypto (my call)

A new backup's passphrase is at least 12 characters, matching `MIN_PASSWORD`. Restore does
not check the length: a short passphrase simply fails the check value as a wrong passphrase, so
raising `MIN_PASSWORD` later never locks out older backups. The key is derived with
scrypt from `cryptography` (random salt; parameters recorded in the manifest) and used as a
Fernet key. The passphrase lives only in the request that uses it: never in a job row, never
logged.

## Backup flow

Admin page, new panel "Backup & restore":

1. The admin types the passphrase twice and clicks Download backup.
2. The browser downloads through a native form POST (`POST /admin/backup`, form field
   `passphrase`), so the zip streams to disk instead of into a JS blob. This is unlike
   `downloadBlob` used elsewhere. The response streams the zip as it is written; the
   filename includes the date, e.g. `ta-backup-2026-10-27.zip`.
3. Admin only, and refused (409) while a restore is in progress.

## Restore flow

Entry points:

- Admin → "Backup & restore" → Restore (admin only).
- `/setup` → "Restore from a backup", open while no user exists, the same trust model as the
  first-admin claim. It takes the `SETUP_LOCK` advisory lock, and if a user appears meanwhile
  it answers 409 like `/setup/admin`.

Steps:

1. The admin picks the file, types the passphrase, and (Admin tab only) types a confirmation
   word, because this wipes a live server. The upload streams to
   `TA_DATA_DIR/uploads/restore/` (pattern of `api/tadb_uploads.py`; swept after 24 h).
   Upload cap: my call 4 GiB, as a single streamed request (no chunked or resumable upload),
   with a matching Caddy route limit (today 1 GiB for ta.db) and no short proxy timeouts on
   that route. Uvicorn runs one worker, which fits the single-process maintenance flag.
2. **Validate before touching anything:** zip sanity (members read by name, never extracted;
   size limits in the spirit of `epub_safety.py`), manifest format version known, revision
   known to this server and not newer than head, passphrase check value decrypts. A failure
   here is a 422 with a plain message, and the server is unchanged.
3. **Run the restore in one database transaction** (Postgres DDL is transactional):
   1. Drop every app table and `alembic_version`.
   2. Run the alembic migrations from base up to the manifest's revision on that same
      connection. `migrations/env.py` must accept a connection passed in through
      `config.attributes`.
   3. Load every table's rows.
   4. Re-encrypt credentials with this server's key.
   5. Reset every sequence to the table's max id.
   6. Run the migrations from that revision to head, so data migrations run on the restored
      rows.
   7. Commit.

   On any error, roll back: the old server is intact. This is one of the sanctioned commits
   outside the route boundary; add it to that list in CLAUDE.md.
4. **Dictionary files:**
   - Before the commit, read every `dict/` member (each capped at the dictionary module's
     128 MiB), validate it the way `api/dictionary.py` validates an upload, and stage the
     *complete* replacement directory at `TA_DATA_DIR/dict.restore/`. A backup with no EDICT2
     member stages a directory without one, so the old server's file goes away. A dictionary
     that fails validation fails the restore before the commit.
   - Right after the commit, rename `dict.restore/` → `dict.ready/`. That rename is the marker
     that the database committed: `dict.restore/` means "staged, maybe never committed",
     `dict.ready/` means "committed, swap it in".
   - Then swap: if `dict/` exists, rename it to `dict.old/` (a fresh install may have no
     `dict/`); rename `dict.ready/` → `dict/`; drop the in-process dictionary caches. Deleting
     `dict.old/` comes last and is best effort: a failure there is logged, not reported.
   - If a rename fails (a filesystem error after the database committed), the status says so
     plainly: "The database was restored, but the dictionary files could not be replaced;
     download EDICT2 again in Admin → Dictionary." `dict.ready/` stays, so the next start
     completes the swap.
   - At startup, recover instead of blindly deleting: delete `dict.restore/` (never committed);
     if `dict.ready/` exists, complete the swap above; then delete `dict.old/` only when `dict/`
     exists. A crash at any point between the commit and the end of the swap therefore leaves
     exactly one dictionary directory in place after the next start.
   - Files supplied through `TA_EDICT_PATH` / `TA_CONJUGATIONS_PATH` are never touched.
5. Afterwards, no sessions exist. The SPA shows "Restore finished, sign in with an account
   from the backup" and goes to the login page.

**It cannot be a normal job.** The `jobs` table and the user who would own the job are
replaced mid-run. My call: the restore runs in a background thread in the API process, with
its state (phase, done/total, message, error) held in memory and exposed by
`GET /restore/status`, which needs no login. The status holds no data from the backup beyond
counts. While a restore runs, the server is in **maintenance mode**: every other API route
answers 503 with "Restore in progress", the job worker, the Ollama runner and the scheduler
tick don't claim work, and a second restore or a backup is refused. The SPA shows a full-page
progress view and polls the status. Single-process only; note it the way `lane` notes its
limit.

**Work already running (my call):** a restore is refused (409, naming what is running) while
any job is queued or running, or any work that writes outside a request is in flight:
- a job handler,
- an Ollama run,
- a scheduler tick,
- a by-hand Ollama chunk,
- an `/mt/stream` translation (which commits its cache row in its own session after the
  network call).

All of these go through one **admission gate**: an in-process lock with a count of work in
flight. Work enters the gate before it starts and leaves when it ends, and it can't enter while
maintenance is on. The restore checks again *after* the upload and validation, and turns
maintenance on under the same lock, so nothing can slip in between the check and the switch.
The restore transaction also sets a `lock_timeout` (around 30 s) as a last guard, failing
cleanly instead of hanging. The worker, the Ollama runner and the scheduler tick are asyncio
tasks in the API process (`api/main.py` lifespan), so an in-memory gate reaches them.

**Which tables are app tables:** the tables in `Base.metadata`, plus the retired tables some
old revision created and a later migration drops (today only `profiles`), plus `alembic_version`.
Backup exports only app tables, restore drops only app tables, and the table checks compare only
app tables. Any other (stray) table is ignored: never exported, never dropped, never loaded. A
stray table that clashes with a migration makes the restore fail and roll back.

**`uploads/` after a restore:** after the commit, the restore deletes everything under
`TA_DATA_DIR/uploads/` except the restore file itself, which is deleted after it is closed, at
the end. If some files can't be deleted, the restore still finishes (the database committed)
with the warning "The database was restored, but some pending uploads could not be removed;
delete the files under the data directory's uploads/ folder." The 24-hour sweep removes them
later anyway.

**An incomplete backup is refused:** after migrating to the backup's revision, the set of tables
in the manifest must equal the reflected schema's tables minus `sessions` and
`alembic_version`. Each table file's header must match the table's columns, and each loaded row
count must match the manifest. Any mismatch rolls back. Pending ta.db and Yomitan uploads
are keyed by user id, and those ids now belong to other people.

## Version handling

- Backup revision == head: load directly.
- Older and known: migrate the empty schema to it, load, upgrade to head (step 3 above).
- Replaying old migrations uses today's code and the *new* server's environment. For example,
  `7bb38754e763_ollama_own_server` reads `TA_OLLAMA_URL` and calls `encrypt_secret`. That is
  accepted (my call): an old backup lands as if that server had been upgraded in place on the
  new machine. Credentials are re-encrypted before the upgrade to head (step 3.4 before 3.6),
  so `encrypt_secret` in a migration sees the new key. The old-revision test should cover a
  revision before `7bb38754e763`.
- Newer or unknown: refuse with "This backup comes from a newer version of Translation
  Assistant; upgrade this server first."

## Code layout (guidance)

- `api/backup/` package: `manifest`, `crypto` (passphrase KDF, check value, credential
  re-lock), `export` (snapshot → zip stream), `restore` (validate, transactional load),
  `state` (maintenance flag and status). No module over ~400 lines.
- Router `api/routers/backup.py` built with `api_router()`; the setup-wizard restore entry
  goes in `api/routers/setup.py` or shares the same handler.
- SPA: `web/src/admin/BackupPanel.tsx`, a restore choice in the setup page, and a restore
  progress view. Styles use tokens only.
- Regenerate `web/src/api/schema.d.ts`; update CLAUDE.md with a short Backup and restore
  paragraph.

## Testing

- Round trip: seed users, series, volumes, images, covers, glossary, credentials, settings,
  dictionaries, and finished and running jobs. Back up, change `TA_SECRET_KEY`, restore, then
  compare rows. Sessions and running jobs are gone, credentials decrypt with the new key, and
  sequences continue past max id.
- A wrong passphrase, a corrupt zip, an unknown or newer revision, and a format version
  mismatch each leave data unchanged.
- A failure injected mid-load rolls back to the old data.
- Restoring from an older revision: build a backup at an earlier revision (migrate a schema
  to that revision, insert rows, export) and check that it lands at head with the data
  migrations applied.
- Maintenance mode answers 503 for other routes during a restore.
- The setup-wizard restore works only while no user exists.
- A Playwright smoke test for the Admin panel's backup download, if practical.

## Left to the builder

The per-table file format (as long as it is faithful), the zip compression, the exact limits,
the copy of the confirmation word, the restore page's look, how the background thread
reports progress, and how the old-revision test fixture is built.
