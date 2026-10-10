# ta-web

Web port of the Translation Assistant desktop app. This repo currently holds **phases 1-2**:
the skeleton (FastAPI app, full Postgres schema via Alembic, session auth with invites,
per-user profiles/settings/shortcuts/encrypted credentials, the `ta.db` importer) and the
library API (series, volumes, documents, picker listing with progress, reorder and renumber,
merge and split, covers, TXT import, TXT/Markdown export). There is no web UI yet; the SPA
arrives in phase 3. Phases 3-6 are described in the spec.

- Spec: [`docs/superpowers/specs/2026-10-10-web-app-port-design.md`](docs/superpowers/specs/2026-10-10-web-app-port-design.md)
- Phase 1 plan: [`docs/superpowers/plans/2026-10-10-phase1-skeleton.md`](docs/superpowers/plans/2026-10-10-phase1-skeleton.md)
- Phase 2 plan: [`docs/superpowers/plans/2026-10-10-phase2-library.md`](docs/superpowers/plans/2026-10-10-phase2-library.md)

## Prerequisites

Python 3.12+, Docker (with Compose), and a shell.

## Quick start

```bash
# 1. Postgres (bound to 127.0.0.1:5432)
docker compose up -d postgres

# 2. Virtualenv + dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Config (the app reads .env itself). The app deliberately refuses the .env.example placeholder key,
#    so copying the file unchanged will not boot -- generate a real one:
cp .env.example .env
sed -i "s|^TA_SECRET_KEY=.*|TA_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')|" .env

# 4. Schema
alembic upgrade head

# 5. First admin (prompts for a password)
python -m tools.seed_admin --email you@example.com

# 6. Run
uvicorn api.main:app --reload     # http://127.0.0.1:8000/docs
```

`TA_SECRET_KEY` encrypts stored credentials; losing or changing it makes them unreadable.

## Tests and lint

`tests/conftest.py` defaults `TA_DATABASE_URL` to a `ta_test` database on the local Postgres. The
suite **drops and recreates** that database on every run, and refuses to run against any name that
does not end in `_test`. Export `TA_DATABASE_URL` only to point the suite at a different Postgres.

```bash
ruff check .
pytest
```

CI (`.github/workflows/ci.yml`) runs the same two commands against a `ta_test` database.

## Importing a desktop `ta.db`

Work on a copy of the file. Do a dry run first (reports counts, writes nothing), then the real run:

```bash
python -m tools.import_tadb --db /path/to/ta.db --user you@example.com --dry-run
python -m tools.import_tadb --db /path/to/ta.db --user you@example.com
```

The destination user must already exist. The importer refuses to run when the same file was
already imported for that user, **and** when the account already holds any documents — a `ta.db`
you kept working in has a different fingerprint, so the document count is what stops a second run
from duplicating the whole library. `--force` overrides both; documents whose series and title are
already present are then skipped (reported as "already present"), so only new chapters are added.
`--dry-run` is never refused for a non-empty account — it writes nothing, so it reports the
existing document count and exactly which chapters would be added or skipped.

Before writing anything the importer checks the source's columns against the desktop schema it was
written for (`SOURCE_COLUMNS` in `tools/import_tadb.py`, transcribed from the desktop
`translation_assistant/db.py`): a column no released desktop version has is an error, while the
columns later desktop builds added by `ALTER TABLE` (`OPTIONAL_COLUMNS`) are tolerated as missing
in an older file. Each row is written in its own savepoint; rows the schema rejects are skipped and
listed, and the command **exits non-zero if any rows were skipped**.

Timestamps (`lines.translated_at`, `documents.wp_date`) are read as UTC, which is what the desktop
writes. Not carried over: `documents.created_at` / `updated_at` — imported rows get the import
time, so "created" dates restart at migration. That is a known, accepted omission for phase 1.

## Backup

There is no in-app backup. Dump the database with `pg_dump` (custom format, restorable
with `pg_restore`):

```bash
docker compose exec -T postgres pg_dump -U ta -Fc ta > ta-$(date +%F).dump
docker compose exec -T postgres pg_restore -U ta -d ta --clean --if-exists < ta-2026-10-10.dump
```

Back up `TA_SECRET_KEY` alongside it: without the key, the stored credentials in a restored
dump cannot be decrypted.

## Container

```bash
docker compose up --build        # needs TA_SECRET_KEY in .env or the environment
```

The `api` service runs `alembic upgrade head` and then uvicorn on port 8000. TLS and a reverse
proxy arrive with the SPA in phase 3; until then the API is served directly, bound to loopback only (`127.0.0.1:8000`, like Postgres)
because cookies are not `Secure` without TLS; opening it up belongs with the TLS work in phase 3.
Once a proxy fronts it, keep `--proxy-headers` on uvicorn (already in the container command) and make sure the
proxy is the only thing that can reach it, otherwise clients can spoof their address.

## Design decisions

- **Sessions are opaque random tokens**, stored hashed in a `sessions` row, instead of the spec's
  "signed session id". Same guarantee, no signing dependency, and revocation is deleting a row.
- **Registration is invite-only**, by construction: `/auth/accept-invite` is the only
  endpoint that creates an account. `TA_ALLOW_PUBLIC_SIGNUP` exists because the spec asks for
  it, but **nothing reads it yet** — it is reserved for the signup path a later phase adds, and
  setting it to `true` changes nothing today.
- **`mt_cache` is global, with no `user_id`.** Its key is the content hash, so identical source
  text dedupes across the whole library.
- **Cross-user access returns 404, not 403**, so the existence of another user's rows is not disclosed.
- **The login limiter keys on both client address and submitted email.** The address comes from
  `request.client.host`, which behind a proxy is the proxy's address for everyone unless uvicorn
  runs with `--proxy-headers` (and trusts the proxy via `--forwarded-allow-ips` if it is not local).
- **Lint is `select = ["E", "F", "I", "B", "UP"]` with `B008` ignored** (`Depends()` in default
  arguments is the FastAPI idiom). Autogenerated Alembic revisions are exempt from `E501` only:
  rewrapping them by hand would be undone by the next `--autogenerate`.
- **Delete semantics follow the addressing.** Key-addressed stores are idempotent:
  `DELETE /settings/{key}` and `DELETE /shortcuts/{action_key}` answer 204 whether or not the key
  existed. Id-addressed resources are not: `DELETE /profiles/{id}` and `DELETE /credentials/{id}`
  answer 404 for an id that is not the caller's. Phases 2-6 should follow the same rule.
- **Writes commit in the request path**, in `CommitOnResponseRoute` (`api/routing.py`), not in the
  session dependency's teardown — a teardown commit runs after the response has been sent, so its
  failure could not be reported. Build every router with `api_router()`; handlers only `flush()`.
- **An id in a request body that is missing or someone else's is a 422**, with one message for
  both (`series_id: no such item`, `document_ids: no such item` for merge). The URL names the
  resource, so a 404 there would misreport which thing was not found; the single message keeps
  existence undisclosed. Split takes its document from the URL, so its miss is a 404.
- **Deleting a series or a volume keeps its chapters.** They become unsorted / unassigned
  (`ON DELETE SET NULL`); deleting chapters is its own action.
- **Merge and split move line rows rather than rewriting them**, so each line keeps its
  `translated_at` (the desktop lost these on merge/split). In split, an image anchored after
  the last line goes to the last segment.
- **The last opened document** is the `last_document_id` user setting, written by the client via
  `PUT /settings`; a deleted document simply answers 404.
- **Uploads are capped and sniffed:** TXT at most 5 MiB, UTF-8 (BOM allowed), no NUL bytes;
  covers at most 10 MiB, PNG/JPEG/GIF/WebP by magic bytes.
