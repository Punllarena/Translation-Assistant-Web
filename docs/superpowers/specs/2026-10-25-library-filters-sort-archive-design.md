# Library filters, sort, archive and series status

## Intent

The Library (`/`) lists every series sorted by title, with a title search as the only way to narrow it. As
the shelf grows, the user wants to see the series that matter right now: the syosetu ones still being
translated, the ones with fresh syosetu chapters, the ones already on WordPress. Finished or abandoned series
should be able to leave the shelf without being deleted.

## Goals

- **Archive / Unarchive** a series from its Settings tab's Danger zone. Archived series are hidden from the
  Library by default.
- A per-series **status** the user sets by hand.
- A record of where a series came from (**source**).
- The date syosetu last posted a chapter (**latest syosetu update**).
- On the Library: a **Sort** dropdown and a **Filters** popover with removable chips (mockup option A).

## Non-goals

- **Grouping.** The user dropped it; filters cover the need.
- **A daily background syosetu check.** The user wants it, but the app has no scheduler. It goes into
  `docs/TODO.md` (see "Deferred"). For now the syosetu date only refreshes when the app reads a chapter list.
- Filters the user turned down: new chapters available on syosetu, untranslated lines left, WordPress summary
  pending.
- Filter and sort choices that follow the account to other devices.

## Anti-goals

- Archiving must never lose or change data. Unarchive puts the series back exactly as it was.
- Archived series must not linger on the Library under the default filter.
- No filtering or sorting on the server. The Library already loads every series, document and volume, so this
  stays a client-side view over those lists.

## Decided by the user

### Archive

- The Danger zone (`web/src/library/SeriesSettings.tsx`) gets an **Archive series** button beside **Delete
  series**. It asks for confirmation through `ConfirmDialog`, the same way Delete does, but not as a
  destructive action: archiving can be undone.
- The Delete confirmation suggests archiving instead: a line in the message plus an **Archive instead** action
  that closes Delete and opens the Archive confirmation, or archives directly (builder's call; see "Left to the
  builder").
- An archived series shows **Unarchive series** in that spot. Unarchiving needs no confirmation and only puts
  the series back on the Library.
- Archiving hides the series from the Library. The Archived filter can bring it back into view.

### Status

- The user sets it on each series. The values are **Ongoing**, **On hold**, **Dropped** and **Completed**
  (`ongoing`, `on_hold`, `dropped`, `completed`).
- It is edited in the series Settings tab and can be filtered on in the Library.

### Filters (in the Filters popover; the ones in use appear as chips)

| Filter    | Choices                                  | Default |
|-----------|------------------------------------------|---------|
| Source    | Syosetu, EPUB, Other (tick any)          | none ticked = all |
| Status    | Ongoing, On hold, Dropped, Completed (tick any) | none ticked = all |
| WordPress | Any, Has published, None published       | Any |
| Archived  | Hide, Include, Only archived             | Hide |

- Different groups combine with AND; ticks inside one group combine with OR.
- "Has published" means at least one of the series' chapters has `wp_status == "publish"`. Because the client
  already loads the chapter list, this is computed client-side.
- Each chip has an ✕ that clears its group. **Clear all** resets every group to its default, Archived back to
  Hide.
- The bar shows "N of M series", where M counts every series, archived ones included.
- The title search stays and combines with the filters (AND).

### Sort (a dropdown beside the search box)

| Sort                   | Key                                                              | Default direction |
|------------------------|------------------------------------------------------------------|-------------------|
| Last modified          | newest `documents.updated_at` in the series (the card's `editedAt`) | newest first |
| Latest syosetu update  | `series.syosetu_updated_at` (below)                              | newest first |
| Latest added           | newest `documents.created_at` in the series (when chapters last landed) | newest first |
| Title                  | `series.title`, the existing collator                            | A–Z |
| Progress               | the card's `progress` %                                          | highest first |
| Last published         | newest `documents.wp_published_at` in the series                 | newest first |
| Chapter count          | the card's `chapterCount`                                        | most first |

- A ↑↓ button next to the dropdown flips the direction.
- Series with no value for the chosen key go last in either direction: an EPUB series under syosetu update, or
  a never-published series under last published. Ties break by title.
- The default sort is **Last modified, newest first**. (My call; today's order is Title.)

### Layout

Mockup option A: the PageHeader actions hold, in order, search, Sort dropdown + direction button, a
**Filters (n)** button (n = groups not at their default), then the Bookshelf/List toggle, then Import and New
series. Under the header, a row holds the chips, **Clear all** (only when a filter is in use), and the "N of M
series" count. The Filters button opens a popover holding the four groups. Bookshelf and List both show the
same filtered, sorted cards.

### Persistence

Sort, direction and filters are kept in `localStorage` (`ta.librarySort`, `ta.libraryFilters`), next to
`ta.libraryView`, with a helper like `web/src/library/viewPref.ts` that falls back to the defaults on missing
or invalid JSON. They are per browser, not per account.

## Data model (`api/models/content.py`, `Series`)

All three columns are new, added in one autogenerated migration.

- `archived_at: DateTime(timezone=True) | None`. NULL means not archived. A timestamp rather than a boolean
  costs nothing and records when the series was archived.
- `status: Text, NOT NULL, server_default 'ongoing'`, with a CHECK constraint on the four values. Existing rows
  become `ongoing`.
- `source: Text, NOT NULL, server_default 'other'`, with a CHECK on `syosetu`, `epub` and `other`. The
  migration sets `syosetu` wherever `syosetu_url <> ''`. Everything else stays `other`, because nothing records
  which old series came from an EPUB.
- `syosetu_updated_at: DateTime(timezone=True) | None`: the newest chapter post date syosetu showed at the
  last chapter-list read. NULL means never read, or not a syosetu series.

`SeriesOut` gains all four. `SeriesCreate` / the PATCH schema accept `status` and `source`. `archived_at` is
set through the endpoints below, not through a PATCH.

### Setting `source` at creation

| Path | Source |
|------|--------|
| `POST /series` with a non-empty `syosetu_url` (the New → Syosetu flow) | `syosetu` |
| `POST /series` without one (New → Paste) | `other` |
| `/epub/import` creating a series (`api/routers/epub.py`) | `epub` |
| ta.db import (`api/core/tadb_rows.py`, `tadb_glossary.py`) | `syosetu` when the desktop profile has a syosetu URL, else `other` |
| Batch TXT import creating a series (`api/routers/transfer.py`) | `other` |

When a PATCH sets `syosetu_url` on an `other` series, its source does not change on its own. The user can
change source in Settings (a select: Syosetu / EPUB / Other).

### Endpoints (`api/routers/series.py`)

- `POST /series/{id}/archive` sets `archived_at = now()` and returns `SeriesOut`. It is idempotent: an already
  archived series keeps its first timestamp.
- `POST /series/{id}/unarchive` clears it and returns `SeriesOut`. It is idempotent too.
- Both go through `scoped()` (404 for another user's series), and both are built with `api_router()`.
- `GET /series` keeps returning archived series. The client filters them.

### Syosetu update date (`api/core/scrape.py`)

- `_extract_chapters` also reads each chapter row's post date. On syosetu's current index layout that is the
  `div.p-eplist__update` text in the row's `div.p-eplist__sublist`, a `YYYY/MM/DD HH:MM` in JST, sometimes
  followed by a revision (改稿) marker. Take the post date and ignore the revision date. Store it on the chapter
  dict as `posted_at` (an aware datetime in Asia/Tokyo, or None when missing or unparseable).
- `fetch_series_index` returns the chapters as today (each with `posted_at`). Callers take
  `max(posted_at)`.
- Every chapter-list read writes `series.syosetu_updated_at` when it gets a non-None max:
  - the fetch job (`api/fetch_job.py`, after `fetch_series_index`)
  - `_read_index` in `api/routers/scrape.py`, shared by `GET /series/{id}/syosetu/chapters` (the Syosetu fetch
    dialog), the volume-headings preview and the apply
- **This deliberately bends the "chapter-list GET reads only" rule** (user's decision): the date records a fact
  about syosetu, not the user's work, and refreshing it whenever the list is viewed keeps the sort current until
  the daily check exists. Only `syosetu_updated_at` may be written by the GET and the preview; `syosetu_headings`
  and everything else stay untouched there. Update the `list_chapters` docstring and the CLAUDE.md sentence to
  say so. `SyosetuFetch.tsx` and `HeadingVolumes.tsx` invalidate the `series` query after a read, so the
  Library's sort isn't stale. Tests cover the GET writing the date and leaving `syosetu_headings` alone.
- A short story (no index, `_short_story`) has no dates. It leaves `syosetu_updated_at` untouched.
- Test fixtures need index HTML that carries the update element. Copy the structure from a real index page,
  but never commit real chapter titles or text: invent placeholders.

## SPA

- `web/src/library/shelf.ts`: `SeriesCard` gains `addedAt` (newest `created_at`) and `publishedAt` (newest
  `wp_published_at`) beside `editedAt`, plus `hasPublished`. `seriesCards` stops filtering and sorting. That
  moves into pure functions, `filterCards(cards, filters, search)` and `sortCards(cards, sort, dir)`, in a new
  `web/src/library/libraryQuery.ts` with vitest tests. Those cover every sort key, nulls-last in both
  directions, AND/OR filter combination, and the archived default.
- `Library.tsx` wires the bar. A new `LibraryFilters.tsx` holds the popover and chips. Styles use tokens in
  `web/src/styles/`.
- When nothing matches: today's "No series match" message, widened to cover filters, with a Clear all button.
  When every series is archived and the filter is Hide, the message says so and offers "Show archived".
- `SeriesSettings.tsx`: Status and Source selects saved with the existing Save, plus the Danger zone changes
  above. After archive or unarchive, invalidate the library queries (`invalidateLibrary`).
- An archived series still opens at `/series/:id` and stays fully editable. *My call:* its page shows a
  small "Archived" note near the title with an Unarchive link, so the state isn't hidden in the Settings tab.
- Run `npm run gen:api` after the schema changes.

## Elsewhere

- *My call:* archiving affects only the Library. Series pickers (Move-to, New chapter's series choice, batch
  import), statistics and publishing still list and accept archived series.
- `docs/TODO.md` gets the deferred daily syosetu check.
- CLAUDE.md gets a short paragraph on archive, status, source, `syosetu_updated_at` and the Library query
  helpers.
- E2E: one Playwright spec, with its own seeded series in `tools/e2e_seed.py`. It archives a series, sees it
  leave the Library, finds it with Archived → Include, and unarchives it. It also applies a status filter and
  a sort.

## Deferred

- **Daily syosetu check job:** once a day, read the chapter list of every non-archived Ongoing syosetu series,
  respecting `TA_SYOSETU_DELAY_SECONDS`, and update `syosetu_updated_at`. It needs a scheduler, which the app
  doesn't have yet.

## Left to the builder

- Exact wording of the confirmations and messages. Archive's confirmation names the series and says it can be
  brought back with Unarchive.
- Whether Delete's "Archive instead" opens the Archive confirmation or archives at once.
- How the popover is built (a native `<dialog>` or `popover` element, or a positioned panel), as long as
  keyboard and Escape work and it isn't covered by the shelf.
- How the Settings selects are laid out.
