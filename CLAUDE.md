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
Edit Source/Split; Playwright smoke flows. Phases 4–6 are next.

- Spec: `docs/superpowers/specs/2026-10-10-web-app-port-design.md` (layout §2, phases §15)
- Plans: `docs/superpowers/plans/` (one per phase)

## Commands

```bash
docker compose up -d postgres          # Postgres on 127.0.0.1:5432
pip install -e ".[dev]"                # in .venv
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
npm run e2e                            # Playwright; venv active, Postgres up, ta_e2e reset
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
- **Size discipline:** no Python module over ~400 lines (spec §2).
- Tests use a per-test transaction rolled back at the end (`db` fixture), with
  `app_client` overriding `db_session`. `insecure_cookies` is needed because
  TestClient speaks plain http.
- `TA_ALLOW_PUBLIC_SIGNUP` is reserved and inert; `/auth/accept-invite` is the only
  account-creation path.
