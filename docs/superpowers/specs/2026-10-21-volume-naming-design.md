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
  volume-aware chapter indexing"). Only the volume name sent to WordPress changes here.
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
cases, `tests/fixtures/volume_names.json`, read by pytest and by vitest, so the two can't drift.

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
order, mirroring `PUT /series/{id}/order` for chapters (stale list → 409, not half-applied). Then
`arrange()`.

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
- WordPress `doc_meta.volume_title` (`api/publish.py`, `api/publish_job.py`): **open, see below.**
- EPUB import form: `volume_title` is replaced by `volume_kind`, `volume_index`, `volume_subtitle`.
  `_volume()` in `api/routers/epub.py` finds an existing volume by `(kind, index)` when index is
  given, else `(kind, subtitle)`, and otherwise creates one with the placement rule above.
- ta.db import (`api/core/tadb_rows.py`): parse each desktop volume title, look up / create by the
  same key; the import cache key becomes that key. Report messages name the label.

Regenerate `web/src/api/schema.d.ts` (`npm run gen:api`).

## Migration

One Alembic revision, autogenerated for the schema, plus a data step (the only hand-written part):

1. Add `kind`, `volume_index`, `subtitle`, `series.volume_title_template`.
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
  case-insensitive kind, reorder stale-list 409, sort, `arrange()` after reorder/sort, EPUB export
  title and filename with and without override, template validation 422, tenancy 404s.
- Migration: a fixture series with "Volume 1", "Vol. 2.5 - Extra Bits", "第3巻", "Vol 3",
  "Prologue" → expected kind/index/subtitle, unchanged order and `epub_title`.
- ta.db and EPUB import: matching an existing volume by the new key.
- Playwright (`library.spec.ts` owns its seed rows): edit a volume's index to 3.5 and see it move;
  drag a volume and see it stick after creating another; Sort by number.

## Left to the builder

- Exact JSON shape of `volume_index` (string vs number), as long as the client never sees float
  rounding.
- Where the placement helper lives (`api/library.py` next to `arrange()` is the natural spot;
  keep modules under ~400 lines).
- Datalist wording and the settings help text.

## Open

- **What WordPress receives as `volume_title`.** `api/core/wp.py` sends it on every chapter
  publish and illustrations call; the plugin is outside this repo. If the plugin groups or finds
  volume pages by that string, changing it splits already-published volumes. Then a
  `wp_volume_title` column, filled from `title` in the migration, must keep sending the old string.
  `doc_meta` also sends `series_title` separately, so `full_title` would repeat the series name.
  Tracked in `docs/TODO.md` ("WordPress plugin: how it uses `volume_title`"); must be settled
  before the migration ships.
- **Syosetu volume grouping lands first** (owner's work, decided 2026-10-21). It is a fourth
  volume-creation path (`api/fetch_job.py`: a volume per chapter-title heading, found by
  `Volume.syosetu_group`). This change then names those volumes with the same parser (headings
  like 第一章 don't match a volume shape, so they become empty kind + heading as subtitle) and
  places them with the same rule (empty kind, no index → appended in creation order, i.e. arc
  order), keeps `UniqueConstraint("series_id", "syosetu_group")`, and leaves `syosetu_group` as
  the lookup key.
