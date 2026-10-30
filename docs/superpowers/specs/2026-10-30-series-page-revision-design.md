# Series page revision: chapter table, WordPress tags, Gallery tab, account-saved views

*2026-10-30. Agreed in conversation with the user; items marked "builder's call" or "Claude's call" were not
decided by the user.*

## Why

The series page (`/series/:id`, `web/src/library/SeriesPage.tsx`) is where the user checks progress, publishes
batches and tidies volumes, and today it gets in the way:

- Ticking several chapters is fiddly: the title link's `::after` covers the whole row
  (`.ch-title .row-link::after { inset: 0 }`, `web/src/styles/library.css`), so any click that misses the
  checkbox opens the editor.
- A long chapter title pushes the table past the screen's edge.
- The WordPress tag shows `documents.wp_status` as stored at publish time. It is only refreshed when the
  single-chapter Publish dialog calls `POST /documents/{id}/wp/status`, so a chapter WordPress has since posted
  still says "Scheduled". The date sits in a hover tooltip only (`wpBadge`, `web/src/publish/badge.ts`).
- A scheduled chapter's publish path asks "Publish anyway?"; for a scheduled chapter that should be
  "Reschedule".
- The user cannot see a series' images without opening each chapter in the editor.
- The table's columns are fixed; the user wants to choose them, and wants that choice (and the Library's
  view, sort and filters) to follow the account across devices.

It also takes in the series-page items from `docs/TODO.md` § "Series page: chapter table columns and Ollama
actions", which this work removes from the TODO when done.

## Goals

1. Selecting chapters is easy and never opens the editor by accident.
2. The table fits the screen whatever the title length.
3. The user picks which columns show; the choice is saved on the account.
4. WordPress tags never claim a state the site has left, and each can be opened for its detail and actions.
5. A Gallery tab shows, and lets the user manage, every image in the series.
6. Ollama's series-wide actions live in Tools; the selection bar is less crowded.
7. Deleting a chapter with images asks what happens to them.
8. Library view, sort and filters are saved on the account too.

## Non-goals

- Page-load checking of every chapter's WordPress status. It needs a series-wide status route in the plugin;
  that is deferred to a plugin TODO (below). This work only uses the existing per-chapter route.
- Sorting the chapter table by a column. Chapter order is the reading order; it stays the only order.
- Syosetu background fetch / daily check, the Settings page tabs, editor and Ollama-symbol items, Yomitan,
  EPUB metadata — other TODO sections, untouched.
- Thumbnails as stored images (see Gallery: builder's call).

## Anti-goals

- A click in select mode that opens the editor.
- A tag that says "Scheduled" for a chapter whose scheduled time has passed, with nothing hinting it may be live.
- A "Publish again" / "Publish anyway" offer on a scheduled chapter.
- Losing a user's current Library view, sort or filters when they move to the account.
- Firing a WordPress request per chapter on page load.

## 1. Chapter table (`web/src/library/ChapterTable.tsx`)

### Select mode

- The table has a **Select** toggle button (top right of the table, next to Columns ▾). Ticking any row's
  checkbox also turns select mode on. Leaving it: the toggle, the selection bar's Clear, or Esc; leaving
  clears the ticks.
- In select mode a click anywhere on a row toggles that row; shift-click toggles the range from the last
  clicked row (reuse `rangeToggle.ts`). The title is not a link (render it as text, no stretched `::after`),
  drag handles are hidden, and the row ⋯ menu stays usable (it does not toggle the row).
- Outside select mode the row behaves as today (the whole row opens the editor) and the checkbox stays as the
  way in.
- Quick picks in the selection bar's "Select ▾": All (in this volume, across closed blocks too), None,
  Untranslated (progress < 100), Not posted (`wp_status` empty).

### Selection bar

- It no longer replaces the header row (the header stays visible and the layout does not jump). It sits
  above the table and sticks to the top of the viewport while scrolling.
- Contents, in order: "N selected", Select ▾, **Publish…**, **Check status** (WordPress, see §2), Export ▾,
  Move to…, Merge, Delete, then Clear at the end. **Queue for Ollama** and **Flush Ollama output** are removed
  from it.
- Publish… and Check status are hidden when WordPress is not set up (§2).

### Layout

- The table uses fixed layout and never exceeds its container's width. The Chapter column takes the leftover
  width; its title is one line with an ellipsis, the full title in a `title` tooltip. Other columns size to
  their content's typical width.
- On narrow screens no horizontal page scroll; if the chosen columns cannot fit, the table's own wrapper
  scrolls sideways (builder's call on the breakpoint behaviour), never the page.
- The header row sticks while scrolling (below the selection bar when that shows).
- Above the table, a one-line summary of the selected volume: "42 chapters · 68% translated · 30 posted ·
  5 scheduled (next: Nov 2, 18:00)". The WordPress parts are hidden when WordPress is not set up; counts come
  from the cached `wp_status` (the Published? state of §2 counts as posted).
- Progress shows as a thin bar plus the percent.

### Columns

A **Columns ▾** menu lists every column with a checkbox. # and Chapter cannot be hidden; the select, grip and
⋯ columns are not listed. Defaults (Claude's call): the current five — #, Chapter, Progress, Edited,
WordPress.

| Column | Shows | Source |
|---|---|---|
| # | chapter number | existing |
| Chapter | translated title, else source title | existing |
| Progress | bar + % | existing |
| Edited | `updated_at` date | existing |
| WordPress | status tag (§2) | existing; hidden when WP not set up |
| Original title | `documents.title` when `chapter_title` is set and differs from it, else blank — the same rule as the Rename dialog's "Original title" note (`ChapterMenu.tsx`); there is no separate source-title field and none is added (Claude's call) | existing field |
| Images | `image_count` | already on `DocumentListItem` |
| Lines | non-blank source lines (`line_count`) | already on `DocumentListItem` |
| Translated | "120 / 340" (`translated_count` / `line_count`) | already on `DocumentListItem` |
| Characters | source characters, not counting whitespace | **new** on `DocumentListItem` |
| Words (EN) | words in the translated text | **new** on `DocumentListItem` |
| WP date | `wp_published_at` (posted or scheduled time), local date and time | existing field; hidden when WP not set up |
| Ollama | "N waiting" = live suggestions (`ollama_suggestions` with text not NULL, not used/dismissed — builder confirms the exact "waiting" predicate from `api/ollama/store.py`), "Queued" when the chapter is in an `ollama_queue_items` entry, else blank | **new** count on `DocumentListItem`; queued state from `GET /ollama/queue` client-side |
| Source | "syosetu" link when `source_url` is set, else blank | existing field |
| Added | `created_at` date | existing field |

The counts are added to the existing aggregated query in `list_documents` (`api/routers/documents.py`, the
`lines` and `images` subqueries), not per-row queries. Characters: sum of the length of `raw_text` with
whitespace removed, over non-blank lines. Words: count of whitespace-separated tokens in `translated_text`
(builder's call on the SQL, e.g. `array_length(regexp_split_to_array(trim(...), '\s+'), 1)`). Regenerate
`schema.d.ts`.

A hidden column is not rendered; the chosen set is the user setting `series_columns` (§5).

### Ollama actions

- The series' Tools tab (`SeriesTools.tsx`) gets an **Ollama** section with **Queue series for Ollama**
  (`POST /ollama/queue` with `kind: "series"`, which the API already supports) and **Flush Ollama output…**
  (`POST /ollama/flush` with `series_id`, behind the same `ConfirmDialog` wording as today). Reuse
  `useQueueOllama` / `useFlushOllama`.
- The chapter ⋯ menu and the volume ⋯ menu keep their Queue and Flush entries (the volume menu's was Claude's
  assumption, not contradicted by the user).

### Deleting a chapter that has images

- `DELETE /documents/{id}` takes `images=delete|move` (default `delete`, so today's callers keep working).
  `move` appends the chapter's `document_images` to the end of its volume's Illustrations chapter, after the
  existing images' highest `anchor_position` (the same rule as `api/illustrations.py`'s fold), creating the
  Illustrations chapter when the volume has none (`add_images` already creates one; reuse its rules). `move` on
  a chapter with no volume, in a syosetu series, or that is itself the Illustrations chapter is 409 with a
  message (rules and messages live in `api/illustrations.py`).
- A moved image never disappears: where `add_images` / `merge_into` skip an image whose `src_path` the
  Illustrations chapter already holds, a move instead renames it with a numeric suffix (`img.jpg` →
  `img-2.jpg`) and moves it (Claude's call). The same applies to the Gallery's Move to Illustrations.
- The SPA: deleting a chapter whose `image_count > 0` shows a dialog with "Delete N images too" or "Move them
  to this volume's Illustrations chapter" (the second absent when not allowed), then Delete. Multi-select
  delete asks once when any selected chapter has images; `move` applies to the ones that can move, and the
  dialog says how many cannot and will lose their images (builder's call on the exact wording). A
  multi-select delete stays one request per chapter, as today.
- The Illustrations chapter itself, being deleted, is plain Delete (its images go).

## 2. WordPress tags

"WordPress set up" means the user has a `wordpress` credential. The SPA needs a cheap flag for it; reuse what
the credentials or `/wp` settings endpoints return if one already says so, else add a boolean to an existing
response (builder's call which). When not set up: no WordPress column, no WP date column, no Publish… or
Check status in the selection bar, no Publish… in the chapter ⋯ menu, no WordPress tab on the series page.

### Tag states

| Stored `wp_status` | Condition | Tag |
|---|---|---|
| `publish` | — | Published |
| `future` | `wp_scheduled_for` (else `wp_published_at`) in the future | Scheduled |
| `future` | that time has passed | **Published?** (muted tone) |
| empty / other | — | Not posted |

### Clicking a tag

The tag is a button. It opens a small popover anchored to it that immediately calls
`POST /documents/{id}/wp/status` (the existing live check) and shows: the live status, the post link,
"checked just now" (or the remote error), and the posted or scheduled date and time (local) **as ta-web
stored it at publish** (`wp_scheduled_for`, else `wp_published_at`), labelled as such — the plugin's `/status`
returns no date, so a live date joins the plugin TODO below (Claude's call). When the live status is
`publish` and the stored one was `future`, the date line reads "scheduled for <date>, now live". The row's tag
updates from the result (invalidate the library query). Actions in the popover:

- Scheduled: **Reschedule…** — opens the single-chapter publish flow with the schedule field shown and
  prefilled, titled "Reschedule", that sends `confirm_republish: true` itself (the user already chose to
  reschedule; no second "Publish anyway?" confirm). Builder checks that re-sending a scheduled chapter with a
  new `scheduled_date` moves the post's date in the plugin; if it does not, stop and raise it.
- Published: **Update post…** — the existing publish flow (its overwrite note stays).
- Not posted: **Publish…**.
- An Illustrations chapter never offers Reschedule (its single publish, `POST /documents/{id}/wp/illustrations`,
  has no date; only batch publish schedules it). Scheduled → Update post… through the existing
  `IllustrationsPublish` (Claude's call; no API change).

The chapter ⋯ menu's Publish… item follows the same naming: Reschedule… for a scheduled chapter, Update
post… for a published one. `PublishDialog`'s `window.confirm` for the republish 409 is replaced by
`ConfirmDialog` while here.

### Check status (selection bar)

Checks the ticked chapters one at a time through the same route, at most 50 per click (more selected: it
checks the first 50 and says so), showing "Checking 12 / 50…" and a Stop button; the table updates as each
returns. Client-side loop, no job.

### Plugin TODO

Add to `docs/TODO.md` a section "WordPress plugin: series-wide status route": one request returning the
status, post URL and date of every chapter (and illustrations page) of a series, so the series page can check
on load instead of per chapter. It should also return each post's live date (today's per-chapter `/status`
returns none). Note what ta-web then changes (page-load check, live dates, drop the 50 cap).

## 3. Gallery tab

A new tab, `?tab=gallery`, between Volumes and Glossary.

- Shows every `document_images` row of the series' chapters plus each volume's cover. Grouped by volume (in
  `volume_order`, "No volume" last), within a volume the cover first, then chapters in order, then each
  chapter's images by `anchor_position`. A small heading per chapter ("Ch. 3 · Title"). A volume filter at the
  top (All / one volume).
- Needs one listing route, e.g. `GET /series/{id}/images` (id, document id, anchor position, src name,
  `exclude_export`; never the bytes), scoped through the series. Images load from the existing
  `GET /images/{id}` and `GET /covers/{id}` with `loading="lazy"`, shown as fixed-size tiles (`object-fit:
  cover`). Builder's call whether a resized-thumbnail route is needed for large books; if added it must not
  store derived images.
- Clicking a tile opens a full-size viewer (native `<dialog>` with `showModal()`, previous/next, Esc closes)
  with these actions — no "open in editor":
  - **Set as volume cover**: copies the image's bytes into the chapter's volume's cover (a new
    `volume_covers` row, as `PUT /volumes/{id}/cover` does). Absent for a loose chapter's image.
  - **Move to Illustrations**: moves the image to the end of its volume's Illustrations chapter (creating it,
    same rules and 409s as delete-with-move). Absent when not allowed or when already in that chapter.
  - **Delete**: removes the image, behind `ConfirmDialog`. Deleting an image removes its anchor from the
    chapter; builder checks what the editor shows for a line whose image is gone and that export copes.
  - **An Illustrations chapter left with no images is deleted** (user's choice), by a Gallery Delete or
    Move, in the same request; `arrange()` then runs as for any chapter delete. Its WordPress illustrations
    page, if published, is left on the site untouched. The confirm dialog says so when the action will
    empty it ("This is the last image; the Illustrations chapter will be deleted too.").
  - For a cover tile: no actions beyond viewing (covers are managed in the volume's details).
- New routes for these (builder's call on shape, e.g. `POST /images/{id}/cover`, `POST /images/{id}/move`,
  `DELETE /images/{id}`), each scoped by `scoped_image`, id-addressed (404 for other users' ids).

## 4. Library and other prefs

Nothing changes in the Library's behaviour here, only where its prefs live (§5).

`PUT /settings` today validates only the Ollama schedule key; the four keys below get their own validation
(422 on a malformed value).

## 5. Account-saved views

New user settings (per-user key/value, `/settings`), validated server-side as other settings are:

- `series_columns`: list of column ids, unknown ids dropped; missing = the defaults.
- `library_view`: `shelf` / `list` (today `ta.libraryView`).
- `library_sort`: `{key, dir}` (today `ta.librarySort`).
- `library_filters`: the `LibraryFilters` shape (today `ta.libraryFilters`).

They follow the `ui_theme` pattern (`web/src/theme/`): `localStorage` keeps a copy so the page paints before
`/settings` arrives, the account's value wins once it does, and every change writes both. The readers in
`libraryPrefs.ts` / `viewPref.ts` keep their validation and are reused to validate the account's values.

**Migration of existing prefs:** on the first `/settings` load where the account has no value for one of
these keys but this browser has a `localStorage` value, the SPA writes the browser's value up to the account.
(First browser to load wins; others then take the account's value.)

## 6. Docs

- `docs/TODO.md`: remove the "Series page: chapter table columns and Ollama actions" section; add the plugin
  status-route section (§2).
- `CLAUDE.md`: a short paragraph for the series page revision (select mode, columns setting, tag states,
  Gallery tab, `images=` delete parameter, the four new settings), pointing at this spec.

## Testing

- Pytest: the new `DocumentListItem` counts (characters, words, Ollama waiting); `DELETE ?images=move` (appends
  after the last anchor, creates the Illustrations chapter, 409 cases, default unchanged); the gallery listing
  and image actions (tenancy 404s, cover copy, move, delete); settings validation for the four keys.
- Vitest (pure modules): tag state rule (incl. Published?), column-set validation, summary line counts,
  select-mode range toggling.
- Playwright: one spec with its own seeded series — select mode never opens the editor on row click; long
  title does not overflow at 1280 px and 375 px; Columns menu hides/shows and survives a reload; Gallery shows
  images and Delete removes one.

## Left to the builder

- Exact visual styling within the token system (`web/src/styles/tokens.css`).
- The WordPress-configured flag's location.
- SQL for character and word counts.
- Gallery route shapes and whether a thumbnail route is needed.
- How the selection bar, sticky header and summary stack on narrow screens.
- Splitting the work into PRs (suggested: table + WordPress + Ollama + delete; Gallery; account-saved prefs).
