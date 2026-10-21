# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Web port of the Translation Assistant PySide6 desktop app, **ported from
https://github.com/Punllarena/Translation-Assistant**. The desktop repo is the
reference and is never modified by this work. Its Qt-free modules
(`translation_assistant/core.py`, `epub.py`, `wp_publisher.py`, `imageopt.py`,
`scraper.py` functions, `ta/translators/*`) are ported near-verbatim into `api/core/`
and `api/mt/`; its `db.py` schema is the reference for the SQLAlchemy models, but its
code is not. The full mapping is in the spec, §1.

**Phases 1–2** exist: FastAPI app, full Postgres schema, invite-only session auth,
per-user profiles/settings/shortcuts/encrypted credentials, the `ta.db` importer, and
the library API (series/volumes/documents CRUD, reorder, renumber, merge/split, covers,
TXT import, TXT/Markdown export).

Phase 3a: editor API (lines, spell, images), Caddy, and the SPA under `web/` (login, picker,
series manager).

Phase 3b: editor screen: cards, CodeMirror input, saving, keymap, find, spell, images,
Edit Source/Split; Playwright smoke flows.

Phase 4: glossary API and Profiles page, translation memory panel, series find and replace (reviewed batch), phrase suggestions (MeCab via the optional `mecab` extra).

Phase 5: machine-translation aggregator. DeepL, LibreTranslate and Ollama stream through `GET /mt/stream`
(SSE; the single-shot backends yield once); MeCab and JParser return structured entries, not HTML. Results
are cached in `mt_cache`, whose keys include the endpoint: `deepl`, `libretranslate:<sha12(url)>`, and
`ollama:<model prefix>:<sha12(json [url, model, prompt])>`, so one user's server never answers for another's.
Per-user backend settings live under `/mt` and Settings → Machine translation. User-supplied LibreTranslate and
Ollama URLs are refused when they resolve to a non-global address unless `TA_MT_ALLOW_PRIVATE_URLS=true`
(guard in `api/mt/urls.py`).

Phase 6a: acquisition. Jobs (`api/jobs.py`; worker started in the lifespan; SSE at `/jobs/{id}/events`);
syosetu fetch (`api/core/scrape.py`: chapter numbers only, redirects checked, only `*.syosetu.com`);
batch TXT import (<=500 files, 12 MB (Caddy) / 12 MiB (API) per request) and EPUB import (`api/core/epub_read.py`,
limits in `epub_safety.py`: 64 MiB upload, 4 MiB per text entry, 32 MiB parsed per book, 256 MiB per-import
budget charged per image reference before reading, 900 chapters) are synchronous; per-volume EPUB build (`epub_build.py`). Form titles
with NUL are 422. Phase 6b: publishing and statistics. WordPress config is a `wordpress` credential plus `wp_*` user settings
(`api/wp_prefs.py`); `api/publish.py` builds chapters and records results; single publish is a request with a
server-enforced re-publish 409 (`confirm_republish`), batch publish and volume illustrations are jobs
(`api/publish_job.py`); one `wp_publish` and one `wp_illustrations` job may be active per user (409 otherwise).
Every WordPress call passes `check_user_url` unless `TA_WP_ALLOW_PRIVATE_URLS=true`, and the client never follows
redirects. Images over 40 megapixels (`MAX_PIXELS`, `api/core/images.py`) are sent as-is without decoding. A
cancelled or interrupted batch keeps per-chapter results (passwords included) in the job result. WordPress error
messages show only the plugin's JSON `error`/`message` field; a non-JSON or other body never reaches them. `GET /stats?tz=` buckets `lines.translated_at` in the viewer's
IANA zone. The SPA's publish dialogs open with native `showModal()` (non-modal `<dialog open>` inside table cells
got covered by rows).

Phase 7a: visual system. Colours, fonts and spacing are tokens in `web/src/styles/tokens.css` (light and
`:root[data-theme="dark"]`); every other stylesheet under `web/src/styles/` (pulled in by `index.css`) uses
tokens, never literal colours. Fonts are self-hosted through `@fontsource` (`web/src/fonts.ts`). The theme
preference is the user setting `ui_theme` (`system`/`light`/`dark`), mirrored in `localStorage` `ta.theme`;
an inline script in `web/index.html` paints it before the bundle loads, `web/src/theme/` owns the rules, and
the account's value wins once `/settings` arrives. Spec: `docs/superpowers/specs/2026-10-14-web-redesign-design.md`.

Onboarding: with no users, the SPA sends every page to `/setup` (`GET /setup/status`, `POST /setup/admin`,
which takes a Postgres advisory lock; `api/accounts.py`). Admin-only `/admin/settings` rows in `server_settings`
override `TA_OLLAMA_URL`, `TA_LIBRETRANSLATE_URL`, `TA_MT_ALLOW_PRIVATE_URLS`, `TA_WP_ALLOW_PRIVATE_URLS` and
`TA_SYOSETU_DELAY_SECONDS` (DB row > env > default; read through `api.server_settings.effective(db)`, never
`get_settings()` for those keys). Accounts have a `username` (3–32 of `A-Za-z0-9_.-`, unique ignoring
case, shown instead of the email); `/auth/login` takes `login`, an email when it contains `@`, otherwise a
username; the account rate bucket is keyed by that normalised string, never by the matched account (a
shared 429 would link a username to its email); a hidden `account_limiter` (`user:<id>`) caps the account
itself, and an exhausted account answers like a wrong password (401, dummy hash paid, no further charge).
Each bucket is charged before the password verify with `LoginLimiter.try_acquire` (atomic check-and-count)
and cleared on success, so concurrent requests cannot outrun the cap; `record_failure` is only a test seam. `TA_DATA_DIR` holds `dict/` (EDICT2 and Conjugations; `TA_EDICT_PATH` /
`TA_CONJUGATIONS_PATH` still win) and `uploads/` (pending `ta.db` imports, swept after 24 h). EDICT2 download is
the `dict_download` job (`api/dict_job.py`); `ta.db` import is the `tadb_import` job (`api/tadb_job.py`, dry run
then run). The importer lives in `api/core/tadb_*.py`; `tools/import_tadb.py` is its CLI. It reports
progress through `JobContext.report` (job row only, so a dry run still writes nothing; Cancel rolls the whole
import back) and inserts lines in Core batches of 1,000 (`api/core/tadb_lines.py`), retrying a rejected batch row
by row. `GET /import/tadb/pending` lets the import card resume; the header's running-jobs button polls
`GET /jobs?active=true`.

Library redesign: the Library (`/`) lists series only, as a bookshelf or a list (`ta.libraryView` in `localStorage`, helper
`web/src/library/viewPref.ts`). A series opens at `/series/:id?tab=volumes|tools|settings&volume=<id>|none`: Volumes is a
two-pane view (volume list, then the selected volume's chapters with a selection bar and per-row ⋯ menu; "No volume" holds
loose chapters), and its grouping and numbering helpers live in `web/src/library/volumeGroups.ts`. `documents.series_id` is
`NOT NULL` and deleting a series cascades to its volumes and chapters. `arrange()` (`api/library.py`) keeps each volume a
contiguous run numbered 1..N (loose chapters last) and runs after: creating a chapter, a chapter PATCH that changes its series
or volume, deleting a chapter, assigning chapters to a volume, a volume's order change or delete, reorder and renumber-by-title,
merge, split, and EPUB import. Syosetu-sourced series keep syosetu's chapter numbers. Renumbering alone leaves
`documents.updated_at` untouched (`renumber()` writes those rows in SQL). `POST /documents/export/zip`
exports ticked chapters; `GET /volumes` feeds the Move-to dialogs. Library dialogs (`web/src/ui/Dialog.tsx`: `ConfirmDialog`,
`PromptDialog`) replace native `prompt`/`confirm`, and none of them closes while its action is busy. Deferred work (WordPress
volume indexing, the EPUB illustrations chapter) is tracked in `docs/TODO.md`.

Syosetu heading volumes: the fetch job puts each chapter in the volume of its `p-eplist__chapter-title` heading, per the
series' `syosetu_volume_mode` (`all` / `marker` with `syosetu_volume_marker` / `off`); the rules are pure, in
`api/core/syosetu_volumes.py`, and read the heading sequence stored in `series.syosetu_headings` (written by the fetch job
and regroup, never by the chapter-list GET). Heading→volume links live in `volume_syosetu_groups` (hidden, so renamed
volumes keep receiving chapters; a merged volume holds several). `POST /series/{id}/syosetu/volume-headings`
(`api/syosetu_regroup.py`) previews or applies a setting change: it never deletes volumes and never moves chapters out of
volumes with no heading link. `POST /series/{id}/volumes/merge` merges volumes into one (the Volumes tab's Select mode).

- Spec: `docs/superpowers/specs/2026-10-10-web-app-port-design.md` (layout §2, phases §15)
- Plans: `docs/superpowers/plans/` (one per phase)

## Commands

```bash
docker compose up -d --build           # whole app at https://localhost; the setup wizard creates the first admin
docker compose --profile dev up        # hot reload: SPA :5173, API :8000 (dev image, source bind-mounted)
docker compose run --rm tools pytest   # also: ruff check ., sh -c "cd web && npm test|npm run e2e|npm run gen:api"

# Without Docker:
docker compose up -d postgres          # Postgres on 127.0.0.1:5432
pip install -e ".[dev]"                # in .venv
pip install -e ".[dev,mecab]"          # full dev install (adds fugashi + unidic-lite)
alembic upgrade head
uvicorn api.main:app --reload          # http://127.0.0.1:8000/docs
python -m tools.seed_admin --email you@example.com
python -m tools.import_tadb --db ta.db --user you@example.com --dry-run

ruff check .
pytest                                 # all
pytest tests/test_auth.py::test_name   # one test

cd web && npm run dev                  # SPA on :5173, /api proxied to :8000
npm run gen:api                        # regenerate web/src/api/schema.d.ts after API changes
npm test                               # vitest (pure modules only)
npm run e2e                            # Playwright; venv active (with the mecab extra), Postgres up, ta_e2e reset
```

`TA_SECRET_KEY` must be set and ≥32 chars; the app refuses the `.env.example`
placeholder. Tests default `TA_DATABASE_URL` to `ta_test` and **drop and recreate**
that database each run; conftest refuses any database name not ending in `_test`.

## Architecture rules

- **Commit boundary:** writes commit in `CommitOnResponseRoute` (`api/routing.py`),
  before the response is sent, via `run_in_threadpool(session.commit)`. The commit must
  stay off the event loop: a synchronous commit there deadlocked overlapping same-session
  requests (they all update `sessions.last_seen_at`). Build every router with `api_router()` —
  `tests/test_commit_boundary.py` fails otherwise. Handlers only `flush()`, never
  `commit()`. `db_session` teardown is rollback-and-close.
- **Tenancy:** fetch user-owned rows by id via `scoped()` in `api/deps.py`
  (404, never 403, for another user's rows). List endpoints filter by `user_id` inline.
- **Delete semantics:** key-addressed stores (`/settings/{key}`, `/shortcuts/{key}`)
  are idempotent 204; id-addressed resources 404 for ids that aren't the caller's.
  Later phases follow the same rule.
- **Migrations:** autogenerate (`alembic revision --autogenerate`); all models must be
  imported in `api/models/__init__.py`. Fix the model and regenerate rather than
  hand-patching a migration. `migrations/versions/*` is exempt from E501 only.
- **Config:** env only (`TA_` prefix, pydantic-settings in `api/config.py`), no config files.
- **E2E conventions:** each Playwright spec owns its seeded rows in `tools/e2e_seed.py`; seed
  names must not contain "E2E chapter"; glossary phrases a spec adds must occur only in its own
  chapters; the `ta_e2e` database is reset once per run, not per spec.
- **Size discipline:** no Python module over ~400 lines (spec §2).
- Tests use a per-test transaction rolled back at the end (`db` fixture), with
  `app_client` overriding `db_session`. `insecure_cookies` is needed because
  TestClient speaks plain http.
- `TA_ALLOW_PUBLIC_SIGNUP` is reserved and inert; `/auth/accept-invite` is the only
  account-creation path.
- MT backends take an injected `httpx.AsyncClient`; tests use `httpx.MockTransport` fixtures
  (`tests/fixtures/mt/`), never live endpoints. The `/mt/stream` cache write runs in its own session
  (`_put_sync` in `api/routers/mt.py`), one of two sanctioned commits outside the route boundary; the other is the
  job worker (`JobContext.progress`, `JobContext.report` (job row only, its own session, throttled)
  and `run_next` in `api/jobs.py`). WordPress calls take an injected `httpx.Client`
  the same way (`http_client` seams in `api/routers/wp.py` and `api/publish_job.py`).
- Tests set `TA_RUN_JOBS_WORKER=false` and drive jobs with `jobs.run_next()`, swapping `api.jobs.SessionLocal` for the test session.
