# TODO

Deferred work, recorded so it can be picked up later. Newest first.

## WordPress plugin: series-wide status route

*Raised 2026-10-30.* The series page checks WordPress one chapter per request
(`POST /documents/{id}/wp/status`, capped at 50 a click in `web/src/publish/useStatusCheck.ts` because every
check is a request). Add one route to the plugin (Punllarena/translation-assistant-publisher) returning, for a
series' slug, every chapter's and the volume illustrations page's status, post URL and live date in one answer;
today's per-chapter `/status` returns no date at all, so ta-web can only show the date it stored at publish.

What ta-web does with it:

- check on page load instead of when a tag is clicked, so no tag claims a state the site has left;
- show each post's live date (and so "Published?" becomes a real state, not a guess);
- drop the 50-chapter cap in `useStatusCheck` (and the per-chapter route stays for a single chapter).

Spec: `docs/superpowers/specs/2026-10-30-series-page-revision-design.md` §2.

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

## Editor: JParser dictionary words inside a Latin run

*Raised 2026-10-29.* Ctrl+Z after Use and JParser's Latin runs were fixed in PR #31.

- An unmatched Latin run is taken whole, so a dictionary entry starting mid-run is not looked up. Minor;
  revisit only if it shows up.

## Yomitan dictionaries: deferred formats and fields

*Raised 2026-10-22 during the Yomitan dictionaries work
(`docs/superpowers/specs/2026-10-22-yomitan-dictionaries-design.md`).*

Only term dictionaries are read, flattened to a short plain-text gloss. Deferred:

- Kanji dictionaries (KANJIDIC and similar) are refused; a per-character lookup panel could use them.
- Pitch-accent dictionaries (`term_meta_bank` `pitch`) are ignored.
- Frequency dictionaries (`term_meta_bank` `freq`) are ignored; they could rank candidates.
- Full entries: the structured-content tree is flattened, so tables, images, examples and cross-references are not shown.

## EPUB: series position metadata

*Raised 2026-10-21 during the volume naming work
(`docs/superpowers/specs/2026-10-21-volume-naming-design.md`).*

Volumes now carry a numeric `volume_index`, but the EPUB built by `api/core/epub_build.py` does
not record where a volume sits in its series, so readers cannot sort volumes of one series.

To do:

- Write `calibre:series` / `calibre:series_index` (EPUB 2 meta) from the series title and `volume_index`.
- Write EPUB 3 `belongs-to-collection` (collection type `series`) with `group-position` from `volume_index`.
- Skip both for unnumbered volumes (no `volume_index`).

## WordPress: volume names must be unique per series

*Raised 2026-10-21 (volume naming review).*

The naming indexes keep `(kind, index)` and `(kind, subtitle)` unique, but WordPress gets
`Volume.wp_name` (`wp_volume_title`, else `wp_label(kind, index, subtitle)`), and two different
names can share it: an unkinded volume subtitled "Volume 3" and Volume 3 both send
"Volume 3". The plugin keys the TOC heading and the illustrations page on that string, so
publishing both would merge them on the site.

Not blocked today. Option: refuse (409) a create or PATCH whose `wp_label` collides with
another volume's `wp_name` in the same series, and report collisions left by the migration.
