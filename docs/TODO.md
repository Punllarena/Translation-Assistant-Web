# TODO

Deferred work, recorded so it can be picked up later. Newest first.

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

*Raised 2026-10-20 during the library redesign
(`docs/superpowers/specs/2026-10-20-library-redesign-design.md`).*

The library redesign numbers chapters **per volume** (Volume 1 Chapter 1…x, then Volume 2
Chapter 1…) and keeps each volume a contiguous run of `series_order`. Moving a chapter between
volumes renumbers `series_order`. Publishing reads the series-wide `chapter_number`
(`chapter_number` / `chapter_numbers` in `api/library.py`): `series_order` less the Illustrations
chapters before it, so the Illustrations chapter never takes a number. It is still series-wide, not
per volume:

- `api/publish.py:98`: `build_chapter` takes `chapter_number(db, doc)` as the chapter's WordPress
  number (`doc_meta["series_order"]`) and computes the password / unlock-after window from it
- `api/publish.py:181`: the confirm dialog's "previous chapter" is `previous_chapter` in
  `api/library.py`, the nearest earlier chapter that is not an Illustrations chapter

To do:

- Decide what WordPress should receive for a series with volumes. The target order is:
  Volume 1 Illustrations → Volume 1 Chapter 1 … Volume 1 Chapter x →
  Volume 2 Illustrations → Volume 2 Chapter 1 … Volume 2 Chapter x, and so on.
- Make the previous/next chapter links follow that order, including the illustrations page first
  in each volume (the unlock chain already skips it).
- Chapters already published before a renumber will carry their old index on WordPress. Decide
  how a re-publish reconciles them (and whether the re-publish 409 safeguard should flag a
  changed index).
- Series without volumes and syosetu series keep their own indexing (syosetu's chapter numbers).

## WordPress plugin: volume Illustrations page first

*Raised 2026-10-24 (`docs/superpowers/specs/2026-10-24-volume-illustrations-chapter-design.md`).*

- Title the illustrations page **"Volume X Illustrations"**, built from the `volume_title` it is sent.
- List it **first** in the volume's table of contents, ahead of chapter 1, outside the chapter
  numbering and the unlock chain.
- Optional: accept a scheduled date, so a batch can schedule it like a chapter.

## WordPress: volume names must be unique per series

*Raised 2026-10-21 (volume naming review).*

The naming indexes keep `(kind, index)` and `(kind, subtitle)` unique, but WordPress gets
`Volume.wp_name` (`wp_volume_title`, else `wp_label(kind, index, subtitle)`), and two different
names can share it: an unkinded volume subtitled "Volume 3" and Volume 3 both send
"Volume 3". The plugin keys the TOC heading and the illustrations page on that string, so
publishing both would merge them on the site.

Not blocked today. Option: refuse (409) a create or PATCH whose `wp_label` collides with
another volume's `wp_name` in the same series, and report collisions left by the migration.
