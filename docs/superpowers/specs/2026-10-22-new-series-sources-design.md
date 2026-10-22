# New series: three starting points

*2026-10-22. Status: approved.*

## Intent

A user who presses **New series** is starting a new translation, not moving existing work in
(that is what the Import page is for). A new translation begins one of three ways:

1. **From syosetu.** The user has the novel's syosetu URL.
2. **From an EPUB.** The user already owns the EPUB of at least one volume.
3. **From somewhere else.** The user will paste chapter text in by hand.

So New series should ask which of the three it is, then run a flow fitted to it. Each flow should
leave the user one step from translating. The syosetu flow should drop them in front of chapter 1.

The series also gains a record of the original work: its **Japanese title** and **author**, plus the
**author's name in romaji**. The Japanese title is kept so the EPUB can credit the original.

## Goals

- New series opens a chooser with three options: Syosetu, EPUB, Paste.
- Every series can record the original Japanese title, the original author, and the author's romaji
  name. All three are optional. The translated (English) title stays the series name and is
  required.
- **Syosetu:** paste a URL. The app reads the Japanese title and author from the novel's index page
  and shows them. The user types the translated title and the author romaji, then confirms. The
  series is created with that URL and **only the first chapter** is fetched. The user then lands on
  that chapter.
- **EPUB:** the same logic as today's EPUB import (inspect, prefilled volume name, metadata,
  chapter ticks, import, cover). The differences: it always creates a new series, and it has
  the new series fields.
- **Paste:** today's New series dialog, with the three optional original-work fields added.
- The Japanese title appears as attribution in exported EPUBs.

## Non-goals

- Fetching the rest of a syosetu series on creation. The rest is fetched as today, from the series'
  Tools tab. Periodic background scraping of every syosetu series is a separate piece of work. Add
  it to `docs/TODO.md` (see below).
- Changing the Import page. It still covers bulk TXT, ta.db, and adding an EPUB to an existing series.
- Changing how a series' chapters, volumes or numbering work once it exists.

## Anti-goals

- New series must not quietly attach to an existing series. Today's EPUB import reuses a series
  whose title matches; the New series EPUB flow must refuse a duplicate title instead.
- A syosetu New series must not start a long fetch of the whole novel.
- The Japanese author name must not replace the romaji name where readers see an author
  (the EPUB `dc:creator`). *(The library does not show authors today, and this work does not add
  them. My call.)*

## Current state (for the builder)

- `Series` (`api/models/content.py`) has `title` (unique per user), `syosetu_url` and settings.
  It has no original-work fields.
- New series is a `PromptDialog` asking for a title (`web/src/library/Library.tsx`), calling
  `POST /series` (`SeriesCreate`: `title`, `syosetu_url`).
- EPUB import: `POST /epub/inspect`, then `POST /epub/import` (`api/routers/epub.py`), with the
  SPA in `web/src/library/ImportEpub.tsx` and the reusable `useEpubBook` / `EpubPicker` /
  `EpubFields` / `EpubResult` in `web/src/library/epubBook.tsx`. `_series()` finds or creates the
  series by title. Volume metadata (`epub_author`, …) is per volume.
- Syosetu: `api/core/scrape.py` reads the chapter index (`fetch_series_index`) but not the novel's
  title or author. Fetching runs as the `syosetu_fetch` job
  (`POST /series/{id}/syosetu/fetch` with `nums`), which also places chapters into heading volumes.
  The SPA shows job progress with `JobProgress`.
- Profiles are gone (series glossaries, merged in #14); each series owns its glossary. This work is
  on its own branch, `claude/new-series-sources`, off `main`.

## Design

### Data

New `Series` columns, all `Text NOT NULL DEFAULT ''`:

- `original_title`: the Japanese title.
- `original_author`: the author as written in Japanese.
- `author_romaji`: the author's name in romaji.

*(Names are the builder's call; these are suggestions.)* They are added to `SeriesCreate`,
`SeriesUpdate` and `SeriesOut`, with the same NUL and length rules as other free-text fields.
Existing series and ta.db imports get empty values.

They are editable on the series' **Settings** tab, next to the title.

### The chooser

**New series** (Library header and the empty-library actions) opens a dialog with three choices,
each with a one-line description:

- **Syosetu**: "Start from a syosetu URL and fetch the first chapter."
- **EPUB**: "Start from an EPUB of a volume you have."
- **Paste**: "Start empty and paste chapters in yourself."

Picking one moves to that flow, which can go back to the chooser. *(Whether this is one dialog with
steps or a page at its own route is the builder's call. The EPUB flow is long because of its
chapter checklist, so a page such as `/new` may suit it better than a dialog.)*

### Shared series fields

All three flows show the same series block:

| Field | Required | Prefill |
|---|---|---|
| Title (translated) | yes | none |
| Japanese title | no | syosetu: index page title; EPUB: book title |
| Author | no | syosetu: index page author; EPUB: book author |
| Author (romaji) | no | none |

A title already used by one of the user's series is refused with a clear message (the existing
`(user_id, title)` unique constraint). Today that refusal is a 409 or a constraint error, so check
it and surface it next to the field.

### Syosetu flow

1. The user pastes a URL and presses **Read**. A new endpoint (e.g. `POST /scrape/syosetu/novel`
   with `{url}`) validates it as a series root, as `_validate_series_url` does. It reads the
   **first index page only** and returns the Japanese title, the author, and the first chapter
   (number and title). The full index is not walked here. It uses the same `_slot()` and
   throttle as the other request-path syosetu calls. On today's syosetu layout the title is
   `h1.p-novel__title` and the author is in `div.p-novel__author` (its `<a>` when present, without
   the `作者：` label). Check this against a saved fixture page and add fixtures to the tests.
2. The form shows the series fields with the Japanese title and author filled in.
3. **Create**: `POST /series` with the fields and `syosetu_url`, then
   `POST /series/{id}/syosetu/fetch` with `nums: [first chapter number]`. Using the existing job keeps
   heading-volume placement and stored headings the same as any other fetch.
4. The SPA shows the job's progress. When it succeeds, it opens chapter 1 in the editor. If the
   fetch fails, the series still exists, and the user lands on its page with the error and a pointer
   to Tools → Fetch from Syosetu.

**Short stories (短編).** A one-shot novel has no chapter index; its text is on the root page.
These must work: the read step recognises a root page with novel text and no index entries,
returns its Japanese title and author with "one chapter", and Create turns that page's text into
a series with a single chapter (number 1, titled from the page). The page's title element differs
from the serial chapter one (`fetch_syosetu` looks for `p-novel__title--rensai`), so the parse needs
a fixture of a short-story page. The fetch job (or a sibling path) must handle a series whose
`syosetu_url` is itself the chapter. Tools → Fetch from Syosetu then has nothing more to offer, and
should say so. The user decided this.

*(Builder's call: whether create-then-fetch is two SPA calls or one endpoint that creates and
enqueues. Two calls reuse what exists. One avoids a series with no chapter if the second call
fails. Either is fine. An empty syosetu series is harmless and recoverable.)*

### EPUB flow

Reuse `useEpubBook`, `EpubPicker`, `EpubFields` and `EpubResult` as they are. The flow:

1. Pick the EPUB. The app inspects it as today.
2. Series block (above). The Japanese title is prefilled from the book title, and the author from the
   book's author. There is no existing-series picker.
3. Volume name, metadata and chapter checklist, unchanged. The volume-name prefill uses the book
   title as it does now. With no series volumes yet, `prefillName` gets an empty list.
   The volume's **Author** metadata field defaults to the series' author romaji while the user has
   not edited it, and to the EPUB's author when romaji is blank. *(My call: readers see the
   romanised name in exported EPUBs.)*
4. **Import** creates the series with its fields and imports exactly as `POST /epub/import` does
   today. Then it shows `EpubResult` with a link to the new series.

Server side: `POST /epub/import` needs to (a) accept the three original-work fields when it creates
a series and (b) have a mode that **refuses** an existing title rather than reusing it (e.g. a
`new_series=true` form field). The Import page keeps today's find-or-create behaviour.
*(Alternative, builder's call: the SPA calls `POST /series` first, then imports with `series_id`. If
the import then fails, it must delete the empty series, or the user is left with one.)*

### Paste flow

Today's dialog with the series block in place of the single title field. **Create** calls
`POST /series` and opens the new series' page (*my call: today it stays on the Library*), where the
user adds chapters with the existing New chapter flow.

### EPUB author fallback

When a volume's `epub_author` is blank, `export_volume` uses the series' `author_romaji`. This
covers syosetu and paste series, whose volumes appear later and never pass through the EPUB form.
*(My call.)*

### EPUB attribution

When the series has an `original_title`, the exported EPUB credits it in the OPF metadata only
(`api/core/epub_build.py`), as `dc:source`. `original_author` goes in the same entry when present.
There is no visible credits line or page. The user decided this.

### TODO entry

Add to `docs/TODO.md` (newest first):

> **Syosetu: periodic background fetch.** Raised 2026-10-22 during the new-series work. New
> syosetu series fetch only their first chapter. Add a scheduled job that, for every series with a
> `syosetu_url`, reads the index and fetches chapters not yet fetched, respecting
> `syosetu_delay_seconds`, one `syosetu_fetch` job per series at a time, and the per-user job
> limits. Decide the interval, opt-out per series, and how failures surface.

## Testing

- API: the new columns round-trip through create, PATCH and GET. The novel-read endpoint parses
  title, author and first chapter from fixture pages (current layout, a page missing the
  author, and a short story) and refuses chapter URLs and non-syosetu hosts. The EPUB import in new-series mode refuses
  a duplicate title and stores the fields. The EPUB build writes the attribution when
  `original_title` is set and omits it when blank.
- SPA: vitest for any pure helpers, such as the author-metadata default.
- Playwright: one smoke flow per option. Syosetu uses a stubbed fetch, following how existing
  scrape tests avoid live syosetu. EPUB uses a small fixture EPUB. Paste uses the dialog.

## Left to the builder

Column names; dialog versus route for the chooser; the two-call or one-endpoint syosetu create; the
new-series mode on `/epub/import` versus create-then-import; layout and copy.
