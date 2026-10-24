# Volume Illustrations chapter, and EPUB chapters by table of contents

*2026-10-24. Replaces the TODO entry "EPUB import: create a volume Illustrations chapter".*

## Why

Two problems with EPUB import, found together.

**Clutter.** A light-novel EPUB opens with pages that hold nothing but art: cover, colour plates,
frontispiece, title page. Import makes one chapter per file, so a volume's chapter list starts with
a run of image-only chapters, most named after their file (`part0000`, `part0001`, ...).

**Wrong chapter boundaries.** Some publishers cut the book into files at every illustration, not at
every chapter, and the table of contents points at anchors *inside* files. Reference book:
「好きな子に告ったら、双子の妹がオマケでついてきた1」 (Brave Bunko). In that book:

- `part0006` holds the Prologue (`#toc-001`), `part0007` is a picture inside the Prologue, and `part0008`
  continues the Prologue and then starts chapter 1 at `#toc-002`;
- `part0012` holds five chapters (`#toc-004` to `#toc-008`);
- `part0014`, `part0018` and `part0026` are text with no TOC anchor at all, continuing the previous
  chapter after a picture.

Today's reader (`api/core/epub_read.py`) drops TOC fragments (`_resolve`), keeps one entry per file
(`_dedupe_by_href`), and adds off-TOC files as chapters of their own (`_order_by_spine`). For that
book you get about 30 chapters, five real chapters merged into one, and chapters named after
their files.

The user wants the art pages gathered into **one Illustrations chapter, first in the volume**, and
illustrations inside the story **kept inline** in their chapters. That chapter publishes to
WordPress as the volume's first post, previewing all of the volume's art.

## Goals

1. **EPUB chapters follow the table of contents.** The spine is read as one continuous stream, and a
   new chapter starts at each TOC entry (file plus optional `#anchor`). Everything between two
   entries (the rest of a file, off-TOC continuation files, image-only files) belongs to the
   chapter in progress. For an ordinary one-file-per-chapter EPUB the result is the same as today.
2. **Art pages become one Illustrations chapter, first in the volume.** Every chapter that comes out
   of step 1 with images and no text merges into a single chapter titled "Illustrations". This
   includes a leading off-TOC page and a TOC entry like 口絵. Its images keep their spine order.
3. **Illustrations inside the story stay inline** in the chapter they fall in (e.g. `part0007` stays
   in the Prologue). Nothing is copied into the Illustrations chapter at import.
4. **Publishing the Illustrations chapter to WordPress** sends one page holding its own images first,
   then every inline image from the volume's other chapters in reading order. That is **all** the
   volume's art, published or not. This is the user's decision: they accept that the page previews
   art from chapters still scheduled or locked. Images marked "exclude from export" stay out. The
   volume cover goes too, as today.
5. **The Illustrations chapter sits outside chapter numbering and outside the unlock chain.** In
   Volume 1 the first text chapter is still chapter 1, in the app and on WordPress. The
   Illustrations chapter gets no password and shifts no other chapter's number, password window,
   or previous/next link.
6. **"Mark as Illustrations"** on a chapter with no text, so volumes imported before this change can
   get an Illustrations chapter after the user merges their old plate chapters by hand.
7. **Retire** the "Publish illustrations" volume action and `POST /volumes/{id}/wp/illustrations`.
   Publishing the Illustrations chapter replaces them.

## Non-goals

- No automatic conversion of existing volumes. The user merges and marks by hand (Goal 6).
- No duplication of inline images into the Illustrations chapter. The volume-wide gathering happens
  only when the WordPress payload is built.
- No Illustrations chapter from TXT, syosetu or ta.db imports.
- No change to the WordPress plugin here. Its side goes in `docs/TODO.md` (below).
- No re-import or migration of chapters already imported with the old one-file-per-chapter rule.

## Anti-goals (failure even if it "works")

- A text chapter's number changes because an Illustrations chapter exists: in the SPA's per-volume
  numbering, in `wp_chapter_index`, in the password/unlock window, or in the previous-chapter link.
- Inline illustrations go missing from their text chapters (editor, EPUB export, or the chapter's
  own WordPress post), or mid-story art is pulled out into the Illustrations chapter.
- Text that sits between two TOC anchors is dropped or lands in the wrong chapter.
- The Illustrations chapter is refused for publish because it has no translated lines.
- A volume ends up with two Illustrations chapters.

## EPUB reading (`api/core/epub_read.py`)

### Chapters from the TOC

- The TOC entries keep their `#fragment`. `_dedupe_by_href` goes away, or dedupes on file plus
  fragment. Only the real table of contents counts: the nav's `landmarks` list (Cover / 本編 / 目次 in
  the reference book) and `page-list` are ignored. Check that `_read_toc` already does this.
- Walk the spine in order as one stream. A TOC entry without a fragment starts at the top of its
  file. One with a fragment starts at the element carrying that id. A chapter runs until the next
  entry's start, crossing file boundaries.
- Spine files before the first TOC entry: an image-only file falls under Goal 2. A text file
  becomes a chapter of its own named after the file, as today (my call: rare, and keeps
  today's behaviour).
- TOC entries whose start isn't on the spine are appended at the end, as `_order_by_spine` does today.
  A TOC entry whose anchor id can't be found starts at the top of its file (my call).
- An entry whose run has neither text nor images is dropped. An example is a nested "Part 1" entry
  pointing at the same spot as its first section.
- Entries are in reading (spine) order, not TOC order, as today.

### What `open_book` reports

Per chapter: title, a stable identifier the import can send back (file plus fragment; the builder
picks the shape), `char_count`, `image_count`, and whether it is image-only (images, no text).
`/epub/inspect`'s schema follows. Regenerate `schema.d.ts`.

### Extracting a chapter

`extract_chapter_content` works on a run (start file+anchor up to the next start), not a whole file.
Its output contract stays the same: text, plus images with `anchor_position`. The existing
illustration shapes (`<p><img></p>`, `<svg><image>`) and ruby handling carry over. An image-only
file inside a run is an inline illustration at that point in the text.

### Limits

`epub_safety.py`'s limits still hold. Images are charged per reference before they are read, as
now. A file split across several chapters may be charged per chapter that reads it (conservative,
fine) or once per import: builder's call. Either way the total must stay inside the 256 MiB
per-import budget. `MAX_CHAPTERS` (900) counts TOC chapters.

## Which chapters are "image-only"

A chapter (from the TOC split above) that ends up with at least one image and no text lines, by
the same test the import uses for its `empty` list (`not raw`) plus images. The picker gets this
from `open_book`. At import, the extraction result wins if the two disagree.

A chapter whose only image is the book's cover (`cover_href`) is dropped rather than merged (my
call). The cover is already stored as the volume's `is_cover` image, and the Illustrations page
would show it twice.

## EPUB import (`POST /epub/import`)

- The request names the picked chapters by the identifier from `open_book`. The Illustrations row
  stands for all image-only chapters.
- The image-only chapters picked produce **one** document: title and `chapter_title` "Illustrations",
  marked as the volume's Illustrations chapter (see Data). It has no lines. Its images are in spine
  order with `anchor_position` 0 and order kept by insertion (`id`).
- Text chapters import as one document each.
- With no image-only chapter picked, no Illustrations chapter is made.
- The volume **already has** an Illustrations chapter (re-import, or a second EPUB into the same
  volume): the new images are appended to it, except ones whose `src_path` it already holds (my
  call). Re-importing the same EPUB adds nothing, and there are never two.
- Text chapters keep today's skip-by-title rule against the volume. Chapters imported under the
  old rule, with file-name titles, won't match. That's accepted (Non-goals).
- The response lists "Illustrations" once in `imported`.
- The volume cover still attaches to the first imported document. That may be the Illustrations
  chapter, which is fine.

## Import picker (`web/src/library/epubBook.tsx`)

- Lists TOC chapters with their titles, not files.
- All image-only chapters collapse into **one row**, "Illustrations · N pages · M images", ticked by
  default (my call). Unticking it leaves them all out.
- Default ticks otherwise as today (`char_count >= 500` or has images). So the contents page (目次)
  and colophon (奥付) in the reference book stay listed but unticked.

## Ordering and numbering

- `arrange()` (`api/library.py`) always puts a volume's Illustrations chapter first in that volume,
  whatever order the client sends (reorder, drag, renumber-by-title, assign).
- **Chapter numbers skip it.** Every consumer of "the chapter number" must see numbers that exclude
  Illustrations chapters:
  - SPA `chapterNumber` (`web/src/library/volumeGroups.ts`): the Illustrations row shows no number.
  - `record()`: `wp_chapter_index` (not set for the Illustrations chapter).
  - `build_chapter`: the password/unlock window. The Illustrations chapter never gets a password.
  - `suggested_slot` and any other `series_order ± 1` neighbour lookup.
  - The cover-with-chapter-1 rule in `build_chapter`, which keys on the first *numbered* chapter.
  - Everything else from `grep series_order` (`api/restructure.py`, `api/routers/transfer.py`,
    `api/routers/exports.py`, the batch publish SPA).
- **How** (left to the builder): keep `series_order` as the pure sort key and derive a chapter number
  that skips Illustrations chapters, or keep `series_order` as the chapter number and give the
  Illustrations chapter a separate sort position. Pick whichever touches fewer consumers, and keep
  `renumber()`'s quiet-update behaviour. The TODO entry "WordPress: volume-aware chapter indexing"
  covers related ground. Don't solve it here, but don't make it harder.
- Syosetu series: never get one from import. Marking one by hand is refused there (my call: their
  numbering is syosetu's).

## Mark as Illustrations

- A chapter ⋯ menu item, "Mark as Illustrations", plus the reverse, "Unmark" (my call). Backed by a
  document field the API can write (PATCH or a dedicated endpoint: builder's choice).
- Allowed only when the chapter has no text lines (`line_has_content`), sits in a volume, and that
  volume has no other Illustrations chapter. Otherwise 409 with a message saying which rule failed.
  Marking moves it first in its volume (`arrange()`). Unmarking leaves it there as an ordinary
  numbered chapter.
- While marked:
  - Merging is refused if any part of the merge has text. Merging image-only chapters into it is
    allowed and keeps the mark. `api/restructure.py`'s merge keeps the first chapter, which will
    be the Illustrations chapter.
  - Edit Source that would give it text lines is refused (409).
  - Moving it to another volume is allowed only if that volume has no Illustrations chapter, and
    moving it to "No volume" is refused.

## Editor, progress, export

- It opens in the editor like any image-only chapter today. Progress counts as 100% (the existing
  `progress()` rule).
- EPUB export (`export_volume`) includes it as an image-only chapter, first, titled
  "Illustrations".

## WordPress publishing

- **Single publish** of the Illustrations chapter (the chapter row's Publish action) doesn't call the
  chapter endpoint. It enqueues the upload to the plugin's existing illustrations endpoint
  (`wp_http.publish_illustrations`), batched under ~1 MB by `build_illustrations_payloads` because the
  host's proxy resets larger bodies. That reuses today's `wp_illustrations` job machinery. The images
  are the Illustrations chapter's own images first, then the rest of the volume's (Goal 4).
- No translated lines are needed and no password is set. It is never scheduled: the endpoint takes
  no date, so it goes live when the upload runs.
- Status: the plugin has no lookup for the illustrations page (`check_status` keys on chapter number).
  The status refresh skips the Illustrations chapter, and its re-publish check uses the stored
  `wp_status` (my call).
- The re-publish safeguard applies. An Illustrations chapter already live asks for confirmation
  ("an existing illustrations page will be overwritten").
- **Batch publish** may include it. The batch job routes that item through the illustrations upload,
  takes no schedule slot for it, and records a per-item result like any chapter.
- **Write-back** on success: `wp_status = "publish"`, `wp_post_url` from the endpoint's `page_url`,
  `wp_published_at` = now, no `wp_chapter_index`. The first upload freezes the volume's WordPress name
  (`freeze_volume_name`), as today.
- At most one illustrations upload per user at a time (today's 409 for `wp_illustrations`), whether
  started alone or from a batch. Builder's call how the two share that rule.
- **Retired:** the "Publish illustrations" item in the volume ⋯ menu (`VolumePane.tsx`,
  `VolumeDetails.tsx` `Illustrations`/`useIllustrations`) and `POST /volumes/{id}/wp/illustrations`. The
  `wp_illustrations` job kind may stay as the internal worker or fold into a new one. The
  running-jobs label (`RunningJobs.tsx`) follows.

## Data

My call: a column on `documents` marking the volume's Illustrations chapter, e.g. `kind`
(`chapter` / `illustrations`, default `chapter`) or `is_illustrations`. Use an autogenerated
migration, with a partial unique index on `volume_id` where set (at most one per volume). Expose
it on the document schemas.

## Plugin TODO (add to `docs/TODO.md`)

New entry, "WordPress plugin: volume Illustrations page first":

- Title the illustrations page **"Volume X Illustrations"**, built from the `volume_title` it is sent.
- List it **first** in the volume's table of contents, ahead of chapter 1, outside the chapter
  numbering and the unlock chain.
- Optional: accept a scheduled date, so a batch can schedule it like a chapter.

Also:

- Remove "EPUB import: create a volume Illustrations chapter" (this design replaces it).
- In "WordPress: volume-aware chapter indexing", the target order now puts **Volume N Illustrations
  first** in each volume, not last.

## Desktop parity

This departs from the desktop reader (`translation_assistant/epub.py`), which splits by file. The
desktop repo is not changed. Note the departure in the module docstring.

## Tests the builder should cover

- Reader: a fixture shaped like the reference book (built in the test; never commit text from the
  real book). The cases:
  - a fragment in mid-file starts a new chapter;
  - five chapters in one file;
  - an off-TOC text file continues the previous chapter;
  - an image-only file mid-chapter stays inline at its position;
  - leading plates become image-only chapters;
  - landmarks are ignored;
  - a missing anchor starts at the top of its file;
  - an empty nested entry is dropped.

  Also: a one-file-per-chapter EPUB gives today's result.
- Import:
  - image-only chapters merge into one first chapter in spine order;
  - a cover-only page is dropped;
  - a re-import appends nothing new;
  - no image-only chapters picked means no Illustrations chapter;
  - budget limits still trip.
- `arrange()`: the Illustrations chapter stays first through reorder/assign/renumber, and text
  chapters' numbers don't change because it exists.
- Mark/unmark: each rule's 409, the merge and Edit Source refusals, the volume-move rules.
- Publish:
  - password, unlock index, previous-chapter link and `wp_chapter_index` match a volume without
    one;
  - single and batch publish of the Illustrations chapter hit the illustrations endpoint
    (MockTransport) with its own images first;
  - it is never refused for missing lines;
  - the status refresh skips it.
- SPA: `chapterNumber` skips it (vitest), and the picker groups image-only chapters.

## Left to the builder

The chapter identifier's shape, column shape and name, how numbering skips the Illustrations
chapter, PATCH versus endpoint for marking, whether `wp_illustrations` stays as the job kind, the
picker row's look, per-chapter versus per-import charging of split files, and how batch and single
uploads share the one-at-a-time rule.
