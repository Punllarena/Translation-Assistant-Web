# Volume naming: kind, decimal index, subtitle and a title template

Date: 2026-10-21 · Status: draft for review

## Why

A volume today has one free-text `title` (unique per series), a whole-number `volume_order`
that sets its place, and a free-text `epub_title` that falls back to the title, then the series
title (`api/routers/epub.py`, EPUB export). Light novels routinely ship **x.5 volumes**, **side
story collections with their own numbering** and one-off **extras**; a single title string can't
say which is which, can't sort them, and every volume's EPUB title has to be typed by hand in the
same `{Series} - Volume N - Subtitle` shape.

The owner chose (2026-10-21, "option 2"): each volume has a **kind**, a **decimal index** and a
**subtitle**; each series has a **title template**; the EPUB title is **generated from the
template unless overridden**. Volumes are **placed by kind + index by default, but a dragged
volume keeps its place**.

## Goals

1. Volume details show **Kind**, **Index** and **Subtitle** instead of Title.
2. Index is an exact decimal (`3`, `3.5`, `0`), or empty for a one-off extra.
3. Each series has a volume title template, default `{series} - {kind} {index} - {subtitle}`,
   edited in the series' Settings tab with a live preview.
4. A volume's EPUB title is the template's output unless the volume's `epub_title` is non-blank.
   Blank shows the generated title as the field's placeholder.
5. New volumes, and volumes whose kind or index changes, are placed in kind + index order; the
   volume list can be **dragged** to reorder, and a dragged position sticks. A **Sort by number**
   action restores kind + index order for the whole series.
6. Existing volumes, ta.db imports and EPUB imports get kind/index/subtitle parsed from their
   titles. Existing order is preserved exactly.

## Non-goals

- WordPress chapter indexing per volume stays deferred (`docs/TODO.md`, "WordPress:
  volume-aware chapter indexing"). Only the volume name sent to WordPress changes here, and only
  for volumes never published before (see "WordPress volume name").
- No `calibre:series_index` / EPUB3 `belongs-to-collection` metadata in built EPUBs. Worth doing
  (readers would sort x.5 volumes correctly) — add a `docs/TODO.md` entry, don't build it.
- No per-user default template; the default is a constant.
- No change to chapter numbering rules beyond `arrange()` running after volume reorders as it
  already does.

## Anti-goals

- Re-sorting anyone's volumes during migration or on a kind/index edit of a *different* volume.
- A generated title that goes stale: nothing stores the template's output; it is computed on read.

## Data model

`volumes` (`api/models/content.py`):

| column | type | notes |
|---|---|---|
| `kind` | `Text`, not null, default `'Volume'` | trimmed; free text, ≤ 40 chars |
| `index` (name it `volume_index` in SQL/Python to dodge the keyword) | `Numeric(10, 3)`, nullable | ≥ 0; null = no number |
| `subtitle` | `Text`, not null, default `''` | trimmed, ≤ 300 chars |
| `title` | **dropped** | replaced by the three above |
| `volume_order`, `epub_*` | unchanged | `epub_title` now means "override" |

Uniqueness (replaces `UniqueConstraint("series_id", "title")`), case-insensitive on kind like
`uq_users_username_lower`:

- `(series_id, lower(kind), volume_index)` unique **where `volume_index IS NOT NULL`**;
- `(series_id, lower(kind), subtitle)` unique **where `volume_index IS NULL`**.

So "Volume 3" can't exist twice, and two no-number extras need different subtitles. The 409
message becomes "a volume with that kind and number exists in this series".

`series` gains `volume_title_template: Text`, not null, default `''` — blank means the default
template constant. Validation: ≤ 300 chars, only the placeholders below, otherwise 422.

## Names

All naming lives in one pure module, `api/core/volume_names.py` (no DB, no FastAPI), mirrored in
`web/src/library/volumeNames.ts` for live previews. Both are tested against one shared table of
cases, `web/src/library/volumeNames.cases.json`, read by pytest and by vitest, so the two can't
drift. (It lives under `web/src`: the web image builds from `web/` alone and `tsc` checks test
files, so a vitest import of `tests/fixtures/` would break the Docker build.)

**Index formatting:** drop trailing zeros and a trailing point: `3.000 → 3`, `3.500 → 3.5`.

**Template rendering.** Placeholders: `{series}`, `{kind}`, `{index}`, `{subtitle}`. Rendering:

1. Split the template on the literal separator ` - `.
2. In each segment, substitute placeholders. A segment that contained at least one placeholder
   and in which **every** placeholder came out empty is dropped. (A segment with no placeholders
   is literal text and always kept.)
3. Collapse runs of spaces and trim each kept segment; join with ` - `.

Examples with the default template, series "Mushoku":

| kind | index | subtitle | result |
|---|---|---|---|
| Volume | 3 | The Journey | Mushoku - Volume 3 - The Journey |
| Volume | 3.5 | | Mushoku - Volume 3.5 |
| Side Story | 1 | Roxy | Mushoku - Side Story 1 - Roxy |
| Extra | — | Q&A | Mushoku - Extra - Q&A |

**Short label** (used where the series is already on screen): `{kind} {index} · {subtitle}`,
same dropping rules with ` · ` as separator — "Volume 3.5", "Side Story 1 · Roxy".

**Effective EPUB title:** `epub_title.strip() or render(template, …)`.

**Parsing a title** (migration, ta.db import, EPUB import pre-fill) → `(kind, index, subtitle)`:

- Normalise full-width digits and `．` to ASCII first.
- If the title starts with the series title followed by a separator (` - `, `:`, space), strip it.
- Recognised shapes, case-insensitive, each followed by an optional separator (`-`, `–`, `—`,
  `:`, `.`) and the rest as subtitle:
  - `Volume N`, `Vol N`, `Vol. N`, `V N` → kind `Volume`
  - `第N巻` → kind `Volume`
  - `Side Story N`, `SS N` → kind `Side Story`
  - `Short Stories N` → kind `Short Stories`
  - a bare leading number `N` → kind `Volume`
  - where `N` is `\d+(\.\d+)?`.
- Anything else: kind **empty**, index null, subtitle = the whole title (my call, 2026-10-21), so
  "Prologue" stays "Prologue" as a label and "Mushoku - Prologue" as an EPUB title, instead of
  "Volume · Prologue".

**Empty kind is allowed** (≤ 40 chars, may be `''`). Rendering treats it like any empty
placeholder; the sort key puts empty kind after all named kinds; the unique indexes cover it like
any other kind; the datalist doesn't offer it, but clearing the field is allowed.

## Ordering

`volume_order` stays the single source of truth for display and for `arrange()`; volumes are kept
numbered `1..N` per series after every change below.

**Sort key:** `(0 if kind is "Volume" (case-insensitive) else 2 if kind is empty else 1,
lower(kind), index is null, index, id)` — Volume first, other named kinds alphabetically, then
empty kind; each by index, unnumbered last within its kind.

**Placement on create, or when a PATCH changes kind or index** (my call, 2026-10-21): take the
volume out, then, looking only at volumes of the **same kind** (case-insensitive):

1. if one has a lower index (or this one has no index and any numbered one exists), insert right
   after the last such volume's position;
2. else, if one has a higher index, insert right before the first such volume's position;
3. else (first of its kind) insert at `1 + max(volume_order of volumes whose sort key < its key)`,
   or 1 if none.

Shift the rest down. Other volumes keep their relative order, so a dragged Side Story stays put
and its siblings follow it. Example: order Vol 1, Vol 2, Vol 3, SS 1 (dragged here), Vol 4 — a new
Vol 5 goes after Vol 4; a new SS 2 goes right after SS 1, before Vol 4; a first "Extra" goes at the
end. An explicit `volume_order` in the create body still wins (existing API behaviour).

**Drag:** `PUT /series/{id}/volumes/order` with every volume id of the series once, in the new
order, mirroring `PUT /series/{id}/order` for chapters (stale list → 422 like that endpoint, not
half-applied). Then `arrange()`.

**Sort by number:** `POST /series/{id}/volumes/sort` reorders every volume by sort key, then
`arrange()`. The SPA asks with a `ConfirmDialog` first ("Sort volumes by kind and number? Volumes
you placed by hand will move.").

## API

- `VolumeCreate`: `kind` (default "Volume"), `volume_index` (decimal or null), `subtitle`
  (default ""), replacing `title`; rest unchanged. `VolumeUpdate`: same fields, optional.
- `VolumeOut`: drops `title`; adds `kind`, `volume_index` (serialised as a string such as `"3.5"`
  so no float rounding reaches the client — builder's call on exact JSON shape), `subtitle`,
  `label` (short label) and `full_title` (effective EPUB title).
- `SeriesOut` / `SeriesUpdate`: `volume_title_template`; `SeriesOut` also gets
  `volume_title_template_effective` (the default when blank) so the SPA doesn't hard-code it twice.
- EPUB export: title = effective EPUB title; filename = `sanitize_filename(full_title)`.
- Markdown/TXT export label (`api/routers/exports.py`): `full_title`.
- WordPress `doc_meta.volume_title` (`api/publish.py`, `api/publish_job.py`): the frozen
  `wp_volume_title`, else the WordPress label; see "WordPress volume name". `VolumeOut` also gets
  `wp_volume_title`.
- EPUB import form: `volume_title` is replaced by `volume_kind`, `volume_index`, `volume_subtitle`.
  `_volume()` in `api/routers/epub.py` finds an existing volume by `(kind, index)` when index is
  given, else `(kind, subtitle)`, and otherwise creates one with the placement rule above.
- ta.db import (`api/core/tadb_rows.py`): parse each desktop volume title, look up / create by the
  same key; the import cache key becomes that key. Report messages name the label.

Regenerate `web/src/api/schema.d.ts` (`npm run gen:api`).

## Migration

One Alembic revision, autogenerated for the schema, plus a data step (the only hand-written part):

Down-revision: `f8ea6091f19f` (head after PR #10).

1. Add `kind`, `volume_index`, `subtitle`, `wp_volume_title`, `series.volume_title_template`;
   fill `wp_volume_title` for already-published volumes (see "WordPress volume name").
2. For each series, parse each volume's title in `volume_order, id` order. If the parsed
   `(kind, index)` is already taken in that series, store empty kind, null index and the **whole**
   title as subtitle instead (a "Vol 3" next to a "Volume 3" survives unchanged as a label).
   Expected, accepted change: a volume with a blank `epub_title` gets a new, template-generated
   EPUB title and download name after migration (that is the feature).
3. Do not touch `volume_order` or `epub_title`. An existing non-blank `epub_title` therefore stays
   an override, as the owner typed it.
4. Drop `title` and its constraint; create the two partial unique indexes.

Downgrade restores `title` from the short label (best effort; documented as lossy only in that
the label format may differ from the original string).

## SPA

- **Volume details** (`VolumeDetails.tsx`): Kind (input with a `<datalist>` of Volume, Side
  Story, Short Stories, Extra, plus kinds already used in the series), Index (text input,
  `inputmode="decimal"`, validated as `\d+(\.\d+)?` or empty), Subtitle, then EPUB title with the
  live generated title as its placeholder, then the other EPUB fields.
- **New volume** (`NewVolumeDialog.tsx`): the same three fields, kind defaulting to Volume and
  index to the next whole number after the series' highest Volume index (1 if none).
- **EPUB import** (`epubBook.tsx`): the "Volume title" field becomes the three fields, pre-filled
  by parsing the book's title (the TS parser).
- **Series Settings** (`SeriesSettings.tsx`): "Volume title template" field, placeholder = default
  template, a one-line help listing the four placeholders, and a preview rendered against the
  series' first volume (or a sample "Volume 1 - Subtitle" when it has none).
- **Volume list** (`VolumeList.tsx`): rows show the short label; rows become draggable to reorder
  (grip, as in `ChapterTable.tsx`). The list already accepts chapter drops — the drag payload must
  say whether it carries a chapter or a volume (`web/src/library/drop.ts`). A **Sort by number**
  item goes in the volume pane's ⋯ menu.
- Everywhere that shows `volume.title` today shows `label`: `VolumeList`, `VolumePane` header and
  confirm dialogs, `MoveDialog`, `shelf.ts`, `VolumesTab` aria-label. The EPUB download filename
  uses `full_title`.

## Tests

- `volume_names` shared case table: rendering (all-empty segments, literal segments, extra spaces,
  decimals), index formatting, parsing (each shape, full-width digits, series prefix, no match).
- API: create/patch placement (dragged volume stays put), uniqueness 409s for both partial indexes,
  case-insensitive kind, reorder stale-list 422, sort, `arrange()` after reorder/sort, EPUB export
  title and filename with and without override, template validation 422, tenancy 404s.
- Migration: a fixture series with "Volume 1", "Vol. 2.5 - Extra Bits", "第3巻", "Vol 3",
  "Prologue" → expected kind/index/subtitle, unchanged order and `epub_title`.
- ta.db and EPUB import: matching an existing volume by the new key.
- WordPress: the first publish freezes `wp_volume_title`; a later subtitle/template change still
  sends the frozen string (chapter and illustrations payloads); migration fills it only for
  volumes with published chapters.
- Syosetu: `group_volume` creates empty-kind heading volumes, suffixes clashing subtitles, keeps
  arc order; merge keeps the survivor's naming fields.
- Playwright (`library.spec.ts` owns its seed rows): edit a volume's index to 3.5 and see it move;
  drag a volume and see it stick after creating another; Sort by number.

## Left to the builder

- Exact JSON shape of `volume_index` (string vs number), as long as the client never sees float
  rounding.
- Where the placement helper lives (`api/library.py` next to `arrange()` is the natural spot;
  keep modules under ~400 lines).
- Datalist wording and the settings help text.

## WordPress volume name

Checked 2026-10-21 against the plugin source
(`Punllarena/translation-assistant-publisher`, `includes/class-publisher.php`). The plugin uses
`volume_title` as a **key**, not only for display:

- `publish_illustrations` finds the volume's illustrations page by the slug
  `{series_slug}-illustrations-{sanitize_title(volume_title)}`, and titles it
  `{volume_title} — Illustrations`. A changed string creates a second illustrations page and
  orphans the first.
- `append_toc_entry` writes `<h3>{volume_title}</h3>` on the series index page once per volume,
  de-duplicated by an exact substring match. A changed string starts a second heading in the
  middle of the volume's table of contents.

So the string WordPress gets must not change once a volume has been published, whatever later
happens to its kind, index, subtitle or the series template (my call, 2026-10-21):

- New column `volumes.wp_volume_title: Text`, nullable. Null = never published.
- What is sent: `wp_volume_title` when set; otherwise the **WordPress label** — the short label
  with ` - ` instead of ` · ` ("Volume 3 - The Journey"); the series title is already the index
  page's own title, so the full title would repeat it.
- The first successful chapter publish or illustrations publish of a volume stores what it sent in
  `wp_volume_title` (`api/publish.py`, `api/publish_job.py`), so it is frozen from then on.
- Migration: set `wp_volume_title = title` for every volume with at least one chapter that has a
  non-empty `wp_post_url` or a `wp_published_at`, so already-published volumes keep sending
  exactly what they sent before. Illustrations-only publishes are not recorded anywhere today, so
  a volume published only that way is missed; accepted (rare).
- Volume details show the frozen name read-only, under the EPUB fields, as "WordPress volume name",
  with the note "Fixed after first publish; WordPress finds the volume's pages by it." Editing it
  is a non-goal.
- Merging volumes: the survivor keeps its own `wp_volume_title`.

This resolves the `docs/TODO.md` entry "WordPress plugin: how it uses `volume_title`"; remove it
when this ships.

## Syosetu heading volumes

Landed first (PR #10; spec `2026-10-21-syosetu-heading-volumes-design.md`). What this change
does to it:

- `group_volume` (`api/fetch_job.py`) creates a heading volume as kind `''`, index null,
  subtitle = heading. Clash rule follows the no-index uniqueness: suffix the subtitle ` (2)`,
  ` (3)` … while `(series, '', subtitle)` with null index is taken. Placement: the rule above (an
  empty-kind, unnumbered volume goes after the last empty-kind volume, else at the end), which keeps
  heading volumes in arc order. The lookup stays `volume_syosetu_groups` by `(series_id, heading)`.
- Migration: heading volumes are parsed like any other title. Headings like 第一章 don't match a
  volume shape and become empty kind + the title as subtitle; a heading that happens to read
  "第2巻 …" becomes Volume 2, which is fine. `volume_syosetu_groups` is untouched.
- `merge_volumes` (`api/routers/volumes.py`): the survivor keeps its own kind, index, subtitle,
  EPUB fields and `wp_volume_title` — its docstring's "title" becomes those.
- `MergeVolumesDialog.tsx` lists volumes by `label`.
- `VolumeList.tsx` has a Select mode (checkboxes, shift-click ranges, `rangeToggle.ts`) and
  accepts chapter drops; volume drag-to-reorder must not fire in Select mode, and must keep the
  chapter drop working (payload type in `drop.ts`).
