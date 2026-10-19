# ta-web

Web port of the [Translation Assistant](https://github.com/Punllarena/Translation-Assistant) desktop app:
a self-hosted, multi-user FastAPI + Postgres server with a React SPA under `web/`. All six phases of the
port are in place:

1. **Skeleton:** FastAPI app, full Postgres schema via Alembic, session auth with invites, per-user
   profiles/settings/shortcuts/encrypted credentials, the `ta.db` importer.
2. **Library:** series, volumes, documents, picker with progress, reorder and renumber, merge and split,
   covers, TXT import, TXT/Markdown export.
3. **Editor:** line cards with dirty-line saving, keymap and parse navigation, find, spellcheck, inline
   images, Edit Source/Split.
4. **Memory:** glossary and profiles, translation memory, series find and replace, phrase suggestions.
5. **Machine translation:** DeepL, LibreTranslate, Ollama (streamed), MeCab and JParser, with a shared cache.
6. **Acquisition and publishing:** background jobs, syosetu fetch, batch TXT and EPUB import, EPUB build
   (6a); WordPress publish, batch publish/schedule, volume illustrations, and statistics (6b).

- Spec: [`docs/superpowers/specs/2026-10-10-web-app-port-design.md`](docs/superpowers/specs/2026-10-10-web-app-port-design.md)
- Plans, one per phase: [`docs/superpowers/plans/`](docs/superpowers/plans/)

## Quick start

Only Docker (with Compose) is needed.

```bash
docker compose up -d --build
docker compose logs api        # prints: First-run setup: ... https://localhost/setup?token=...
```

Open the setup link, create the first (admin) account, and sign in at `https://localhost`. Caddy
uses its internal CA for `localhost`, so the browser warns once. Set `TA_SITE_ADDRESS` (in `.env`
or the environment) to a public hostname and Caddy obtains a real certificate for it.

The setup token is derived from `TA_SECRET_KEY` and works only while the server has no accounts,
so whoever reaches a fresh public install first cannot claim it. `python -m tools.seed_admin`
(`docker compose run --rm api python -m tools.seed_admin --email you@example.com`) still works too.

**`TA_SECRET_KEY`** is optional. Without it the API generates a key on first boot and keeps it in
the `api_data` volume (`/data/secret_key`); set it explicitly to use your own.
`docker compose down -v` deletes that volume along with the database.

## Development and tests in containers

```bash
docker compose --profile dev up                                  # SPA http://localhost:5173, API http://127.0.0.1:8000/docs
docker compose run --rm tools ruff check .
docker compose run --rm tools pytest
docker compose run --rm tools sh -c "cd web && npm test"
docker compose run --rm tools sh -c "cd web && npm run build"
docker compose run --rm tools sh -c "cd web && npm run e2e"
docker compose run --rm tools sh -c "cd web && npm run gen:api"
```

The `dev` image (Python with the dev and mecab extras, Node 24, Playwright's Chromium) bind-mounts
the checkout, so edits reload live (file watching polls, because bind mounts from Windows and macOS
deliver no events). `web/node_modules` lives in a Linux-only named volume and is reinstalled when
`package-lock.json` changes. `api-dev` uses the same database and key as `api`; `tools` uses
`ta_test` and `ta_e2e` (both reset by their suites) with a fixed test key. Stop `api`
(`docker compose stop api caddy`) before starting the dev profile: each API process runs the job
worker, and a starting one fails the jobs the other is running.

## Without Docker

Python 3.12+, Postgres (`docker compose up -d postgres` binds it to 127.0.0.1:5432), and a shell.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# The app reads .env itself. It refuses the .env.example placeholder key, so generate a real one:
cp .env.example .env
sed -i "s|^TA_SECRET_KEY=.*|TA_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')|" .env

alembic upgrade head
python -m tools.seed_admin --email you@example.com   # or open /setup?token=... from the log
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

CI (`.github/workflows/ci.yml`) runs lint and pytest against a `ta_test` database, the web unit tests and build, a Caddyfile check, and the Playwright suite against `ta_e2e`.

## Importing a desktop `ta.db`

Work on a copy of the file. Do a dry run first (reports counts, writes nothing), then the real run:

```bash
docker compose run --rm -v ./ta.db:/import/ta.db:ro api python -m tools.import_tadb --db /import/ta.db --user you@example.com --dry-run
# or, without Docker:
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

Back up `TA_SECRET_KEY` alongside it (with compose and no explicit key:
`docker compose exec api cat /data/secret_key`). Without the key, the stored credentials in a
restored dump cannot be decrypted.

## Container

```bash
docker compose up --build
```

Caddy serves the SPA and proxies `/api/*` to the API (prefix stripped) at
`https://$TA_SITE_ADDRESS` (default `localhost`, with Caddy's internal CA). Set
`TA_SITE_ADDRESS` to a public hostname and Caddy obtains a certificate for it. Caddy caps
request bodies at 12 MB (64 MiB on `/api/epub/*`). The API container is not published; uvicorn trusts the
forwarded client address because Caddy is its only client. uvicorn runs with
`--timeout-graceful-shutdown 5` because open job SSE streams would otherwise block a shutdown or reload.

## Web app (development)

```bash
uvicorn api.main:app --reload                 # API on 127.0.0.1:8000 (TA_COOKIE_SECURE=false)
cd web && npm install && npm run dev          # SPA on http://localhost:5173, /api proxied
npm run gen:api                               # after any API schema change; commit the result
npm test                                      # vitest
npm run e2e   # Playwright; needs the venv active and Postgres up (database ta_e2e is reset)
```

The first e2e run needs Chromium: `cd web && npx playwright install chromium`. The e2e run uses
ports 8001 (API) and 5174 (SPA).

## Optional: MeCab

`pip install -e '.[mecab]'` installs fugashi and unidic-lite. Without it, phrase
suggestions report that MeCab is unavailable. The Docker image already installs `.[mecab]`.

## Acquisition

- **Syosetu fetch.** Fetch a single chapter from a URL, or a whole series as a background job
  with live progress. Requests to syosetu are spaced `TA_SYOSETU_DELAY_SECONDS` apart
  (default 5), process-wide. Only `*.syosetu.com` hosts are fetched. At most two interactive
  requests (fetch from URL, chapter list, re-fetch) wait on syosetu at once (503 beyond), and a
  series has at most one queued or running fetch job (409 beyond).
- **Re-fetch** a chapter to refresh its source; translations stay attached by line position.
- **Batch TXT import** with an optional glossary CSV: at most 500 files, 5 MiB per TXT and
  12 MB (Caddy) / 12 MiB (API) per request in total. A form title containing a NUL
  character, or longer than 300 characters, is a 422.
- **EPUB import.** The upload is at most 64 MiB (Caddy allows that size on `/api/epub/*` only; the
  API enforces it too). An archive may expand to at most 256 MiB, any single XML/XHTML entry is
  at most 4 MiB and at most 32 MiB of XML/XHTML is parsed per book (422 beyond: giant omnibus
  EPUBs are refused), the chapter files and images of one import share a 256 MiB budget, charged
  per image reference before it is read (413 beyond), and one import takes at most 900 chapters
  (422 beyond).
- **EPUB download** per volume. Every chapter in the volume must be fully translated.

### Background jobs

The in-process job worker runs inside the API process. `TA_RUN_JOBS_WORKER=false` disables it.
A restart marks the running job failed; starting the same fetch again resumes it. Run a single
API process: the startup sweep fails every running job. Progress streams over SSE at
`/jobs/{id}/events`.

## Machine translation

Each user sets up backends at Settings → Machine translation.

- **DeepL** needs your own API key. Free keys end in `:fx` and use the free API host.
- **LibreTranslate** needs a URL. The server default is `TA_LIBRETRANSLATE_URL`; a per-user URL
  overrides it.
- **Ollama** uses the server default `TA_OLLAMA_URL`, a per-user URL override, and a model name.
- **MeCab** needs the `mecab` extra (`pip install -e '.[mecab]'`).
- **JParser** needs `edict2` from <https://www.edrdg.org/jmdict/edict.html>, at `TA_EDICT_PATH`.
  The Docker images download it at build time (`/opt/ta/edict2`). EDICT2 is the property of the
  [Electronic Dictionary Research and Development Group](https://www.edrdg.org/) and is used under
  its licence (CC BY-SA 4.0).
- `TA_CONJUGATIONS_PATH` (optional) points at the desktop's `Conjugations.txt` and enables
  deconjugation in JParser. It is not bundled; under compose, mount it into the `api` service
  (for example `./Conjugations.txt:/opt/ta/Conjugations.txt:ro`) and set the variable.

User-supplied LibreTranslate and Ollama URLs are checked before the server calls them: a host
that resolves to a private, loopback, link-local, or CGNAT (100.64.0.0/10) address is refused.
Set `TA_MT_ALLOW_PRIVATE_URLS=true` to allow those, for example for a LibreTranslate instance on
your LAN. The server defaults (`TA_OLLAMA_URL`, `TA_LIBRETRANSLATE_URL`) are operator-trusted and
are not checked. The guard lives in `api/mt/urls.py`. DNS is checked when the request is
prepared and the result is not pinned, so a host whose DNS changes between the check and the call
(DNS rebinding) can bypass the guard; operators exposing the server to untrusted users should keep
that in mind.

The WordPress endpoint has its own flag, `TA_WP_ALLOW_PRIVATE_URLS` (see WordPress publishing).

## WordPress publishing

Install the Translation Assistant Publisher plugin on the WordPress site, then enter its endpoint
(site URL or `…/wp-json/ta-publisher/v1/publish`) and API key under Settings → WordPress, and each
series' slug and short title on its series page. Publish one chapter with the Publish… button on its row in the library, or select
chapters and choose Publish to publish or schedule them as a job. Volumes have a Publish
illustrations button.

The endpoint may not resolve to a private or local address unless `TA_WP_ALLOW_PRIVATE_URLS=true`
(for a WordPress on the same network). The server never follows a redirect from WordPress; save the
address it redirects to instead. Images are downscaled (Pillow) to keep each request under the
~1 MB body limit some hosts enforce; images over 40 megapixels are sent unchanged. The DNS-rebinding caveat described under Machine translation
applies to the WordPress endpoint too.

## Statistics

The Statistics page (`GET /stats?tz=<IANA zone>`) shows a 52-week activity heatmap, today / 7-day /
30-day / all-time totals with the change against the previous period, current and longest streaks,
a per-day table and a per-series breakdown. Everything is derived from `lines.translated_at`; days
are counted in the viewer's browser time zone.

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
  failure could not be reported. The commit runs in the threadpool: a synchronous commit on the
  event loop deadlocked overlapping requests on the same session (they all update
  `sessions.last_seen_at`). Build every router with `api_router()`; handlers only `flush()`.
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
- **The editor saves as you type.** Edits are kept per line and sent 800 ms after typing
  stops (or on leaving a line); the status bar says Saved only for text the server accepted.
  A flush waits for any save already in flight, then sends what is still dirty. On page hide
  the rest goes out with `fetch` keepalive and is stashed in sessionStorage, so a closed tab
  or expired session cannot lose it — it is re-sent when the chapter reopens. A NUL character
  in a translation or source is refused with a 422.
- **Every editor key is rebindable** (Shortcuts screen). A key another action uses, or one the
  browser reserves (Ctrl+N/T/W), is refused. Bare printable keys cannot be bound, since they
  would make the text untypable, and IME composition keys are ignored.
- **Edit Source keeps one line per line** and does not re-split sentences; a `$` line continues
  the previous paragraph. Only newlines split lines (CRLF is normalised to LF). A save that
  changes the number of lines asks for confirmation, because translations stay attached by
  line position.
- **Japanese highlighting is by character class** (kanji/kana/punctuation); part-of-speech
  colouring arrives with MeCab in phase 5.
