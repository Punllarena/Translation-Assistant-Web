# Library redesign: series shelf and two-pane series page

Date: 2026-10-20 · Status: draft for review

## Why

The Library (`web/src/library/Picker.tsx`) is one flat table of every chapter, grouped by
series. Each row repeats a series dropdown, three export links and a Publish button, so a row
is ~110 px tall and about seven chapters fit on screen. Volumes are invisible there. The series
page (`SeriesPage.tsx`) opens on a settings form, with chapters, volumes and tools stacked below
it in no particular priority.

The owner wants to browse **series → volumes → chapters**, in that order, and to publish to
WordPress **one volume at a time** (their usual workflow). The current look and design tokens
(phase 7a, `web/src/styles/tokens.css`) are "good enough"; this is a layout and navigation
redesign, not a new visual language.

Alongside it, the owner ruled that **every document belongs to a series**. A oneshot is a
series with one chapter. There is no "Unsorted" bucket and no automatic catch-all series.

## Goals

1. Library shows series only, as a cover **Bookshelf** grid or a **Compact list**, switchable.
2. Opening a series shows a **two-pane** page: volumes on the left (at least ¼ width), the
   selected volume's chapters on the right (¾).
3. Publishing and exporting a whole volume is one obvious action; per-chapter export, publish
   and reorder remain available without cluttering every row.
4. `documents.series_id` becomes required everywhere: API, importers, UI, database.
5. Native `window.prompt` / `window.confirm` in the library and series screens are replaced by
   in-app dialogs (they also fail in embedded browsers such as the Claude desktop pane, where
   `prompt()` throws "not supported").

## Non-goals

- No new colour palette, fonts or theme work; reuse tokens and existing component styles.
- The editor, Statistics, Profiles, MT, WordPress settings and Admin pages are untouched.
- No new series/volume cover upload concept: covers stay per-chapter (`DocumentImage.is_cover`).
- No change to how batch publish, illustrations or EPUB build work server-side; only where
  they're launched from. Volume-aware WordPress indexing and an EPUB-import Illustrations
  chapter are deferred to `docs/TODO.md`.

## Anti-goals (a failure even if it "works")

- Any path that silently creates a document with no series, or silently invents a series the
  user didn't ask for (except the one-time migration and `ta.db` import rule below).
- Rows that go back to carrying a full set of always-visible controls.
- Deleting a series without saying how many chapters go with it.

## Screen 1: Library (`/`)

**Toolbar:** search box (filters by series title), view switch (Bookshelf / List), `Import…`,
`New series` (primary). `New document` leaves the Library toolbar; documents are created from
inside a series (see Screen 2).

**Bookshelf view (default):** responsive grid of series. Each item: cover (2:3), title, size
line (`1 vol · 21 ch`, or `212 ch` when the series has no volumes), progress bar. Click opens
`/series/:id`.

**Compact list view:** one row per series: thumbnail, title, size, progress bar, last edited.
Click opens the series. (Column sorting is the builder's call; not required.)

**Remembered view:** stored per device in `localStorage` (`ta.libraryView`), wrapped in
try/catch like `ta.theme`. *[my call: a per-device convenience, not worth a server setting]*

**Series cover:** the cover of the series' first volume, falling back to the first chapter in
series order that has a cover. No cover → a tile in a token colour with the title set on it.
*[my call]*

**Progress:** sum of `translated_count` / sum of `line_count` over the series' documents.
**Last edited:** max `updated_at`.

**Empty state:** no series → a short message with `New series` and `Import…`.

**Mockups:** `.superpowers/brainstorm/75-1792486555/content/library-layout.html` (options A and C
were chosen together).

## Screen 2: Series page (`/series/:id`)

Header: breadcrumb `Library ›`, series title. Tabs: **Volumes** (default), **Tools**, **Settings**.

### Volumes tab: two panes

Grid `1fr 3fr` (left pane never narrower than ¼).

**Left pane: volume list.** Each entry: cover (~52 px wide), title, chapter count, progress
bar; the selected one is highlighted. Below the list: `+ New volume` (opens a dialog for the
title). If the series has chapters with no volume *and* has volumes, a final entry
**"No volume"** lists them. *[my call]* Selected volume is reflected in the URL
(`?volume=<id>` or `?volume=none`) so reloads and links land on it. *[my call]*

**Series with no volumes:** no left pane; the chapter table spans the full width with a
`New volume` button in its header.

**Right pane: selected volume.**
- Header: large cover (~72 px), volume title, `N chapters · X% translated · edited <when>`.
- Header actions: **`Publish volume…`** (primary; opens the existing batch publish dialog for
  that volume's chapters), **`Export volume ▾`** (EPUB, Markdown ZIP, Ruby Markdown ZIP; the
  ZIPs are new per-volume variants of `GET /series/{id}/export/markdown`, with the same
  skip-incomplete rule and `X-TA-Skipped-Incomplete` header), and
  **`⋯`** (Edit volume details: the title and EPUB metadata form from today's `VolumeEditor`;
  Publish illustrations; Delete volume).
- `New chapter` (opens the new-document dialog with series and volume preset).
- **Chapter table:** drag handle, checkbox, number, chapter title, progress, edited, WordPress
  badge (`Published` / `Scheduled` / `Not posted`), `⋯`.
  - Clicking the row (outside the handle, checkbox and `⋯`) opens `/documents/:id`.
  - Row `⋯` menu: Open · Export TXT / Markdown / Ruby Markdown · Publish… · Set cover… /
    Clear cover · Split… · Move to… · Delete.
  - **Selection bar:** ticking one or more rows swaps the table header for
    `N selected · Export ▾ · Publish… · Move to… · Merge · Delete · Clear`.
    Merge keeps today's rule (the server decides what's mergeable); the chapter heading
    question becomes a dialog field. Delete confirms with the count
    (`Delete N chapters? This can't be undone.`). Export downloads **one ZIP** of the selected
    chapters in the chosen format (TXT, Markdown, Ruby Markdown). *[my call]*
  - **Reorder:** drag by the handle within the table, or drop a row onto a volume in the left
    pane to move it there. Both follow **Ordering and numbering** below. `Renumber by title`
    moves into the volume `⋯` / table header as the keyboard path. *[my call: keep it, it's the
    keyboard alternative today]*
- **Move to…** dialog: pick a volume in this series or another series (and optionally a volume
  there). Replaces the per-row series dropdown.

### Ordering and numbering (owner's decision)

- **Series with volumes:** volumes are contiguous runs of `series_order`, in `volume_order`
  (chapters with no volume come after the last volume). The **number shown is the position
  within the volume**: Volume 1 Chapter 1…x, Volume 2 Chapter 1…, and so on.
- Dragging within a volume, or dropping a chapter onto another volume (it goes to the **end**
  of that volume), rewrites `series_order` for the whole series so volumes stay contiguous. This
  needs a server operation that assigns the volume and repositions in one request (today's
  `PUT /series/{id}/order` plus `POST /volumes/{id}/documents` are two). *[builder decides the
  endpoint shape]* Assigning chapters to a volume through any other path (Move to…) follows the
  same rule.
- **Series without volumes:** the number shown is the chapter's position in the series.
- **Syosetu series** (series with a syosetu URL): keep syosetu's own indexing. The fetch job already
  stores syosetu's chapter number as `series_order` (`api/fetch_job.py:51-54`) and skips numbers
  it already has, so renumbering would make a re-fetch duplicate chapters. In these series the
  shown number is `series_order`, and drag-reorder and Renumber by title are disabled.
  Moving a chapter between volumes changes only `volume_id`. *[my call, following the owner's
  "copy the series indexing"]*
- **WordPress is out of scope here.** Publishing still uses series-wide `series_order`; making it
  volume-aware (including a per-volume Illustrations entry after each volume's last chapter) is
  recorded in `docs/TODO.md`. Moving chapters may therefore change the index a later re-publish
  sends; the owner accepted this for now.

**Mockups:** `series-layout-v2.html` (proportions) and `chapter-actions.html` (actions) in the same
brainstorm folder.

### Tools tab *[my call: these exist today and need a home]*

Syosetu fetch (only when the series has a URL), Find and replace, Phrase suggestions: the
existing components moved as-is.

### Settings tab

Title, series URL, profile, the WordPress fields (`SeriesWp`), series-wide Markdown ZIP
exports, and **Delete series** at the bottom in a danger zone.

## Every document belongs to a series

**Database:** `documents.series_id` becomes `NOT NULL`, FK `ON DELETE CASCADE` (deleting a series
deletes its chapters, their lines and images by existing cascades). Autogenerated migration
plus a data step that runs first (see Migration).

**API:** `series_id` is required on document create (`schemas/documents.py` `DocumentCreate`), on
TXT single/batch import (`routers/transfer.py`), and on EPUB import (already either-or; keep it).
`PATCH /documents/{id}` refuses `series_id: null` (422). `DocumentOut.series_id` becomes `int`.
Code paths that branch on `series_id is None` (`library.py`, `publish.py`, `restructure.py`,
`routers/lines.py`, `routers/documents.py`, `routers/jobs.py`) are simplified. Regenerate
`web/src/api/schema.d.ts`.

**Series picker in the UI:** wherever a document is created or imported, the user must pick a
series. The picker offers existing series plus "New series…" (type a title, created on submit).
There is no "Unsorted" option anywhere; `SeriesChoice.tsx` and the per-row dropdown go away.

**Delete series:** a dialog: *Delete "<title>" and its N chapters? This can't be undone.*
The user types nothing extra; the confirm button reads `Delete series and N chapters`.
*[my call on wording; the owner asked for "a warning"]* API docstring at
`routers/series.py:75` updated.

**`ta.db` import:** a desktop document with no series becomes its own series titled with the
document title (the oneshot rule). This is the one sanctioned automatic series creation, because
the import runs unattended. The dry run reports how many such series it would create.
If a series with exactly that title already exists, the document **joins it** rather than
creating "Title (2)", so a forced re-import keeps its promise to add only new chapters (the
existing per-series duplicate check then skips it). *[my call]*

**Migration of existing data:** every document with `series_id IS NULL` gets its own new series
titled after the document; volume_id stays NULL, `series_order` = 1.

**Title collisions (migration only):** `series` is unique on `(user_id, title)`. When the
migration's new title collides, append ` (2)`, ` (3)`, … *[my call]*. (The importer joins an
existing series instead; see above.)

## In-app dialogs

One small dialog component built on native `<dialog>` + `showModal()` (the pattern the publish
dialogs already use), covering confirm (with danger styling) and single-field text input.
Replaces every `window.prompt`/`window.confirm` in `web/src/library/` (Picker, Volumes,
SeriesPage, Chapters). Other screens may adopt it later; not required here.

## Narrow screens

Under ~768 px the two panes stack: the volume list becomes a horizontal scroll strip of covers
above the chapter table. Bookshelf grid drops to 2 columns. Rows keep the `⋯` menu; the drag
handle remains. *[my call]*

## Testing

- API: pytest for required `series_id` (create, import, PATCH null → 422), delete-series
  cascade, migration data step (including title collisions), `ta.db` oneshot rule (including
  joining an existing series on re-import), contiguous renumbering on move/reorder, syosetu
  series keeping their numbers, per-volume and selection ZIP exports.
- Web: vitest for pure helpers (series progress/cover selection, view preference).
- Playwright: update existing library/series specs; add a flow for Library → series → volume →
  publish volume dialog, and delete-series warning. Follow the E2E seeding conventions in
  `CLAUDE.md`.
- Update `CLAUDE.md`'s phase notes.

## Left to the builder

Component breakdown and file layout under `web/src/library/` (keep modules small); whether
series aggregates are computed client-side from `/documents` or served by a new endpoint; how
the cover image id reaches the client; exact spacing and sizes within the existing tokens;
drag-and-drop implementation details.
