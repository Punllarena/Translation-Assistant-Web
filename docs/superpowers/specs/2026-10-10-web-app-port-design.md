# Translation Assistant — Web App Port

**Date:** 2026-10-10
**Status:** design approved, implementation plans pending
**Target:** a new repository (`ta-web`), separate from this one

---

## 1. Purpose

Replace the PySide6 desktop application with a self-hosted, multi-user web
application that carries over every feature of the desktop app. The desktop
repository stays as-is; nothing in it is modified by this work.

Decisions already taken (these are settled, not open questions):

| Decision | Choice |
|---|---|
| Deployment | Self-hosted, multi-user, one server the owner runs |
| Backend | Python — FastAPI + SQLAlchemy 2.0 + Alembic |
| Database | PostgreSQL |
| Frontend | TypeScript SPA (Vite + React) |
| Desktop-bound features | Run server-side (MeCab, JParser, Ollama, spellcheck) |
| Clipboard auto-copy | Dropped |
| MT / WordPress credentials | Per-user, encrypted at rest |
| Existing `ta.db` | Imported by a one-shot CLI tool |

### Why port rather than rewrite

Three approaches were considered: a full rewrite, a port-and-wrap, and a
strangler pattern that kept the desktop app running against a local server.
Port-and-wrap wins. Roughly 3,000 lines of this repository are already
Qt-free, pure-function text logic with tests behind them:

| Module | Lines | Fate |
|---|---|---|
| `translation_assistant/core.py` | 732 | Port verbatim |
| `translation_assistant/epub.py` | 586 | Port verbatim |
| `translation_assistant/wp_publisher.py` | 432 | Port verbatim |
| `translation_assistant/imageopt.py` | — | Port verbatim |
| `translation_assistant/scraper.py` | — | Keep the `fetch_*` functions, drop the three `QThread` workers |
| `ta/translators/*` | ~1,200 | Keep the parsing and HTTP logic, replace `QObject` signals with async generators |
| `translation_assistant/spellcheck.py` | — | Keep the enchant dictionary wiring, drop `QSyntaxHighlighter` |
| `translation_assistant/jp_highlighter.py` | — | Highlight rules become CodeMirror decorations, client-side |
| `translation_assistant/db.py` | 1,070 | Rewritten as SQLAlchemy models + repositories; the schema is the reference, the code is not |
| `translation_assistant/ui/*` | ~6,000 | Rewritten as the SPA |
| `translation_assistant/settings.py` | — | Replaced by DB-backed per-user settings |
| `translation_assistant/migration.py` | — | Not carried over (CSV/LEX legacy importer; superseded by the `ta.db` importer) |

A full rewrite discards the tested text logic for no benefit. The strangler
approach was rejected because it requires maintaining two front ends.

---

## 2. Repository layout

```
ta-web/
├── api/
│   ├── main.py                 FastAPI app factory, CORS, static SPA mount
│   ├── config.py               pydantic-settings; env only, no files
│   ├── deps.py                 current_user, current_profile, scoped_session
│   ├── security.py             argon2 password hashing, session cookies, Fernet helpers
│   ├── jobs.py                 job table driver + in-process asyncio worker
│   ├── core/                   ported, Qt-free, no DB imports
│   │   ├── text.py             ← core.py
│   │   ├── epub.py             ← epub.py
│   │   ├── wp.py               ← wp_publisher.py
│   │   ├── scrape.py           ← scraper.py (functions only)
│   │   ├── images.py           ← imageopt.py
│   │   └── spell.py            ← spellcheck.py (dictionary only)
│   ├── mt/
│   │   ├── base.py             AsyncTranslator protocol
│   │   ├── google.py bing.py deepl.py libretranslate.py ollama.py
│   │   └── mecab.py jparser.py
│   ├── models/                 SQLAlchemy ORM, one module per aggregate
│   ├── schemas/                pydantic request/response models
│   └── routers/
│       ├── auth.py documents.py series.py lines.py tm.py glossary.py
│       ├── mt.py scrape.py epub.py wp.py stats.py settings.py jobs.py
│       └── spell.py
├── web/                        Vite + React + TypeScript
│   ├── src/
│   │   ├── api/                generated client from the OpenAPI schema
│   │   ├── editor/             line-card list, keymap, find bar, spell decorations
│   │   ├── library/            document picker, series manager, volume manager
│   │   ├── panels/             MT aggregator, translation memory, images
│   │   ├── dialogs/            new document, batch import, fetch, publish, stats
│   │   └── state/              TanStack Query + a dirty-lines store
├── migrations/                 Alembic
├── tools/
│   ├── import_tadb.py          one-shot ta.db → Postgres
│   └── seed_admin.py
├── tests/                      pytest (api), vitest + Playwright (web)
├── docker-compose.yml          api, postgres, caddy
└── README.md
```

Module size discipline: no Python module over ~400 lines, no React component
file over ~300. `main_widget.py` reached 1,870 lines in the desktop app and
became hard to change; the routers/repositories split exists to prevent a
repeat.

---

## 3. Data model

Alembic starts from an empty database. The desktop `ALTER TABLE` migration
chain in `db.py::_apply_schema` is not carried over — its end state is the
starting schema here.

```
users
  id, email, password_hash, is_admin, created_at

profiles                        a user may keep several
  id, user_id→users, name, parse_chars, is_default, created_at
  unique(user_id, name)

user_settings                   replaces QSettings
  user_id→users, key, value_json
  primary key(user_id, key)

shortcuts
  id, user_id→users, action_key, binding
  unique(user_id, action_key)

api_credentials                 Fernet-encrypted values
  id, user_id→users, kind ∈ {deepl, libretranslate, wordpress, ollama},
  name, secret_enc, endpoint_url, created_at

glossary
  id, profile_id→profiles, phrase, translation, sort_order
  unique(profile_id, phrase)

custom_words
  id, profile_id→profiles, word
  unique(profile_id, lower(word))

series
  id, user_id→users, title, profile_id→profiles NULL,
  syosetu_url, wp_series_slug, wp_series_title_short,
  wp_password_enabled NULL, wp_unlock_after NULL,
  created_at
  unique(user_id, title)

volumes
  id, series_id→series, title, volume_order,
  epub_title, epub_author, epub_language, epub_description
  unique(series_id, title)

documents
  id, user_id→users, series_id→series NULL, volume_id→volumes NULL,
  title, source_language, series_order, source_url,
  last_position, wp_post_id, wp_status, wp_published_at, wp_scheduled_for,
  created_at, updated_at

lines
  id, document_id→documents, line_number, prefix ∈ {%, $},
  raw_text, translated_text, translated_at NULL
  unique(document_id, line_number)

document_images
  id, document_id→documents, anchor_position, is_cover,
  src_path, data bytea, exclude_export

mt_cache
  id, backend, source_lang, target_lang, source_sha256, result_text, created_at
  unique(backend, source_lang, target_lang, source_sha256)

work_sessions                   replaces the JSONL history log
  id, user_id→users, started_at, ended_at, lines_translated, words_translated
```

Notes on the shape changes from the desktop schema:

- **Series become rows.** The desktop app keys series by title string, with a
  `series_profiles` side table and `documents.series_title` text. Here `series`
  is a real table with a foreign key. This is the one deliberate schema
  improvement; everything else is a faithful carry-over.
- **Volumes become rows** for the same reason — today volume metadata is
  derived from `documents.volume_title` plus columns on `series_profiles`.
- **Image blobs stay in the database.** Object storage is not introduced; a
  chapter has at most a handful of illustrations. `# upgrade path: move to S3
  if a library outgrows the database dump size`
- **Stats stay derived.** `lines.translated_at` remains the source of truth for
  the heatmap, streaks, and period comparisons, exactly as
  `get_daily_stats` / `compute_streaks` / `compute_period_comparisons` do now.
  No stats table.

### Multi-tenancy

Every table is reachable from a `user_id`, directly or through one hop.
Scoping is enforced in one place: a `scoped_session` dependency that yields a
session plus the current user id, and repository functions that take that id as
their first argument. No handler issues an unscoped query. A test asserts that
each router rejects a second user's object id with 404 (not 403 — existence is
not disclosed).

---

## 4. Authentication and accounts

- Session cookies — `HttpOnly`, `Secure`, `SameSite=Lax` — holding a signed
  session id. No JWT; a self-hosted single-server app has no need for stateless
  tokens.
- argon2id password hashing.
- Registration is closed by default. The first account is created by
  `tools/seed_admin.py`; further accounts come from admin-issued invite tokens.
  A public signup flag exists in config and defaults to off.
- Rate limiting on the login endpoint (per-IP, in-memory token bucket).
  `# ponytail: in-memory limiter, move to the DB when there is more than one replica`
- Credential secrets (`api_credentials.secret_enc`) are encrypted with Fernet
  using a key supplied as `TA_SECRET_KEY` in the environment. The server
  refuses to start without it. Secrets are never returned by any endpoint —
  responses carry presence booleans and last-four hints only.
- WordPress and MT calls are made server-side with the owning user's
  credentials, never proxied with a shared key.

---

## 5. Editor

The editor is the feature that carries the application; everything else feeds
it. One document is loaded in full — chapters are a few hundred lines, so
pagination is unnecessary — and rendered as a virtualized list of line cards,
one card per source paragraph, source text above and a translation input below.

**Draft state and saving.** Edits land in a client-side dirty-lines store
keyed by line number. A debounced flush (800 ms idle, or immediately on card
blur, document close, or page hide) sends the dirty set to
`PATCH /documents/{id}/lines` as `{line_number, translated_text}[]`. The server
writes them in one statement and stamps `translated_at` on lines that changed
from empty to non-empty, matching `save_lines` today. This replaces the
desktop autosave timer; there is no explicit save action, but a save-state
indicator (saved / saving / unsaved) is always visible, and the browser's
unload guard fires while the dirty set is non-empty.

**Navigation and keys.** All key handling lives in one keymap module — the
direct analogue of `_handle_key` in `main_widget.py`. Bindings are loaded from
`shortcuts` per user and are rebindable from a settings screen. Carried over:
next/previous line, next/previous paragraph, sentence-level parse navigation
using the profile's `parse_chars`, go-to-line, font size up/down, the F1–F8
Japanese punctuation inserts, and the find bar (`Ctrl+F`, wrap-around,
case-insensitive, `n/total` counter) in both the editor and the source-editing
views.

**Glossary substitution.** Applied to the source text on display, server-side,
by the ported `replace_and_parse`. The response carries both the raw and the
substituted text so the client can toggle.

**Spellcheck.** The translation input is a CodeMirror 6 editor.
`POST /spell/check` takes a text and a profile id and returns misspelled spans
plus suggestions, computed by server-side enchant plus the profile's
`custom_words`; the client renders them as decorations and offers a suggestion
menu and an "add to dictionary" action. Requests are debounced and batched per
visible card. Browser-native spellcheck is not used — per-profile word lists
are a feature, and the desktop behaviour is preserved.

**Japanese highlighting.** The ported `jp_highlighter` rules become a
CodeMirror decoration set over the source text (kanji / kana / punctuation
classes), computed client-side.

**Progress.** Percentage complete, word count, and the line counter are
computed client-side from the loaded document, using the ported
`calculate_progress` rules — blank paragraph markers excluded.

**Images.** Illustrations anchored into a chapter show inline in the card list
at their `anchor_position`, with a collapse toggle, a cover marker, and an
exclude-from-export checkbox.

---

## 6. Library: documents, series, volumes

A document picker screen replaces the desktop `dlg_open` dialog: chapters
grouped by series, per-document translation progress, last-edited time, a live
text filter, multi-select, and in-place metadata editing.

Carried-over operations, each an endpoint plus a UI affordance:

- Create, rename, delete a document; restore the last opened document on login.
- Series management: create, rename, delete, set the series URL, assign a
  profile, drag-and-drop chapter reorder, renumber by title using the ported
  `natural_key` sort.
- **Merge** selected chapters into one, and **split** an over-long chapter at
  manually placed markers — translations, line prefixes, and image anchors
  follow into the correct segment, and `series_order` re-compacts. The desktop
  `merge_documents` / `split_document` logic is ported as the reference
  behaviour; these two are the highest-risk ports and get their own test
  module.
- Volume management: assign chapters to a volume, rename a volume, set EPUB
  metadata, designate a cover.
- Import: legacy TXT, batch import from uploaded files, EPUB import (chapter
  selection from the spine, inline illustration extraction).
- Export: TXT, Markdown (plain), Markdown with ruby annotations, per-series
  Markdown, EPUB per volume.
- Backup: taken with `pg_dump` and documented in the README. There is no
  in-app backup dialog.

File-based operations become uploads and downloads. Uploads are size-capped
and content-sniffed; EPUB and ZIP extraction rejects absolute paths and `..`
entries, and caps the total uncompressed size.

---

## 7. Translation memory, phrases, find and replace

- **Translation memory panel.** `GET /tm/matches?document_id&line_number`
  returns previously translated lines whose source resembles the current one,
  using the ported `find_tm_matches` query, scoped to the user and ranked by
  similarity. Collapsible panel beside the editor.
- **Phrase glossary.** Add, edit, delete, reorder phrases; CSV import of
  phrase/translation pairs via the ported `load_glossary`.
- **Series phrase suggestions.** The ported `extract_frequent_nouns` runs over
  a series' untranslated source text as a job and returns candidate terms with
  frequencies for one-click addition to the glossary.
- **Find and replace across a series.** The ported `find_in_series` lists
  matches across translated lines of a series with context; replacement is
  applied as a reviewed batch, not blind, and runs in one transaction.

---

## 8. Machine translation aggregator

Each translator becomes an `AsyncTranslator` with a single method that yields
chunks:

```python
class AsyncTranslator(Protocol):
    name: str
    async def translate(self, text: str, src: str, dst: str) -> AsyncIterator[str]: ...
    async def available(self) -> Availability: ...   # ok | needs_setup(message)
```

`GET /mt/stream?backend=&document_id=&line_number=` is a Server-Sent Events
endpoint. Ollama streams tokens as they arrive — the behaviour the desktop
panel already has. The single-shot backends (Google, Bing, DeepL,
LibreTranslate) yield once. MeCab and JParser return formatted morphology
blocks, built by the ported formatting functions (`_fmt`, `format_entry`,
`deconjugate`, the `edict2` index loader).

Results are cached in `mt_cache` keyed by backend, language pair, and the
SHA-256 of the source text, so revisiting a line costs nothing. Ollama
streaming responses are cached on completion only.

Availability degrades visibly rather than failing: when MeCab, `edict2`, or
Ollama is absent on the server, `available()` returns `needs_setup` with the
installation instructions, and the panel shows them — the same contract as the
desktop panels. The MeCab dictionary, the `edict2` file, and the Ollama host
are server-side configuration documented in the README; there is no setup
wizard.

**Known limitation — unofficial endpoints.** The Google and Bing translators
call free, unofficial endpoints. On the desktop each user had their own IP; on
one shared server they will be rate-limited and may break without notice.
They ship marked as best-effort and are not the defaults. DeepL (with the
user's own key) and Ollama (local model) are the recommended backends. This is
a documented limitation, not a bug to fix.

**Note (2026-10-12).** Google and Bing were not shipped; this was a user decision during phase 5
planning, because the desktop used keyed APIs and the shared-IP free endpoints are unreliable.
MeCab and JParser return structured entries instead of HTML. Cache keys in `mt_cache` include the
endpoint (LibreTranslate and Ollama keys hash the URL, and Ollama's also hash the model and prompt),
so one user's server never answers for another's. User-supplied LibreTranslate and Ollama URLs are
refused when they resolve to a non-global address, unless `TA_MT_ALLOW_PRIVATE_URLS` is true.

---

## 9. Background jobs

Long-running work: syosetu series index and chapter fetching, batch file
import, EPUB building, and batch WordPress publish/schedule.

A `jobs` table (`id, user_id, kind, params_json, state, progress, total,
message, result_json, created_at, finished_at`) plus one asyncio worker task
started with the API process. The worker claims jobs with
`SELECT ... FOR UPDATE SKIP LOCKED`, writes progress as it goes, and the client
follows along over SSE on `GET /jobs/{id}/events`.

`# ponytail: in-process worker, single replica. Swap for arq + Redis when the
deployment needs more than one API container.`

No Celery, no Redis, no broker in v1. Syosetu fetching keeps the desktop's
rate limiting — a fixed delay between chapter requests, enforced in the worker
so concurrent jobs cannot defeat it.

---

## 10. Publishing and statistics

**WordPress.** The ported `wp_publisher` keeps its payload builders
(`build_chapter_body`, `build_image_payload`, `build_illustrations_payloads`,
`build_payload`), the slug helper, endpoint normalization, status check, and
the auto-schedule computation (`compute_auto_schedule`, chapters-per-day,
default time, global or per-series scope). The re-publish safeguard stays:
publishing checks `wp_status` and the remote status first and refuses a second
publish without explicit confirmation. Per-series password settings and the
attribution toggle carry over as series and user settings. Batch publish and
batch schedule from the picker become a job.

**Statistics.** An activity heatmap calendar, a per-day table, streaks, and
period comparisons, served from `GET /stats` and computed by the ported
`compute_streaks` and `compute_period_comparisons` over `lines.translated_at`.
Per-series stats as today. The desktop's JSONL history log becomes
`work_sessions` rows, written when the client reports session boundaries.

---

## 11. Importing an existing `ta.db`

`tools/import_tadb.py --db path/to/ta.db --user email@example.com` runs
server-side against a copy of the SQLite file. It reads with the standard
library `sqlite3`, maps the desktop schema onto the new one, and writes
everything under one user:

- `profiles` → `profiles` (with `parse_chars`)
- `glossary`, `custom_words` → same, per profile
- distinct `documents.series_title` + `series_profiles` rows → `series`
- distinct `documents.volume_title` + volume metadata → `volumes`
- `documents`, `lines`, `document_images` → same, preserving `line_number`,
  `prefix`, `translated_at`, `series_order`, `anchor_position`, `is_cover`,
  `exclude_export`, and the WordPress status fields
- `QSettings` values are **not** imported; the user reconfigures settings and
  credentials once

The import is idempotent per source database: a `--dry-run` prints the counts
it would write, and a second real run against the same file is refused unless
`--force` is given. Rows that fail validation are reported and skipped, not
silently dropped — the run ends with a summary of written and skipped counts
per table.

---

## 12. Testing

- **API:** pytest with `httpx.AsyncClient` against the app, a real Postgres
  from `docker-compose` (not SQLite — the schema uses Postgres types), each
  test in a rolled-back transaction. The ported `core/` modules keep their
  existing unit tests from this repository, adapted only where imports moved;
  that is the point of porting them verbatim.
- **Tenancy:** one parametrized test per router asserting a second user's
  object id returns 404.
- **High-risk ports get dedicated modules:** merge/split, EPUB build, the
  WordPress payload builders, auto-schedule computation, and the `ta.db`
  importer.
- **Frontend:** vitest for the keymap, the dirty-lines store, and progress
  computation; Playwright for three smoke flows — log in and open a document,
  translate two lines and confirm the save indicator settles, and run a find
  and replace across a series.
- **MT backends** are tested against recorded fixtures, never live endpoints.

---

## 13. Deployment

`docker-compose.yml` with three services: `api` (FastAPI + the in-process
worker, serving the built SPA as static files), `postgres`, and `caddy` for
TLS and reverse proxy. Optional server-side extras — MeCab with its
dictionary, the `edict2` file, and an Ollama host — are mounted or pointed at
by environment variables and degrade to setup instructions when absent.
Configuration is environment-only; `TA_SECRET_KEY` and the database URL are
required for startup.

---

## 14. Explicitly out of scope

Dropped because the desktop context that justified them is gone:

- Clipboard auto-copy and its 400 ms debounce — the MT panels are in-page
- Always-on-top toggle
- Window geometry, splitter state, and panel-collapse persistence as
  OS-level settings (panel collapse state survives as a user setting)
- PyInstaller, AppImage, and NSIS packaging
- The MeCab / JParser setup wizard — server-side admin documentation instead
- In-app database backup and restore — `pg_dump`
- The CSV/LEX legacy importer (`migration.py`) — the `ta.db` importer
  supersedes it

Not built in v1, with no design debt either way: real-time collaboration on a
document, a mobile-specific layout, offline editing, and shared libraries
between accounts.

---

## 15. Phases

One phase per implementation plan. Each is independently shippable and leaves
the application usable.

1. **Skeleton** — repo scaffolding, FastAPI app, Alembic from empty, the full
   schema, auth with sessions and invites, per-user settings and shortcuts,
   the `ta.db` importer, docker-compose, CI running both test suites.
2. **Library** — document and series and volume CRUD, the picker screen with
   filtering and progress, merge, split, reorder, renumber, TXT and Markdown
   import and export.
3. **Editor** — line-card list, dirty-lines saving, the keymap and rebinding,
   parse navigation, find bar, glossary substitution on display, server
   spellcheck with custom words, Japanese highlighting, progress, inline
   images.
4. **Memory** — translation memory panel, phrase glossary with CSV import,
   series phrase suggestions, find and replace across a series.
5. **Aggregator** — the async translator protocol, the five MT backends,
   MeCab and JParser, SSE streaming, `mt_cache`, availability degradation,
   per-user credentials wired in.
6. **Acquisition and publishing** — the jobs table and worker, syosetu single
   and series fetch, batch file import, EPUB import and build, WordPress
   publish with the re-publish safeguard, batch publish and scheduling,
   statistics with the heatmap and streaks.

Phase 5 depends only on phase 1; it can run in parallel with 3 and 4 if that
suits. Everything else is sequential.
