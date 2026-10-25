# Series WordPress tab and series summary — design

*2026-10-25. Decided with the user in chat; calls marked "builder's call" or "my call" were not theirs.*

## Why

On the desktop, a series' **chapter 0** was its summary: the ta-publisher plugin shows chapter
index 0 as the text of the series' table-of-contents page (`build_payload` in `api/core/wp.py`
already treats `series_order == 0` that way: no attribution footer, no first line, no images, no
cover). The web port lost this:

- `arrange()` renumbers every non-syosetu series 1..N, so an imported chapter 0 became an
  ordinary loose chapter (series 47's "Summary", doc 8011, sits at `series_order` 41 and shows as
  "1" under *No volume*, while its `wp_chapter_index` is still 0).
- Re-publishing it today sends `chapter_index` = its display number, creating a stray chapter on
  WordPress instead of updating the ToC text. This is a live bug.

The user also wants the series' WordPress fields out of Settings into their own tab, and both tabs
redesigned: today every field is a bare inline label with no grouping (see the Settings tab).

## Goals

1. A **WordPress** tab on the series page holding the existing WordPress fields and a new
   **Series summary** text field for the ToC page.
2. The summary is stored on the series, not as a chapter.
3. **No new interaction** to publish it: saving the summary only marks it pending; it goes to
   WordPress, as chapter index 0, together with the next chapter of that series that is
   published.
4. Existing published chapter-0 documents become the series summary, and those documents are
   **removed** (user's decision).
5. Settings and WordPress tabs get clear visual separation between groups.

## Non-goals

- No "Publish summary" button, no separate summary job, no rich-text editor (plain textarea).
- No change to the plugin or to how chapter 0 is rendered on WordPress.
- Unpublished `series_order = 0` documents (local DB has "Index" s43, "Eromobuseka Synopsis" s44,
  "Xray 17" s48, "AV 1" s42) are left alone; the user pastes summaries by hand where wanted.
- Not touching the TOC ordering items in `docs/TODO.md`.

## Anti-goals

- A chapter publish must never fail, or be reported as failed, because the summary failed.
- The summary must never be sent as an ordinary numbered chapter, and an ordinary chapter must
  never be sent as index 0 by accident.
- Never re-send an unchanged summary on every chapter publish.

## Data

New `series` columns (autogenerate the migration; builder's call on exact names):

| column | type | meaning |
|---|---|---|
| `wp_summary` | Text, not null, default `""` | plain text; paragraphs separated by blank lines |
| `wp_summary_pending` | Boolean, not null, default false | changed since last successful send |
| `wp_summary_error` | Text, not null, default `""` | last send failure message, cleared on success |

`SeriesOut` exposes all three; `SeriesUpdate` accepts `wp_summary` only. A PATCH that changes
`wp_summary` sets `wp_summary_pending = (new text is not blank)` and clears `wp_summary_error`.
Reject NUL (422, `reject_nul`). Length cap: builder's call (e.g. 100 000 chars, 422 over it).

## Sending the summary

A helper in `api/publish.py` (or a small new module if publish.py would pass ~400 lines), e.g.
`send_summary(db, client, series, endpoint, key, prefs)`:

- Skip unless `series.wp_summary_pending` and `wp_summary.strip()`.
- Build the payload with `wp.build_payload`, `series_order` 0, `chapter_title` "Summary" (the
  desktop doc's title; `build_payload` prefixes the short title), lines from splitting the text on
  blank lines into `{"prefix": "%"…}`-style paragraph rows that `build_chapter_body` renders one
  `<p>` each (single newlines inside a paragraph join with a space, as `$` continuation lines do).
  No password, no unlock index, no schedule date, no volume title, no images or cover.
- On success (`created` or `updated`, or the plugin's "already there" answer — treat any non-error
  response as sent): `pending = False`, `error = ""`.
- On `WPPublishError` or any exception: keep `pending = True`, store a short message in
  `wp_summary_error` (plugin message only, same rule as chapter errors), log it, and **carry on**
  with the chapter.

Called **before** the chapter is sent, with the same HTTP client, from:

- `POST /documents/{id}/wp/publish` (single publish), after the re-publish 409 check passes;
- the `wp_publish` batch job, once per series (before that series' first chapter in the batch);
- the `wp_illustrations` job, before the upload.

The summary's state is written in the same transaction as the chapter result (route commit
boundary / job progress commit); no extra commit points. *My call:* when the chapter request then
fails (single publish 502, illustrations `JobError`), the rollback leaves the summary pending and
drops its error; it is simply sent again next time. Re-sending an unchanged summary overwrites the
same index-0 post, so this is harmless.

*My call:* blanking the summary never sends anything. The tab then says "Not set — WordPress keeps
the last summary it received".

## Guard against chapter 0 as a chapter

`build_chapter` refuses (NotReady → 422 in the single route, per-row error in the batch) a
document whose display number would be 0 or whose `wp_chapter_index` is 0, with a message
pointing to the series' WordPress tab ("The series summary now lives on the series' WordPress tab").
`refresh_status` is unaffected.

## Migration of existing summaries

In the same Alembic migration (data step after the column adds; builder's call to split it into a
second revision): for each series, if any document has `wp_chapter_index = 0` and a live
`wp_status` (`publish`/`future`):

- `wp_summary` = that document's translated lines joined as paragraphs (skip `$`-continuation
  joins the same way `build_chapter_body` does; blank translations dropped), `wp_summary_pending =
  false` (it is already on WordPress).
- Delete that document (its lines/images cascade as for a normal delete) and re-run the series'
  numbering so the rest stay 1..N. In SQL inside the migration the renumber is: re-number the
  remaining non-syosetu documents' `series_order` by their current order. Builder's call how.
- If a series has more than one such document, use the lowest id and delete all of them; log it.
- *My call:* a document with `wp_chapter_index = 0` whose `wp_status` is **not** live (never sent,
  or WordPress reported it gone) is not a summary on the site: clear its `wp_chapter_index` to NULL
  so it publishes as an ordinary chapter (otherwise `previous_chapter_index` 0 would move the ToC
  post).
- *My call:* after renumbering, log (migration output) every live chapter whose new display
  number differs from its `wp_chapter_index`. No automatic fix. A loose summary sits last in its
  series, so in practice nothing shifts (true for series 47).

Downgrade drops the columns (the deleted documents are not restored; say so in the docstring).

## ta.db importer

A desktop document with `series_order = 0` and `wp_chapter_index = 0` and a live `wp_status` is
imported as that series' `wp_summary` (pending false) instead of as a chapter. The dry-run
report counts it ("1 summary"). Other `series_order = 0` documents import as before. Lives in
`api/core/tadb_rows.py` or a small helper next to it.

## SPA

Series page tabs: Volumes · Glossary · Tools · Settings · **WordPress** (`?tab=wordpress`).

**WordPress tab** (`SeriesWp.tsx`, moved out of `SeriesSettings.tsx`), two card sections:

1. **Publishing** — Series slug, Short title, Password protection, Keep N chapters locked; one
   *Save* button; *Open TOC page* link when the endpoint and slug exist. If the user has no
   WordPress credential, a one-line note linking to Settings → WordPress.
2. **Series summary (ToC page)** — a textarea (several rows, grows), *Save summary*, and a status
   line: "Not set" / "Waiting — goes out with the next chapter you publish" / "On WordPress" /
   the stored error (error style) with "will retry with the next chapter".

**Settings tab** gets the same card treatment: *Details* (title, Japanese title, author, author
romaji, series URL), *Volume titles* (template, hint, preview), *Export* (the two Markdown ZIP
links), then the existing *Danger zone*.

Styling: a reusable section/card style in `web/src/styles/` using tokens only (Phase 7a rule):
card background/border, a heading per card, labels stacked above inputs on their own rows with a
consistent width, hints under the field. Builder's call on exact layout; it must read clearly in
light and dark themes and at narrow widths. Run `npm run gen:api` after the API change.

## Tests

- PATCH sets/clears pending and error; NUL and length 422.
- Single publish with a pending summary sends two requests (summary index 0 first, then the
  chapter) and clears pending; a failing summary request still publishes the chapter and stores
  the error; no pending → one request.
- Batch with two chapters of one series sends the summary once.
- Illustrations job sends a pending summary first.
- Guard: a document with display number 0 or `wp_chapter_index` 0 is refused.
- Migration: covered by a test that builds the pre-state, runs the data step's function, and checks
  summary text, deletion and renumbering (builder's call how to test the migration logic; putting
  the transform in a plain function the migration calls makes this easy).
- Importer: a desktop chapter 0 becomes the summary.
- Playwright: the WordPress tab shows the fields and saves a summary (extend an existing spec's
  seed per E2E conventions).

## Docs

Update `CLAUDE.md` with a short paragraph (summary on the series, pending until the next chapter
publish, chapter 0 guard, the tab).
