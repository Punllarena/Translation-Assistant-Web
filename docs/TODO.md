# TODO

Deferred work, recorded so it can be picked up later. Newest first.

## EPUB import: always build the volume's Illustrations chapter

*Raised 2026-10-29.*

Today the picker (`web/src/library/epubRows.ts`) gathers only the image-only pages the user ticks into the
"Illustrations" chapter (`api/core/epub_runs.py`). Instead, import should create that chapter for every
volume whose book has illustrations, already marked `is_illustrations`, holding every illustration in the book.

To decide:

- Images inline in text chapters: copy them into the Illustrations chapter too (keeping the inline copy),
  or only the image-only pages? A copy doubles their bytes in `document_images`.
- Keep the picker's untick, or always include all? The cover image should stay out (it goes to `volume_covers`).
- The `epub_safety.py` per-import image budget then counts copies.

## Series page: chapter table columns and Ollama actions

*Raised 2026-10-29.* Chapter table: `web/src/library/ChapterTable.tsx` (columns today: #, Chapter, Progress,
Edited, WordPress).

- **Image count** column: number of `document_images` per chapter. Needs a count on `DocumentOut` (a
  `column_property` like `VolumeOut.cover_id`, not a per-row query).
- **Line / character count** column: lines and source characters (decide: source or translation characters,
  blank lines counted or not). Same `column_property` approach.
- **WordPress column only when WordPress is set up**: hide the column (and the WordPress tab's publish
  controls?) when the user has no `wordpress` credential. Needs a cheap "configured" flag the SPA can read
  (`/wp` settings or `/me`).
- **Ollama actions move to Tools or Settings**: "Queue for Ollama" and "Flush Ollama output" sit in the
  selection bar, the volume ⋯ menu and the chapter ⋯ menu. Add series-wide "Queue series for Ollama" and
  "Flush Ollama output" to the series' Tools tab (`SeriesTools.tsx`); `/ollama/queue` needs a `series`
  item kind if it lacks one. Decide whether the per-chapter and per-volume entries stay.
- **Deleting a chapter that has images asks what to do with them**: Delete them, or move them to the
  volume's Illustrations chapter (creating it if the volume has none; a loose chapter or a syosetu series
  has no Illustrations chapter, so only Delete applies there). Today `DELETE /documents/{id}` cascades
  `document_images`. Needs a `images=delete|move` parameter, the move appended at the end of the
  Illustrations chapter's anchors, and the same choice for multi-select delete.

## Settings: one Settings page with tabs

*Raised 2026-10-29.*

The header (`web/src/Shell.tsx`) has four separate links: Editor, Machine translation, WordPress,
Shortcuts. Replace them with one "Settings" link opening a tabbed page with those four tabs, like the
series page's `?tab=`. Keep `/settings/editor|mt|wp|shortcuts` working (redirect or route per tab) so
bookmarks survive.

## Edit Source: allow removing all the text

*Raised 2026-10-29.*

`PUT /documents/{id}/source` refuses blank text (422 "source text is empty", `api/routers/lines.py`).
Allow it, behind a confirm dialog ("Remove all of this chapter's text? Its translations go too.") in
`web/src/editor/SourcePage.tsx` using `ConfirmDialog`, not `window.confirm`. Decide what an empty chapter
holds (zero lines, or one blank line) and check the editor, progress, export, publish and Ollama work
handle a chapter with no lines. An Illustrations chapter is already text-free.

## Editor: copy source, undo across cards

*Raised 2026-10-29.* Ctrl+Z after Use and JParser's Latin runs were fixed in PR #31.

- **Copy original text button** next to the line number on each card (`LineCard.tsx`): copies the line's
  raw source to the clipboard. Decide raw text or glossary-replaced text.
- **Undo after leaving the card**: `CodeEditor` is keyed per line, so its undo history starts fresh each
  time a card opens, and Ctrl+Z cannot reach a Use or edit made before moving away and back. Options: an
  "Undo" toast after Use that restores the previous text, or keep each line's history while the chapter
  is open.
- **JParser, dictionary words inside a Latin run**: an unmatched Latin run is taken whole, so a dictionary
  entry starting mid-run is not looked up. Minor; revisit only if it shows up.

## Ollama and translation memory: skip symbol-only lines

*Raised 2026-10-29.*

Lines with no letters or kana/kanji — scene breaks like `■` or `◇◇◇`, a lone `……` — should not be sent to
Ollama and should not appear as translation memory matches or sources.

- Ollama: `rows_for` / `lines_left` / `_with_work` in `api/ollama/work.py` treat only blank lines as no-work;
  add the same rule there (the SQL in `_with_work` and the Python must agree, as `raw_sha`/`_sql_sha` already
  do). Decide whether such a line counts toward progress as done (e.g. its source copied as its translation)
  or is simply left out.
- Translation memory (`/tm/matches`, `api/routers/memory.py`): skip symbol-only lines as the query and as
  candidates.
- One shared predicate ("has a letter", Unicode-aware) in `api/core/text.py`.

## Yomitan dictionaries: deferred formats and fields

*Raised 2026-10-22 during the Yomitan dictionaries work
(`docs/superpowers/specs/2026-10-22-yomitan-dictionaries-design.md`).*

Only term dictionaries are read, flattened to a short plain-text gloss. Deferred:

- Kanji dictionaries (KANJIDIC and similar) are refused; a per-character lookup panel could use them.
- Pitch-accent dictionaries (`term_meta_bank` `pitch`) are ignored.
- Frequency dictionaries (`term_meta_bank` `freq`) are ignored; they could rank candidates.
- Full entries: the structured-content tree is flattened, so tables, images, examples and cross-references are not shown.

## Syosetu: periodic background fetch

*Raised 2026-10-22 during the new-series work
(`docs/superpowers/specs/2026-10-22-new-series-sources-design.md`).*

New syosetu series fetch only their first chapter. Add a scheduled job that, for every series with a
`syosetu_url`, reads the index and fetches chapters not yet fetched, respecting
`syosetu_delay_seconds`, one `syosetu_fetch` job per series at a time, and the per-user job
limits. Decide the interval, opt-out per series, and how failures surface.

## Syosetu: daily update check

*Raised 2026-10-25 (library filters, sort and archive).*

Once a day, check every non-archived Ongoing syosetu series for a newer chapter post date and update
`syosetu_updated_at` (the "Latest syosetu update" sort), respecting `TA_SYOSETU_DELAY_SECONDS`. Needs a
scheduler the app does not have yet; shares it with the periodic background fetch above.

## EPUB: series position metadata

*Raised 2026-10-21 during the volume naming work
(`docs/superpowers/specs/2026-10-21-volume-naming-design.md`).*

Volumes now carry a numeric `volume_index`, but the EPUB built by `api/core/epub_build.py` does
not record where a volume sits in its series, so readers cannot sort volumes of one series.

To do:

- Write `calibre:series` / `calibre:series_index` (EPUB 2 meta) from the series title and `volume_index`.
- Write EPUB 3 `belongs-to-collection` (collection type `series`) with `group-position` from `volume_index`.
- Skip both for unnumbered volumes (no `volume_index`).

## WordPress: volume-aware chapter indexing

Designed in the plugin's `docs/superpowers/specs/2026-10-28-volumes-and-chapter-navigation-design.md`
(plugin 1.6.0, Punllarena/translation-assistant-publisher#1), section "ta-web side": ta-web sends
`chapter_label`, `first_chapter_index` and the Illustrations `publish_date`, and asks
`/status?illustrations=1`.

## WordPress plugin: volume Illustrations page first

Designed in the plugin's `docs/superpowers/specs/2026-10-28-volumes-and-chapter-navigation-design.md`
(plugin 1.6.0, Punllarena/translation-assistant-publisher#1), section "ta-web side": ta-web sends
`chapter_label`, `first_chapter_index` and the Illustrations `publish_date`, and asks
`/status?illustrations=1`.

## WordPress: volume names must be unique per series

*Raised 2026-10-21 (volume naming review).*

The naming indexes keep `(kind, index)` and `(kind, subtitle)` unique, but WordPress gets
`Volume.wp_name` (`wp_volume_title`, else `wp_label(kind, index, subtitle)`), and two different
names can share it: an unkinded volume subtitled "Volume 3" and Volume 3 both send
"Volume 3". The plugin keys the TOC heading and the illustrations page on that string, so
publishing both would merge them on the site.

Not blocked today. Option: refuse (409) a create or PATCH whose `wp_label` collides with
another volume's `wp_name` in the same series, and report collisions left by the migration.
