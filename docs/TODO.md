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
