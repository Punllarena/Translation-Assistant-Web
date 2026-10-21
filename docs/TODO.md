# TODO

Deferred work, recorded so it can be picked up later. Newest first.

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
volumes renumbers `series_order`. Publishing still reads the series-wide `series_order`:

- `api/publish.py:141`: `wp_chapter_index = series_order`
- `api/publish.py:98`: password / unlock-after window computed from `series_order`
- `api/publish.py:167-171`: "previous chapter" found as `series_order - 1`

To do:

- Decide what WordPress should receive for a series with volumes. The target order is:
  Volume 1 Chapter 1 … Volume 1 Chapter x → Volume 1 Illustrations →
  Volume 2 Chapter 1 … Volume 2 Chapter x → Volume 2 Illustrations, and so on.
- Make the unlock chain and the previous/next chapter links follow that order, including the
  illustrations page at the end of each volume.
- Chapters already published before a renumber will carry their old index on WordPress. Decide
  how a re-publish reconciles them (and whether the re-publish 409 safeguard should flag a
  changed index).
- Series without volumes and syosetu series keep their own indexing (syosetu's chapter numbers).

## EPUB import: create a volume Illustrations chapter

*Raised 2026-10-20.*

When an EPUB is imported (`api/core/epub_read.py`, `api/routers/epub.py`), also create an
**Illustrations** chapter for the volume that gathers every image found in the EPUB, placed
last in the volume (after the final chapter).

- Images that appear inside chapters **stay inline** in those chapters too; the illustrations
  chapter is an additional grouping, not a move.
- Respect the existing EPUB limits in `api/core/epub_safety.py` (the image budget is charged per
  image reference; check whether duplicating references needs its own accounting).
- Relate this to the WordPress "Publish illustrations" job (`wp_illustrations`), which today
  builds the illustrations page from the volume's images; decide whether it should publish this
  chapter instead.
