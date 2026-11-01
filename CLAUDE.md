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
per-user settings/shortcuts/encrypted credentials, the `ta.db` importer, and
the library API (series/volumes/documents CRUD, reorder, renumber, merge/split, covers,
TXT import, TXT/Markdown export).

Phase 3a: editor API (lines, spell, images), Caddy, and the SPA under `web/` (login, picker,
series manager).

Phase 3b: editor screen: cards, CodeMirror input, saving, keymap, find, spell, images,
Edit Source/Split; Playwright smoke flows.

Phase 4: glossary API, translation memory panel, series find and replace (reviewed batch), phrase suggestions (MeCab via the optional `mecab` extra).

Series glossaries: there are no profiles. Each series owns its glossary (`/series/{id}/glossary`, the series page's
Glossary tab), and the editor, MT, phrase suggestions and batch import use the chapter's own series' glossary.
Spellcheck words have two layers: account-wide (`/words`, `custom_words.series_id IS NULL`, Settings → Editor) and
per series (`/series/{id}/words`); `POST /spell/check` with a `series_id` accepts a word from either list. Parse
characters are the user setting `parse_chars` (unset or not a string = `DEFAULT_PARSE_CHARS` in `api/core/text.py`;
`""` means don't split). The `ta.db` import copies each desktop profile's glossary and words into every series it
creates that used that profile (`api/core/tadb_glossary.py`). Spec: `docs/superpowers/specs/2026-10-22-series-glossary-design.md`.

Phase 5: machine-translation aggregator. DeepL and LibreTranslate stream through `GET /mt/stream`
(SSE; the single-shot backends yield once); Ollama no longer does (see Ollama background translation); MeCab and JParser return structured entries, not HTML. Results
are cached in `mt_cache`, whose keys include the endpoint: `deepl` and `libretranslate:<sha12(url)>`, so one user's server
never answers for another's (Ollama does not use `mt_cache`).
Per-user backend settings live under `/mt` and Settings → Machine translation. User-supplied LibreTranslate and
Ollama URLs are refused when they resolve to a non-global address unless `TA_MT_ALLOW_PRIVATE_URLS=true`
(guard in `api/mt/urls.py`).

Ollama background translation: users bring their own Ollama server (the operator `TA_OLLAMA_URL` and its admin override are gone;
a private LAN address needs `TA_MT_ALLOW_PRIVATE_URLS`, and `check_user_url` always refuses link-local and cloud-metadata addresses).
The package `api/ollama/` holds `prefs` (presets, chunk sizes), `chunks` (chunking and context), `prompt`, `answer` and `json_lines`
(parsing the model's reply), `outcome` (used / edited / ignored scoring), `work` (the queue's untranslated lines, `raw_sha` stale
check), `translate` (one chunk, splitting on failure), `lane` (a per-user in-process lock that serialises Ollama requests across
the runner and by-hand asks; single process only), `runlog` (each run's live log, in memory only, read at
`GET /ollama/runs/{id}/log` and shown on the Jobs page; single process only, empty after a restart), `endpoint` (URL, model and credential, with the setup message), `runner`
(a separate worker claiming `ollama_run` jobs, which the general worker skips; it works through `ollama_queue_items` until drained or the night window closes), `schedule` (the per-user
night windows and the once-a-minute tick that starts runs and cleans up), `store` (suggestions and the 91-day clean-up of old chunk
prompts and reasoning) and `stats`. `GET /documents/{id}/ollama/stream` (`api/routers/ollama_editor.py`) translates a chunk by
hand in a task that outlives its subscriber, so closing the card leaves it running and asking again follows it. Suggestions live
in `ollama_suggestions` (one per line; the text is NULLed by a flush or the clean-up, never by use or dismissal); chunk rows in `ollama_chunks` keep the settings,
timings and reasoning. A symbol-only line (a scene break such as `■` or `……`: non-blank with no letter by `has_letter` in
`api/core/text.py`) is never asked: `next_plan` fills it with its source (`fill_symbol_lines`, which leaves `translated_at` NULL
so the day heatmap does not count the copy) and `/tm/matches` returns nothing for it. The SPA has the `/jobs` page (running, Ollama queue, scheduled, history; Run now answers 409 with the setup
text without a URL) and Statistics → Ollama. Spec: `docs/superpowers/specs/2026-10-26-ollama-background-translation-design.md`.

Yomitan dictionaries: an admin can upload Yomitan format-3 term dictionaries (JMdict, 新和英, ...; kanji, frequency and
pitch-accent dictionaries are refused) in Admin → Dictionary. `api/core/yomitan_read.py` reads a zip (members read by name, never
extracted; limits like `epub_safety.py`) into one flattened entry per lookup key, and `api/core/yomitan_gloss.py` holds the
flattening rules (structured content and the plain multi-line 新和英 shape) into short meanings. `api/yomitan_store.py` installs
them into `dictionaries` / `dictionary_terms` (keyed by `identity_key`; re-uploading replaces) and owns the order. The order is the
`dictionary_order` row in `server_settings` (tokens `edict` / `yomitan:<id>`, first layer with a key wins); it is not an admin
setting and is not in `api.server_settings.effective`. `api/mt/lookup.py` layers EDICT2 and the Yomitan dictionaries for JParser and
MeCab (`layered`, `candidate_keys`; `session` is the test seam). A Yomitan entry with no POS tags is direct-only: it is never offered
to the deconjugator. Install runs as the `yomitan_import` job (`api/yomitan_job.py`); the upload cap is 64 MiB. Reading a large dictionary (JMdict) peaks around 500 MiB in the API process during the import job. Local check against
real zips: `python -m tools.yomitan_check <zip>... [--line TEXT]` (set `TA_DATABASE_URL` to a scratch database to time `jparser.run`);
never commit text from those dictionaries. Spec: `docs/superpowers/specs/2026-10-22-yomitan-dictionaries-design.md`.

Phase 6a: acquisition. Jobs (`api/jobs.py`; worker started in the lifespan; SSE at `/jobs/{id}/events`);
syosetu fetch (`api/core/scrape.py`: chapter numbers only, redirects checked, only `*.syosetu.com`);
batch TXT import (<=500 files, 12 MB (Caddy) / 12 MiB (API) per request) and EPUB import (`api/core/epub_read.py`,
limits in `epub_safety.py`: 64 MiB upload, 4 MiB per text entry, 32 MiB parsed per book, 256 MiB per-import
budget charged per image reference before reading, 900 chapters) are synchronous; per-volume EPUB build (`epub_build.py`). Form titles
with NUL are 422. Phase 6b: publishing and statistics. WordPress config is a `wordpress` credential plus `wp_*` user settings
(`api/wp_prefs.py`); `api/publish.py` builds chapters and records results; single publish is a request with a
server-enforced re-publish 409 (`confirm_republish`), batch publish and the Illustrations page are jobs
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

Settings page: the header has one Settings link (`Shell.tsx`, marked current for any `/settings/*` by `isSettingsPath`
in `web/src/settings/settingsNav.ts`) instead of the old Editor/Machine translation/WordPress/Shortcuts/Admin links.
It opens a layout route (`SettingsLayout.tsx`) whose sidebar (`nav aria-label="Settings"`) lists Editor, Machine
translation, WordPress and Shortcuts, then for admins an "Admin" group of Server, Invites, Dictionary and Backup &
restore; below 60rem the sidebar is a horizontally scrollable row. The sections are the same pages and panels as
before, each with a `div` root (the layout owns the page's only `<main>`); the admin panels sit in `AdminSections.tsx`
wrappers that give them a `PageHeader` and the `panel sec` look, behind one `AdminOnly` layout route (a non-admin sees
the `Admin only.` box and no panel mounts). `/settings` and `/settings/admin` redirect with `replace` to
`/settings/editor` and `/settings/admin/server`, `/admin` redirects to the latter, and `/settings/profiles` still lands
on Editor. Spec: `docs/superpowers/specs/2026-10-31-settings-sidebar-design.md`.

Onboarding: with no users, the SPA sends every page to `/setup` (`GET /setup/status`, `POST /setup/admin`,
which takes a Postgres advisory lock; `api/accounts.py`). Admin-only `/admin/settings` rows in `server_settings`
override `TA_LIBRETRANSLATE_URL`, `TA_MT_ALLOW_PRIVATE_URLS`, `TA_WP_ALLOW_PRIVATE_URLS` and
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

Library redesign: the Library (`/`) lists series only, as a bookshelf or a list (the user setting `library_view`, mirrored in
`localStorage` `ta.libraryView`, helper `web/src/library/viewPref.ts`). A series opens at `/series/:id?tab=volumes|glossary|tools|settings|wordpress&volume=<id>|none`: Volumes is a
two-pane view (volume list, then the selected volume's chapters with a selection bar and per-row ⋯ menu; "No volume" holds
loose chapters), and its grouping and numbering helpers live in `web/src/library/volumeGroups.ts`. A list over 100 chapters shows as
collapsible view-only blocks of 100 with a jump bar (`chapterBlocks`); only open blocks render. `documents.series_id` is
`NOT NULL` and deleting a series cascades to its volumes and chapters. `arrange()` (`api/library.py`) keeps each volume a
contiguous run numbered 1..N (loose chapters last) and runs after: creating a chapter, a chapter PATCH that changes its series
or volume, deleting a chapter, assigning chapters to a volume, a volume's order change or delete, reorder and renumber-by-title,
merge, split, and EPUB import. Syosetu-sourced series keep syosetu's chapter numbers. Renumbering alone leaves
`documents.updated_at` untouched (`renumber()` writes those rows in SQL). `POST /documents/export/zip`
exports ticked chapters; `GET /volumes` feeds the Move-to dialogs. Library dialogs (`web/src/ui/Dialog.tsx`: `ConfirmDialog`,
`PromptDialog`) replace native `prompt`/`confirm`, and none of them closes while its action is busy. WordPress volume indexing and
the plugin's Illustrations page are designed in the plugin's 1.6.0 spec (see `docs/TODO.md`).

Syosetu heading volumes: the fetch job puts each chapter in the volume of its `p-eplist__chapter-title` heading, per the
series' `syosetu_volume_mode` (`all` / `marker` with `syosetu_volume_marker` / `off`); the rules are pure, in
`api/core/syosetu_volumes.py`, and read the heading sequence stored in `series.syosetu_headings` (written by the fetch job
and regroup). The chapter-list GET writes only `syosetu_updated_at`; regroup's preview reads the index (writing the heading sequence and the date) only when no heading sequence is stored. Heading→volume links live in `volume_syosetu_groups` (hidden, so renamed
volumes keep receiving chapters; a merged volume holds several). `POST /series/{id}/syosetu/volume-headings`
(`api/syosetu_regroup.py`) previews or applies a setting change: it never deletes volumes and never moves chapters out of
volumes with no heading link. Chapters with no `source_url` (a ta.db import) count as syosetu's when numbered from 1 to the last known
syosetu chapter, as the fetch job already treats them (`syosetu_chapters`). `POST /series/{id}/volumes/merge` merges volumes into one (the Volumes tab's Select mode).

Volume naming: a volume has `kind` / `volume_index` (Numeric(10,3), optional) / `subtitle`, not a title; names are unique ignoring case
by kind + index, or kind + subtitle when unnumbered (partial indexes `uq_volumes_kind_index` / `uq_volumes_kind_subtitle`; migration
`6182106ad19b` split old titles). The rules are `api/core/volume_names.py` and its TS twin `web/src/library/volumeNames.ts` (camelCase
names), both tested against `volumeNames.cases.json`. `Volume.full_title` = `epub_title` override, else the series' `volume_title_template`
(blank = `DEFAULT_TEMPLATE`); `Volume.label` is the short SPA form. `api/volume_order.place` positions new and re-keyed volumes (ta.db import
appends in desktop order; an explicit `volume_order` on create is kept). `volumes.wp_volume_title` freezes at the first publish; WordPress gets `Volume.wp_name`.
Chapters in a volume of a non-syosetu series also send `chapter_label` = `f"{wp_name} Chapter {n}"`
(`volume_position` in `api/library.py`); the label never feeds the series-wide `chapter_index`.

New series: the `/new` page (`web/src/library/newSeries/`) offers Syosetu, EPUB or Paste. Series have optional credit fields
`original_title`, `original_author`, `author_romaji` (the translated `title` stays required). `POST /scrape/syosetu/novel`
(`read_novel` in `api/core/scrape.py`) reads a novel's title, author and first chapter without creating anything; Create then runs
`syosetu_fetch` for the first chapter only (its result carries `document_ids`). A syosetu short story (no index, text on the root page)
is a one-chapter series numbered 1 whose chapter URL is the series URL. `/epub/import` with `new_series=true` refuses a taken title
(409) instead of reusing the series. EPUB export: a volume with no `epub_author` uses the series' `author_romaji`; `original_title`
(with `original_author`) is written as `dc:source`.
The export (`epub_build.py`, fixed pages and image rules in `epub_pages.py`) writes `dcterms:modified`, a stylesheet,
a cover page, a title/credits page and landmarks; images keep only EPUB core types (sniffed from their bytes) under
ASCII-safe names. A volume with no `epub_identifier` gets a `urn:uuid` derived from the series' `created_at` and the
volume id (`book_id`, `api/routers/epub.py`), so re-exports are the same book to a reader. The translator credit
(`dc:contributor`, role `trl`) is the volume's `epub_translator`, else the user setting `epub_translator`
(Settings → Editor). Import skips a text-only `epub:type="titlepage"` page (`_title_page`, `epub_read.py`).

Volume Illustrations chapter: EPUB import splits chapters by the table of contents, not by file (`api/core/epub_runs.py`,
fed by `epub_read.py`), and gathers the picked image-only pages into one chapter titled "Illustrations" (the picker shows them
as one row, `web/src/library/epubRows.ts`). `documents.is_illustrations` marks it: at most one per volume, text-free, never in
a syosetu series (rules and 409 messages in `api/illustrations.py`; Mark/Unmark is a PATCH). `arrange()` puts it first in its
volume, and it stands outside `chapter_number` (`api/library.py`) and the unlock chain. It publishes as the volume's
illustrations page through `POST /documents/{id}/wp/illustrations` (the `wp_illustrations` job, `confirm_republish` 409);
batch publish uploads it the same way and gives it a schedule slot (`publish_date` on the first batch); its status
refresh asks `/status?illustrations=1&volume_title=<wp_name>`. Spec: `docs/superpowers/specs/2026-10-24-volume-illustrations-chapter-design.md`.

Volume covers: covers live on volumes, never on chapters (`document_images` has no cover flag; migration `44f4d937ee05`
moved each volume's first chapter cover onto the volume and kept other chapter covers as images excluded from export).
`volume_covers` holds one row per volume; replacing makes a new row, so `GET /covers/{id}` is cached for good. `VolumeOut`
carries `cover_id` (a `column_property`; `api/covers.py` `forget` reloads it after a change) and `is_series_cover` (at most
one per series, `uq_volumes_series_cover`, set by `PUT /series/{id}/cover-volume`). The series cover is the flagged
volume's cover, else the first volume's by `volume_order` that has one (`covers.effective_series_cover`, its SPA twin
`seriesCover` in `web/src/library/shelf.ts`); WordPress gets it with chapter 1. `POST /volumes/{id}/cover/url` downloads
a direct image address (`check_user_url` on every hop, no private-address override, 3 redirects, 10 MiB); an HTML answer is
a 422 telling the user to copy the image address. Merging volumes keeps one cover and moves the series choice to the kept
volume; deleting a volume deletes its cover. Spec: `docs/superpowers/specs/2026-10-24-volume-covers-design.md`.

Library filters: `series.status` (`ongoing` / `on_hold` / `dropped` / `completed`, default ongoing; `SeriesCreate` takes none, PATCH sets it),
`source` (`syosetu` / `epub` / `other`, set at creation: `POST /series` from a `syosetu_url`, EPUB import, ta.db import by URL; the Settings tab edits it),
`archived_at` and `syosetu_updated_at` (syosetu's latest chapter post date). `POST /series/{id}/archive|unarchive` set and clear `archived_at`;
archiving hides a series only from the Library's default filter, never from the API lists, its chapters or the series page, which shows
an "Archived" note with Unarchive. The Library's view, sort, direction and filters are pure in `web/src/library/libraryQuery.ts`;
they are account settings `library_view`, `library_sort` and `library_filters` (read and written through
`web/src/settings/useAccountPref.ts`), mirrored in `localStorage` (`ta.libraryView`, `ta.librarySort`, `ta.libraryFilters`,
`libraryPrefs.ts`) so the page paints before `/settings` arrives. The account's value wins once it does, and a browser's value
with no account one is written up once. Validation is in `api/settings_rules.py`. Specs:
`docs/superpowers/specs/2026-10-25-library-filters-sort-archive-design.md`,
`docs/superpowers/specs/2026-10-30-series-page-revision-design.md` §5.

Series summary: the desktop's chapter 0 is `series.wp_summary` (columns added by migration `6fd2c71c71da`), edited on the series'
WordPress tab (`?tab=wordpress`, `web/src/library/SeriesWp.tsx`, status rules in `summaryStatus.ts`). Saving a changed non-blank text sets
`wp_summary_pending` (blank clears it); `api/wp_summary.send` posts it as chapter index 0 just before the next chapter of that series in single,
batch (once per series) and Illustrations publishes, only when the text is still the one sent (an edit meanwhile stays pending), and a failure is stored in `wp_summary_error` without failing the chapter. Text helpers are
pure, in `api/core/wp_summary.py`. `build_chapter` refuses a chapter numbered 0 or holding `wp_chapter_index` 0
(`publish.SUMMARY_MOVED`). Migration `b7e3a1c95d42` (move_series_summaries) and the ta.db importer (`api/core/tadb_summary.py`)
turn live chapter-0 documents into the summary; the migration also clears a non-live index 0 to NULL, and the importer
stores `wp_chapter_index` NULL for any imported chapter whose desktop value is 0 and caps the summary (the line caps, and none
written over 100,000 characters). Spec: `docs/superpowers/specs/2026-10-25-series-wordpress-tab-design.md`.

Series page revision: the chapter table (`web/src/library/ChapterTable.tsx`) has a Select toggle: in select mode a
row click ticks it (shift-click a range over the rows on screen, `rangeToggle.ts`), the title is text and the drag
grip is hidden; Esc, Done and Clear leave the mode. Columns are the user setting `series_columns` (validated in
`api/settings_rules.py`, ids in `web/src/library/chapterColumns.ts`, cells in `chapterCells.tsx`); # and Chapter
cannot be hidden, the WordPress ones only show with a WordPress credential (`useWpConfigured`). The account-saved
preference hook is `web/src/settings/useAccountPref.ts` (`localStorage` copy, the account wins, a browser-only value
is written up once). The tag (`web/src/publish/wpTag.ts`, `WpTagButton.tsx`) reads Published / Scheduled /
**Published?** (a schedule whose time has passed) / Not posted from the stored `wp_status`; clicking it checks the
live status and offers Reschedule… (`PublishDialog` mode, sends `confirm_republish` itself), Update post… or
Publish…. Check status in the selection bar loops the per-chapter route, 50 a click. New counts on
`DocumentListItem`: `char_count`, `word_count`, `ollama_waiting`. `DELETE /documents/{id}?images=move` moves a
chapter's images to its volume's Illustrations chapter (`api/image_moves.py`: a clashing `src_path` is renamed, not
dropped; 409 outside a volume, in a syosetu series, or for the Illustrations chapter), and the delete dialog asks;
multi-select stays one request per chapter. Series-wide Ollama queue/flush live in Tools. Spec:
`docs/superpowers/specs/2026-10-30-series-page-revision-design.md`.

Series Gallery: the series page's Gallery tab (`?tab=gallery`, `web/src/library/gallery/`) shows every
`document_images` row of the series' chapters plus each volume's cover, grouped by volume (`volume_order`,
cover first, "No volume" last) with a volume filter; the grouping and display order are pure in `galleryGroups.ts`.
`GET /series/{id}/images` returns the rows (cover rows use `volume_covers.id`) and never the bytes; tiles load
`GET /images/{id}` / `GET /covers/{id}` with `loading="lazy"`, and no thumbnails or other derived images are stored.
A tile opens a native `<dialog>` viewer: Set as volume cover (`POST /images/{id}/cover` copies the bytes into a new
`volume_covers` row, 415 for a non-raster image), Move to Illustrations (`POST /images/{id}/move`, `check_can_move`'s
409s) and Delete (`DELETE /images/{id}`). A loose chapter's image offers neither cover nor move, and nothing in the
Gallery opens the editor. An Illustrations chapter left with no images by a Gallery delete is deleted in the same
request (`image_moves.drop_if_empty`), `arrange()` runs and its WordPress page is left alone.

Editor status bar and reading aid: the status bar groups a breadcrumb, previous/next chapter buttons with the volume's chapter
list, place, progress and tools; every move out of the chapter (arrows, list, end card) goes through `useLeave`, which flushes the
save first and refuses to move on a failed save. Floating `JumpBack` buttons and a `ChapterEnd` card follow the cards. `POST /readings`
(`api/routers/readings.py`) tokenises text with MeCab and returns surfaces and readings only (`available: false` without the
`mecab` extra); the SPA places them as ruby. The user setting `reading_aid` (`off` / `hiragana` / `katakana` / `romaji`) picks the
mode; generated readings show on the active card only. Author ruby (`漢字(かんじ)` in the source) renders as `<ruby>` on every card
whatever the mode (`web/src/editor/ruby.ts`, `authorRuby`). A status-bar "Glossary ruby" toggle (the account setting
`glossary_ruby`, default off) shows the card's source as the original text with each glossary match carrying its translation
as `<rt class="rt-glossary">` ruby (`web/src/editor/glossaryRuby.ts`); glossary ruby wins over generated reading ruby and author
ruby wins over glossary marks. The lines endpoint sends `LineOut.glossary_marks` (UTF-16 `from`/`to` into `plain_text`, plus
`shown_from`/`shown_to` and the translation; computed by `api/core/glossary_marks.py`, which mirrors `replace_and_parse`), and
`LineOut.plain_text` (`raw_text` with `$`/`%` stripped anywhere). E2E: `web/e2e/editor-nav.spec.ts` with the `Nav series` seed.
Focus and keys: `useEditorKeys` lets bound keys run from buttons and links (except Enter), Esc closes Find first and
then returns to the editor, and typing on the bare page lands in it (Space still presses a focused button). A key that
cannot act says why (`This line has no translation yet`, `No untranslated lines left`, `No misspelled words on this
line`); Enter on the last line lands on the chapter end card, and Go to line is a `PromptDialog` that refuses a number
the chapter does not have (`parseLineNumber`, `rows.ts`). `useLeave` (`useLeave.ts`) is the one way out — arrows, crumbs,
the end card and links in the app header all queue a move that goes when the save lands and asks once when it fails
(`Leave with unsaved lines?`, the lines and error frozen at that moment); Cancel or Esc keeps the page, a later success
carries the move out, a 401 passes to sign-in, and a save gives up after 20 s.
`saveFailure` (`saveErrors.ts`) names a refused save and marks it permanent, so a 404 or a 422 is never retried; the
`.sb-alert` row under the status bar holds the message with Retry and Copy unsaved text and stays mounted across
attempts, and notices (`useNotice`, 8 s) clear when the line changes.
`Use suggestion N` (Alt+1..9) clicks the `[data-use="N"]` button in the aid column: slots are fixed by `assignSlots`
(`useSlots.ts`) — translation memory 1 and 2, then each backend that has a Use button (MeCab and JParser have none) —
and each button prints its real key in `.use-key`. A memory match still on the previous line and a machine card still
streaming cannot be used. Each line keeps its CodeMirror history for the session (`CodeEditor`'s module map keyed
`${documentId}:${lineNumber}`), so Ctrl+Z after a Use restores the replaced text after moving away and back; the map is
unbounded until reload. `KeyHelp.tsx` is the Ctrl+/ sheet. `StickyTop.tsx` holds the status and find bars and publishes
`--top-h`.
Spec: `docs/superpowers/specs/2026-10-27-editor-status-bar-reading-aid-design.md`.

Backup and restore: `api/backup/` writes one zip per server — `tables/<name>.csv` (Postgres `COPY ... FORMAT csv, HEADER`,
so it is version-portable), the `dict/` files that live under `TA_DATA_DIR`, and a `manifest.json` (format 1, the alembic
revision, row counts, the scrypt KDF and a passphrase check value). Only `api_credentials.secret_enc` is passphrase-locked
(scrypt; the passphrase must be 12 characters when a backup is created and is never length-checked on restore); everything
else is as it is. Left out: `sessions`, jobs still `queued`/`running` (any reference to one, e.g. `ollama_chunks.job_id`,
becomes NULL) and `uploads/`; finished job history stays, chapter passwords in a `wp_publish` result included (they are
content, not secrets). The export streams in its own `REPEATABLE READ`, read-only transaction.

Restore (`api/backup/restore.py`) validates the whole file first (zip sanity, member names and size caps, a known revision
not newer than head, the passphrase check value, the table set) and then runs in one transaction on its own connection: drop
the app tables (`Base.metadata` plus `RETIRED_TABLES`, today `profiles`; a stray table is never exported or dropped), replay
the migrations to the backup's revision, `COPY` the rows in (header and row count checked), re-encrypt the credentials,
reset the sequences, upgrade to head. A failure before the commit leaves the old server untouched and nothing after the
commit may say otherwise. It runs in a background thread, because the `jobs` table is one of the tables it replaces, with its
status in memory at `GET /restore/status`.

The admission gate (`api/backup/state.py`) counts out-of-request work in flight — a job handler, an Ollama run, a scheduler
tick, a by-hand Ollama chunk, an `/mt/stream` translation — and a restore begins only when that count is 0 and no job is
queued or running. The check runs again after the upload, under the same lock that turns maintenance on, so nothing slips in
between. In maintenance every route but `/restore/status` and `/healthz` answers 503, and the worker, the runner and the tick
claim nothing. Single process only, like the Ollama lane. The passphrase lives only in the request that uses it: never in
`jobs.params`, a log or the status route.

Dictionaries: the backup's `dict/` members are validated and staged in `dict.restore/` before the commit; after it, the rename
to `dict.ready/` is the marker that the database committed, then `dict/` becomes `dict.old/` and `dict.ready/` becomes `dict/`
(an empty stage removes a file the backup did not carry). A failed swap leaves `dict.ready/` and the status warns;
`recover_dictionaries()` in the lifespan completes it at the next start and always leaves exactly one directory. Files named
by `TA_EDICT_PATH` / `TA_CONJUGATIONS_PATH` are never touched.

Routes: `POST /admin/backup` (a native form POST that streams `ta-backup-YYYY-MM-DD.zip`; 409 while restoring or when the
database is not at head), `POST /admin/restore` (admin, confirm word `RESTORE`) and `POST /setup/restore` (open while no user
exists), each one streamed upload capped at 4 GiB in Caddy and again in `api/backup/uploads.py` (swept after 24 h), and
`GET /restore/status` without a login. SPA: Admin → Backup & restore (`web/src/admin/BackupPanel.tsx`), the setup wizard's
"Start fresh" / "Restore from a backup" choice, and `/restore` outside the setup gate, polling the status while every other
call is 503. Spec: `docs/superpowers/specs/2026-10-27-backup-restore-design.md`.

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
  series' chapters; the `ta_e2e` database is reset once per run, not per spec.
- **Size discipline:** no Python module over ~400 lines (spec §2).
- Tests use a per-test transaction rolled back at the end (`db` fixture), with
  `app_client` overriding `db_session`. `insecure_cookies` is needed because
  TestClient speaks plain http.
- `TA_ALLOW_PUBLIC_SIGNUP` is reserved and inert; `/auth/accept-invite` is the only
  account-creation path.
- MT backends take an injected `httpx.AsyncClient`; tests use `httpx.MockTransport` fixtures
  (`tests/fixtures/mt/`), never live endpoints. The `/mt/stream` cache write runs in its own session
  (`_put_sync` in `api/routers/mt.py`), one of the sanctioned commits outside the route boundary; the others are the
  job worker (`JobContext.progress`, `JobContext.report` (job row only, its own session, throttled)
  and `run_next` in `api/jobs.py`) and the Ollama commits: the runner (`api/ollama/runner.py`), the by-hand chunk
  save (`api/routers/ollama_editor.py`) and the scheduler tick (`api/ollama/schedule.py`), each in its own session. The restore owns its own
  transaction too (`run` in `api/backup/restore.py`: the jobs table it would report to is replaced mid-run). WordPress calls take an injected `httpx.Client`
  the same way (`http_client` seams in `api/routers/wp.py` and `api/publish_job.py`).
- Tests set `TA_RUN_JOBS_WORKER=false` and drive jobs with `jobs.run_next()`, swapping `api.jobs.SessionLocal` for the test session.
