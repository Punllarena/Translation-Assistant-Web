# ta-web

Web port of the Translation Assistant desktop app. This repo currently holds **phases 1–2 and 3a**:
the skeleton (FastAPI app, full Postgres schema via Alembic, session auth with invites,
per-user profiles/settings/shortcuts/encrypted credentials, the `ta.db` importer), the
library API (series, volumes, documents, picker listing with progress, reorder and renumber,
merge and split, covers, TXT import, TXT/Markdown export), and the editor API (line load and
dirty-line save, parse navigation, spellcheck, inline images). Phase 3a also brings the SPA under
`web/` (login, picker, series manager); the editor screen is phase 3b. Phases 3b–6 are described
in the spec.

- Spec: [`docs/superpowers/specs/2026-10-10-web-app-port-design.md`](docs/superpowers/specs/2026-10-10-web-app-port-design.md)
- Phase 1 plan: [`docs/superpowers/plans/2026-10-10-phase1-skeleton.md`](docs/superpowers/plans/2026-10-10-phase1-skeleton.md)
- Phase 2 plan: [`docs/superpowers/plans/2026-10-10-phase2-library.md`](docs/superpowers/plans/2026-10-10-phase2-library.md)
- Phase 3a plan: [`docs/superpowers/plans/2026-10-11-phase3a-editor-api-and-spa.md`](docs/superpowers/plans/2026-10-11-phase3a-editor-api-and-spa.md)

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

Caddy serves the SPA and proxies `/api/*` to the API (prefix stripped) at
`https://$TA_SITE_ADDRESS` (default `localhost`, with Caddy's internal CA). Set
`TA_SITE_ADDRESS` to a public hostname and Caddy obtains a certificate for it. Caddy caps
request bodies at 12 MB. The API container is not published; uvicorn trusts the
forwarded client address because Caddy is its only client.

## Web app (development)

```bash
uvicorn api.main:app --reload                 # API on 127.0.0.1:8000 (TA_COOKIE_SECURE=false)
cd web && npm install && npm run dev          # SPA on http://localhost:5173, /api proxied
npm run gen:api                               # after any API schema change; commit the result
npm test                                      # vitest
```

## Design decisions

- **Caddy serves the SPA and fronts the API under `/api`.** The API's paths and the SPA's
  routes would otherwise collide on a refresh; the proxy strips the prefix, so the API itself
  is unchanged. The interactive docs are at `http://127.0.0.1:8000/docs` in development only.
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
  covers at most 10 MiB, PNG/JPEG/GIF/WebP by magic bytes. These caps apply only after the
  request body has been received (multipart file parts are spooled before auth and before
  `read_capped`), so a reverse-proxy body cap (e.g. Caddy `request_body { max_size 12MB }`) is
  required before the API is exposed beyond 127.0.0.1 (Caddy provides it).
- **Imported and created documents are capped at 50,000 lines** (`MAX_LINES` in
  `api/library.py`); TXT import and `POST /documents` answer 422 beyond that.
- **`translated_at` is the day a line was first translated.** A save stamps it when a line goes
  from empty to non-empty, clears it when the line is emptied, and keeps it on an edit (the
  desktop restamped every edit).
- **Spellcheck spans are UTF-16 offsets**, the units of a browser string; enchant runs
  server-side with each profile's custom words. Without enchant or an English dictionary the
  endpoint answers `available: false` and flags nothing. Requests are capped at 200 texts,
  100,000 characters each and 200,000 in total (422 beyond), and enchant calls are serialised
  behind one global lock.
- **Images are served by sniffed type only** (PNG/JPEG/GIF/WebP); anything else is
  `application/octet-stream` with `nosniff`.
- **The SPA drops every cached query except the session's on sign-in and sign-out**, so one
  user's data never shows to the next.
