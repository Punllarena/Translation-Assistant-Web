# Volume Naming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace a volume's single `title` with kind + decimal index + subtitle, generate EPUB titles from a per-series template unless overridden, place volumes by kind and index while letting a dragged position stick, and freeze the name WordPress sees once a volume is published.

**Architecture:** One pure naming module (`api/core/volume_names.py`) with a TypeScript twin (`web/src/library/volumeNames.ts`), both tested against one JSON case table. `Volume` gains model properties (`label`, `full_title`, `wp_name`) that every reader uses instead of `title`, so routers and `VolumeOut` stay thin. Placement, reorder and sort live in a new `api/volume_order.py`, and every path that creates a volume goes through `place()`.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres (partial and functional unique indexes), Pydantic v2, React + TanStack Query, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-21-volume-naming-design.md`

## Global Constraints

- Handlers only `flush()`; build every router with `api_router()`; tenancy via `scoped()` / `scoped_volume()` (404 for other users' rows).
- Migrations: autogenerate the schema part; the data step is the only hand-written part. Down-revision `f8ea6091f19f`.
- No Python module over ~400 lines (`api/core/tadb_rows.py` is at 387; Task 6 moves its volume code out).
- `kind`: trimmed, ≤ 40 chars, may be `''`; default `"Volume"`. `subtitle`: trimmed, ≤ 300 chars. `volume_index`: `Numeric(10, 3)`, ≥ 0, nullable.
- Default template: `{series} - {kind} {index} - {subtitle}`. Placeholders: `{series}`, `{kind}`, `{index}`, `{subtitle}` only. Template ≤ 300 chars.
- Short label template `{kind} {index} · {subtitle}` with separator ` · `; WordPress label `{kind} {index} - {subtitle}` with separator ` - `.
- 409 message for a taken name: `a volume with that kind and number exists in this series`.
- Sort-by-number confirm copy: `Sort volumes by kind and number? Volumes you placed by hand will move.`
- Volume details note for the frozen name: label `WordPress volume name`, note `Fixed after first publish; WordPress finds the volume's pages by it.`
- Run `npm run gen:api` after every API schema change that the SPA reads.
- E2E: each spec owns its seed rows in `tools/e2e_seed.py`; seed names must not contain "E2E chapter".

## Review Focus

1. **A comma or too many decimals in the index** (`3,5`, `3.1234`): the API answers 422 and the SPA shows the error. Nothing is silently rounded. Test in Task 3.
2. **Kinds that differ only in case or spacing** (`volume ` vs `Volume`): stored trimmed, treated as the same kind by the unique indexes (409) and by placement. Test in Tasks 3 and 4.
3. **A subtitle that contains ` - `** (`Re:Start - Part 1`): only the template's own separators split segments, so the subtitle stays whole. Case in the shared table, Task 1.
4. **All three name fields empty** (kind `''`, no index, no subtitle): refused with 422 (`give a kind, number or subtitle`), because the label would be blank. Test in Task 3.
5. **Path-hostile characters in a generated EPUB filename** (`Vol 3: A/B`): the download name passes through `sanitize_filename`, and an empty result falls back to `volume.epub`. Test in Task 3.

---

## File structure

| File | Responsibility |
|---|---|
| `api/core/volume_names.py` (new) | Pure: index formatting, template render/validate, labels, title parsing, sort key |
| `web/src/library/volumeNames.cases.json` (new) | Shared case table for pytest and vitest |
| `web/src/library/volumeNames.ts` (new) | TS twin of the naming functions, plus `nextVolumeIndex` |
| `api/models/content.py` | `Volume` columns, indexes and properties; `Series.volume_title_template` |
| `migrations/versions/<rev>_volume_naming.py` (new) | Schema, title split, WordPress name freeze |
| `api/schemas/volumes.py`, `api/schemas/series.py` | New fields and validation |
| `api/volume_order.py` (new) | `place`, `reorder`, `sort_by_number` |
| `api/routers/volumes.py` | Create/patch via `place`; `PUT …/volumes/order`, `POST …/volumes/sort` |
| `api/routers/epub.py`, `api/core/tadb_volumes.py` (new, split from `tadb_rows.py`), `api/fetch_job.py` | Creation paths by the new key |
| `api/publish.py`, `api/publish_job.py`, `api/routers/wp.py` | Send `wp_name`; freeze on first publish |
| `web/src/library/*.tsx` | Fields, labels, template setting, volume drag, Sort by number |

---

### Task 1: Python naming module and shared case table

**Files:**
- Create: `api/core/volume_names.py`
- Create: `web/src/library/volumeNames.cases.json`
- Test: `tests/test_core_volume_names.py`

**Interfaces:**
- Produces:
  - `DEFAULT_TEMPLATE: str`, `PLACEHOLDERS = ("series", "kind", "index", "subtitle")`
  - `format_index(index: Decimal | None) -> str`: `""` for None; trailing zeros and point dropped
  - `render(template: str, *, series: str, kind: str, index: Decimal | None, subtitle: str, sep: str = " - ") -> str`
  - `label(kind, index, subtitle) -> str` and `wp_label(kind, index, subtitle) -> str`
  - `validate_template(template: str) -> None`: raises `ValueError` naming the bad placeholder or stray brace
  - `parse_title(title: str, series_title: str = "") -> ParsedName`, a `NamedTuple(kind: str, index: Decimal | None, subtitle: str)`
  - `sort_key(kind: str, index: Decimal | None) -> tuple`: `(0 Volume | 1 named | 2 empty, kind.casefold(), index is None, index or 0)`

- [ ] **Step 1: Write the case table** `web/src/library/volumeNames.cases.json`. Indexes are strings or `null`. Its shape:

```json
{
  "format_index": [{"in": "3.000", "out": "3"}, {"in": "3.500", "out": "3.5"}, {"in": "0", "out": "0"}, {"in": null, "out": ""}],
  "render": [
    {"template": "{series} - {kind} {index} - {subtitle}", "series": "Mushoku", "kind": "Volume", "index": "3", "subtitle": "The Journey", "out": "Mushoku - Volume 3 - The Journey"},
    {"template": "{series} - {kind} {index} - {subtitle}", "series": "Mushoku", "kind": "Volume", "index": "3.5", "subtitle": "", "out": "Mushoku - Volume 3.5"},
    {"template": "{series} - {kind} {index} - {subtitle}", "series": "Mushoku", "kind": "Side Story", "index": "1", "subtitle": "Roxy", "out": "Mushoku - Side Story 1 - Roxy"},
    {"template": "{series} - {kind} {index} - {subtitle}", "series": "Mushoku", "kind": "Extra", "index": null, "subtitle": "Q&A", "out": "Mushoku - Extra - Q&A"},
    {"template": "{series} - {kind} {index} - {subtitle}", "series": "Mushoku", "kind": "", "index": null, "subtitle": "Prologue", "out": "Mushoku - Prologue"},
    {"template": "{series} - {kind} {index} - {subtitle}", "series": "S", "kind": "Volume", "index": "1", "subtitle": "Re:Start - Part 1", "out": "S - Volume 1 - Re:Start - Part 1"},
    {"template": "{series} Vol. {index}:  {subtitle}", "series": "S", "kind": "Volume", "index": "2", "subtitle": "X", "out": "S Vol. 2: X"},
    {"template": "Book - {subtitle}", "series": "S", "kind": "Volume", "index": "2", "subtitle": "", "out": "Book"}
  ],
  "label": [
    {"kind": "Volume", "index": "3.5", "subtitle": "", "out": "Volume 3.5", "wp": "Volume 3.5"},
    {"kind": "Side Story", "index": "1", "subtitle": "Roxy", "out": "Side Story 1 · Roxy", "wp": "Side Story 1 - Roxy"},
    {"kind": "", "index": null, "subtitle": "第一章", "out": "第一章", "wp": "第一章"}
  ],
  "parse": [
    {"title": "Volume 1", "series": "", "kind": "Volume", "index": "1", "subtitle": ""},
    {"title": "Vol. 2.5 - Extra Bits", "series": "", "kind": "Volume", "index": "2.5", "subtitle": "Extra Bits"},
    {"title": "vol 4: Dawn", "series": "", "kind": "Volume", "index": "4", "subtitle": "Dawn"},
    {"title": "V 7", "series": "", "kind": "Volume", "index": "7", "subtitle": ""},
    {"title": "第3巻 旅立ち", "series": "", "kind": "Volume", "index": "3", "subtitle": "旅立ち"},
    {"title": "第１２巻", "series": "", "kind": "Volume", "index": "12", "subtitle": ""},
    {"title": "Side Story 1 — Roxy", "series": "", "kind": "Side Story", "index": "1", "subtitle": "Roxy"},
    {"title": "SS 2", "series": "", "kind": "Side Story", "index": "2", "subtitle": ""},
    {"title": "Short Stories 1", "series": "", "kind": "Short Stories", "index": "1", "subtitle": ""},
    {"title": "3 - The Journey", "series": "", "kind": "Volume", "index": "3", "subtitle": "The Journey"},
    {"title": "Mushoku - Volume 5", "series": "Mushoku", "kind": "Volume", "index": "5", "subtitle": ""},
    {"title": "Mushoku", "series": "Mushoku", "kind": "", "index": null, "subtitle": "Mushoku"},
    {"title": "3rd Arc", "series": "", "kind": "", "index": null, "subtitle": "3rd Arc"},
    {"title": "Prologue", "series": "", "kind": "", "index": null, "subtitle": "Prologue"},
    {"title": "第一章", "series": "", "kind": "", "index": null, "subtitle": "第一章"}
  ],
  "templates_invalid": ["{Series} - {index}", "{title}", "{series} - {kind", "x }"]
}
```

- [ ] **Step 2: Write `tests/test_core_volume_names.py`.** It loads the JSON from `Path(__file__).resolve().parents[1] / "web/src/library/volumeNames.cases.json"` and parametrizes one test per section:
  - `test_format_index(case)`: `format_index(Decimal(in) if in else None) == out`
  - `test_render(case)`: `render(...) == out`
  - `test_label(case)`: `label(...) == out` and `wp_label(...) == wp`
  - `test_parse(case)`: `parse_title(title, series) == ParsedName(kind, Decimal(index) if index else None, subtitle)`
  - `test_invalid_template(t)`: `pytest.raises(ValueError)`; also `validate_template(DEFAULT_TEMPLATE)` returns None
  - `test_sort_key_orders_kinds`: sorted keys put `("Volume","2")`, `("Volume","10")`, `("Volume",None)`, `("extra","1")`, `("Side Story","1")`, `("","1")` in exactly that order

- [ ] **Step 3: Run it and see it fail.** Run `pytest tests/test_core_volume_names.py -v`. Expected: ImportError for `api.core.volume_names`.

- [ ] **Step 4: Implement `api/core/volume_names.py`.**
  - **Render:** split the template on the literal `sep` first, then substitute. A segment that contained a placeholder and whose placeholders all came out empty is dropped. Collapse whitespace runs in each kept segment and strip it, drop segments that end up empty, then join with `sep`.
  - **Parse, in this order:**
    1. NFKC-normalise digits and `．` to ASCII.
    2. Strip a leading series title (case-insensitive) when it is followed by ` - `, `:` or a space, and only if something remains.
    3. Match the case-insensitive shapes `^(?:volume|vol\.?|v)\s*N`, `^第\s*N\s*巻`, `^(?:side story|ss)\s*N`, `^short stories\s*N`, and a bare `^N`, where `N = \d+(?:\.\d+)?`.
    4. The number must be followed by end of string, or whitespace or `[-–—:.]`. This keeps `3rd Arc` from matching.
    5. Strip one optional separator `[-–—:.]` and whitespace. The remainder is the subtitle.
    6. No match: `ParsedName("", None, title.strip())`.

- [ ] **Step 5: Run it and see it pass.** Run `pytest tests/test_core_volume_names.py -v` and `ruff check api/core/volume_names.py`. Expected: all PASS, no lint errors.

- [ ] **Step 6: Commit.** Run `git add api/core/volume_names.py web/src/library/volumeNames.cases.json tests/test_core_volume_names.py && git commit -m "feat(api): volume naming rules (render, labels, parse, sort key)"`.

---

### Task 2: TypeScript naming twin

**Files:**
- Create: `web/src/library/volumeNames.ts`
- Test: `web/src/library/volumeNames.test.ts`

**Interfaces:**
- Consumes: the case table from Task 1.
- Produces: `DEFAULT_TEMPLATE`, `formatIndex(index: string | null): string`, `render(template: string, v: {series: string; kind: string; index: string | null; subtitle: string}, sep?: string): string`, `label(kind, index, subtitle)`, `wpLabel(...)`, `parseTitle(title: string, seriesTitle?: string): {kind: string; index: string | null; subtitle: string}`, `templateError(t: string): string | null`, `nextVolumeIndex(volumes: {kind: string; volume_index: string | null}[]): string`. Indexes stay strings end to end; never `parseFloat` them.

- [ ] **Step 1: Write `volumeNames.test.ts`.** It imports `./volumeNames.cases.json` and runs the same five sections with `it.each`. For `parse`, the expected index is the case's string or `null`, already formatted (`"2.5"`, not `"2.500"`). Add the `nextVolumeIndex` cases:
  - `[]` gives `"1"`
  - `[{kind:"Volume",volume_index:"3.5"},{kind:"volume",volume_index:"2"},{kind:"Side Story",volume_index:"9"}]` gives `"4"`
  - `[{kind:"",volume_index:null}]` gives `"1"`
- [ ] **Step 2: Run it and see it fail.** Run `cd web && npx vitest run src/library/volumeNames.test.ts`. Expected: it fails because the module isn't found.
- [ ] **Step 3: Implement `volumeNames.ts`**, mirroring Task 1's rules. Use `String.prototype.normalize("NFKC")`. `formatIndex` trims the string with the regex `/\.?0+$/` only when it contains a `.`. `nextVolumeIndex` floors the highest `Volume`-kind index (case-insensitive, trimmed) by string-splitting on `.` and adds 1.
- [ ] **Step 4: Run it and see it pass.** Run `cd web && npx vitest run src/library/volumeNames.test.ts && npx tsc --noEmit`. Expected: PASS, no type errors.
- [ ] **Step 5: Commit.** Run `git add web/src/library/volumeNames.ts web/src/library/volumeNames.test.ts && git commit -m "feat(web): volume naming rules mirrored from the API"`.

---

### Task 3: Schema, migration, API fields and the title sweep

Removing `title` breaks every reader at once, so this task also moves every reader to the new properties. Creation paths keep today's "append last" order here; Task 4 replaces it with `place()`.

**Files:**
- Modify: `api/models/content.py` (`Series`, `Volume`)
- Create: `migrations/versions/<rev>_volume_naming.py` (autogenerate, then add the data step)
- Modify: `api/schemas/volumes.py`, `api/routers/volumes.py`, `api/routers/epub.py` (export only), `api/routers/exports.py`, `api/publish.py:112`, `api/publish_job.py:88`, `api/fetch_job.py:group_volume`, `api/routers/epub.py:_volume`, `api/core/tadb_rows.py:_volume` (name fields only; Task 6 reworks the lookup), `tools/e2e_seed.py:117,133`
- Modify tests that build `Volume(title=…)`: `test_arrange.py`, `test_documents.py`, `test_epub_api.py`, `test_epub_export.py`, `test_exports.py`, `test_migration_orphans.py`, `test_restructure.py`, `test_scrape_api.py`, `test_series.py`, `test_volumes.py`, `test_volumes_merge.py`, `test_wp_jobs.py`, and any `title=` volume asserts
- Test: `tests/test_volume_names_api.py`, `tests/test_migration_volume_naming.py`

**Interfaces:**
- Consumes: Task 1 (`render`, `label`, `wp_label`, `parse_title`, `DEFAULT_TEMPLATE`).
- Produces:
  - **Columns:**
    - `Volume.kind: str`
    - `Volume.volume_index: Decimal | None`
    - `Volume.subtitle: str`
    - `Volume.wp_volume_title: str | None`
    - `Series.volume_title_template: str`, `''` = default
  - **Indexes:**
    - `uq_volumes_kind_index` on `(series_id, lower(kind), volume_index)` with `postgresql_where=volume_index IS NOT NULL`
    - `uq_volumes_kind_subtitle` on `(series_id, lower(kind), subtitle)` with `postgresql_where=volume_index IS NULL`
    - Both declared after the class, like `uq_users_username_lower`.
  - **Properties:**
    - `Volume.label -> str`
    - `Volume.full_title -> str`: `epub_title.strip() or render(series template or DEFAULT) or label or series.title`
    - `Volume.wp_name -> str`: `wp_volume_title or wp_label(...)`
    - `Series.volume_title_template_effective -> str`
  - **`VolumeOut` fields:** `kind`, `volume_index: str | None` (serialised with `format_index`), `subtitle`, `label`, `full_title`, `wp_volume_title: str | None`. It no longer has `title`.
  - **`VolumeCreate` / `VolumeUpdate`:**
    - `kind: str = "Volume"` (`max_length=40`, stripped)
    - `volume_index: Decimal | None = Field(None, ge=0, max_digits=10, decimal_places=3)`
    - `subtitle: str = ""` (`max_length=300`, stripped)
    - A model validator raises `give a kind, number or subtitle` when all three are empty. On update it checks the merged result in the router.
  - `NAME_TAKEN = "a volume with that kind and number exists in this series"` replaces `TITLE_TAKEN`.

- [ ] **Step 1: Write the failing API tests** in `tests/test_volume_names_api.py`. Use the existing `app_client`, `make_user` and `make_series` fixtures.
  - `test_create_returns_names`: POST `{"kind": "Volume", "volume_index": "3.5", "subtitle": "Dawn"}` returns 201 with `volume_index == "3.5"`, `label == "Volume 3.5 · Dawn"` and `full_title == "<series> - Volume 3.5 - Dawn"`.
  - `test_index_rejects_comma_and_four_decimals`: `"3,5"` and `"3.1234"` both give 422.
  - `test_kind_is_trimmed_and_case_insensitive_unique`: create `Volume 1`, then `{"kind": " volume ", "volume_index": "1"}` gives 409 with `NAME_TAKEN`.
  - `test_unnumbered_needs_distinct_subtitle`: two `{"kind": "Extra", "subtitle": "Q&A"}` give 409; a different subtitle gives 201.
  - `test_all_empty_refused`: `{"kind": "", "subtitle": ""}` gives 422; PATCH clearing an `Extra / Q&A` volume's kind and subtitle gives 422.
  - `test_epub_title_override_and_filename`:
    - Volume `kind "Vol", index 3, subtitle "A/B"` in series `S` with a chapter that has content: the export's `Content-Disposition` filename is `S - Vol 3 - A_B.epub`.
    - With `epub_title "Mine"` set, the filename is `Mine.epub` and the built EPUB's `dc:title` is `Mine`.
  - `test_markdown_export_label_uses_full_title`: the export label for a volume is its `full_title`. Assert on the ZIP name or label the way `tests/test_exports.py` already does.
- [ ] **Step 2: Write the failing migration test** `tests/test_migration_volume_naming.py`, using the `test_migration_orphans.py` pattern: load the module by path and call its data functions inside the test transaction.
  - Re-add a `title` column with `ALTER TABLE volumes ADD COLUMN title text`. Insert volumes titled `"Volume 1"`, `"Vol. 2.5 - Extra Bits"`, `"第3巻"`, `"Vol 3"` and `"Prologue"` with `volume_order` 1–5, and give `"Volume 1"` `epub_title "Keep"`.
  - Give a chapter in `"Vol. 2.5 - Extra Bits"` `wp_post_url = "https://x/p"`.
  - Call `_split_titles(conn)` and `_freeze_wp_names(conn)`.
  - **Expected `(kind, index, subtitle)`:**
    - `("Volume", 1, "")`
    - `("Volume", 2.5, "Extra Bits")`
    - `("Volume", 3, "")`
    - `("", None, "Vol 3")` (clash)
    - `("", None, "Prologue")`
  - `volume_order` is unchanged and `epub_title == "Keep"`. Only the 2.5 volume has `wp_volume_title == "Vol. 2.5 - Extra Bits"`; the rest are `None`.
- [ ] **Step 3: Run them and see them fail.** Run `pytest tests/test_volume_names_api.py tests/test_migration_volume_naming.py -v`. Expected: FAIL (unknown fields, missing migration).
- [ ] **Step 4: Change the models and autogenerate the revision.** Run `alembic revision --autogenerate -m "volume naming"`.
  - Before `title` is dropped, add the data step to `upgrade()` as two module-level functions taking a `Connection`. `_split_titles` parses each series' volumes in `volume_order, id` order with `parse_title(title, series.title)`; a clash on `(lower(kind), index)` stores `("", None, title)`. `_freeze_wp_names` sets `wp_volume_title = title` where a chapter in the volume has `wp_post_url <> ''` or `wp_published_at IS NOT NULL`.
  - Order the steps: add columns nullable/defaulted, data step, drop the `title` constraint and column, create the indexes.
  - `downgrade()` re-adds `title`, fills it from `label()`, suffixing ` (n)` on clashes, and restores the old constraint.
- [ ] **Step 5: Sweep the readers.**
  - **API:**
    - `publish.py:112` and `publish_job.py:88` send `volume.wp_name`.
    - `epub.py:266` uses `volume.full_title` and the filename `sanitize_filename(volume.full_title) or 'volume'`.
    - `exports.py:64` uses `volume.full_title`.
    - The merge docstring says "keeps its own kind, index, subtitle, EPUB details and WordPress name".
  - **Creation paths, temporarily:**
    - `group_volume` builds `kind="", subtitle=heading`, suffixing ` (n)` while `(series, '', subtitle)` with a null index is taken.
    - EPUB `_volume` and tadb `_volume` look up by `parse_title(title, series.title)` and that key.
  - **Tests and seed:** replace `Volume(title="X")` with `Volume(subtitle="X")`. The default kind `"Volume"` with a null index keeps them unique. Assertions on a volume's visible name read `label`. In `e2e_seed.py`, seed `"Vol A"` and `"Vol existing"` as `kind="", subtitle="Vol A"` and `kind="", subtitle="Vol existing"`, so the labels the specs match on stay the same (`library.spec.ts` uses `/^Vol A/`).
- [ ] **Step 6: Run everything and see it pass.** Run `alembic upgrade head && alembic downgrade -1 && alembic upgrade head && pytest && ruff check .`. Expected: the migration round-trips, all tests PASS, no lint errors.
- [ ] **Step 7: Commit.** Run `git add -A api migrations tests tools && git commit -m "feat(api): volumes have kind, decimal index and subtitle instead of a title"`.

---

### Task 4: Series title template API

**Files:**
- Modify: `api/schemas/series.py`
- Test: `tests/test_series.py` (append)

**Interfaces:**
- Consumes: `validate_template` and the `Series.volume_title_template_effective` property (Task 3).
- Produces: `SeriesOut.volume_title_template: str` and `SeriesOut.volume_title_template_effective: str`; `SeriesUpdate.volume_title_template: str | None` (≤ 300 chars, validated; `""` resets to the default).

- [ ] **Step 1: Write the failing tests.**
  - `test_template_round_trip`: PATCH `{"volume_title_template": "{series} Vol. {index}"}` returns 200, and a volume's `full_title` in `GET /series/{id}/volumes` becomes `S Vol. 2`.
  - `test_template_rejects_unknown_placeholder`: `"{Series}"` gives 422 and the detail mentions `Series`.
  - `test_template_blank_means_default`: PATCH `""` makes `volume_title_template_effective == DEFAULT_TEMPLATE`.
- [ ] **Step 2: Run them and see them fail.** Run `pytest tests/test_series.py -k template -v`. Expected: FAIL.
- [ ] **Step 3: Implement the two schema fields and a `field_validator`** that calls `validate_template` and re-raises its `ValueError`.
- [ ] **Step 4: Run them and see them pass.** Same command. Expected: PASS.
- [ ] **Step 5: Commit.** Run `git commit -am "feat(api): per-series volume title template"`.

---

### Task 5: Placement, reorder and Sort by number

**Files:**
- Create: `api/volume_order.py`
- Modify: `api/routers/volumes.py` (create/patch call `place`; two new routes), `api/schemas/volumes.py` (`VolumeIds`)
- Test: `tests/test_volume_order.py`

**Interfaces:**
- Consumes: `sort_key` (Task 1); `arrange(db, series)` (`api/library.py`).
- Produces:
  - `place(db: Session, volume: Volume) -> None`: positions `volume` among its series' volumes and renumbers `volume_order` 1..N. The caller flushes and runs `arrange`.
  - `reorder(db, series, ids: list[int]) -> list[Volume]`: raises `HTTPException(422, "volume_ids: list every volume of this series once")` on a stale or duplicate list.
  - `sort_by_number(db, series) -> list[Volume]`.
  - Routes: `PUT /series/{series_id}/volumes/order` (body `VolumeIds {volume_ids: list[int]}`) and `POST /series/{series_id}/volumes/sort`. Both return `list[VolumeOut]` in the new order and run `arrange()`.

- [ ] **Step 1: Write the failing tests.** Build volumes through the API so `place` runs.
  - `test_new_volume_goes_after_its_kind`: create V1, V2, V3, then `Side Story 1`. Reorder to V1, V2, V3, SS1 and V4 is created after. Then create V5 and SS2. The order is V1, V2, V3, SS1, SS2, V4, V5.
  - `test_first_of_kind_uses_sort_key`: with V1, V2, create `Extra` (no index). It goes last. `kind ""` + `"Prologue"` goes after `Extra`.
  - `test_index_edit_moves_only_that_volume`: from V1, SS1 (dragged first), V2, V3, PATCH V3's index to `1.5`. The order is SS1, V1, V1.5, V2: SS1 stays first.
  - `test_patch_without_name_change_does_not_move`: PATCH only `epub_author`; the order is unchanged.
  - `test_explicit_volume_order_on_create_still_wins`: the existing behaviour is kept.
  - `test_reorder_stale_list_422`: omit one id, then repeat an id. Both give 422 and the order is unchanged.
  - `test_sort_by_number`: after a reorder, POST sort gives the Volume kinds by index, then other kinds alphabetically, then empty kind.
  - `test_reorder_and_sort_rearrange_chapters`: in a non-syosetu series, chapters' `series_order` follows the new volume order, through `arrange`.
  - `test_reorder_other_users_series_404`.
- [ ] **Step 2: Run them and see them fail.** Run `pytest tests/test_volume_order.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `api/volume_order.py`** with the spec's rule. Siblings are the other volumes with the same `kind.casefold()`. Compare `(sort_key(kind, index), id)`.
  1. If any sibling compares lower, insert after the highest-positioned of them.
  2. Otherwise, if any sibling compares higher, insert before the lowest-positioned of them.
  3. Otherwise, insert after the highest-positioned volume whose `sort_key` is lower, or first if there is none.

  In `create_volume`, call `place` when `body.volume_order is None`; in `update_volume`, call it when `kind` or `volume_index` changed. Either way, follow it with `flush` and `arrange` as today.
- [ ] **Step 4: Run them and see them pass.** Run `pytest tests/test_volume_order.py tests/test_volumes.py tests/test_volume_names_api.py -v`. Expected: PASS.
- [ ] **Step 5: Commit.** Run `git add api tests && git commit -m "feat(api): place volumes by kind and index; reorder and sort endpoints"`.

---

### Task 6: Creation paths by the new key (EPUB import, ta.db import, syosetu)

**Files:**
- Modify: `api/routers/epub.py` (`import_epub` form, `_volume`)
- Create: `api/core/tadb_volumes.py` (move `_volume_meta`, `_merge_volume_meta` and `_volume` out of `tadb_rows.py`)
- Modify: `api/core/tadb_rows.py` (import from the new module), `api/fetch_job.py:group_volume`
- Test: `tests/test_epub_api.py`, `tests/test_import_tadb.py`, `tests/test_scrape_api.py`, `tests/test_volumes_merge.py` (append)

**Interfaces:**
- Consumes: `parse_title`, `place` (Tasks 1 and 5).
- Produces:
  - **EPUB import form:** `volume_kind: str = Form("Volume", max_length=40)`, `volume_index: str = Form("", max_length=20)`, `volume_subtitle: str = Form("", max_length=300)`, replacing `volume_title`.
    - An index that isn't `^\d+(\.\d{1,3})?$` gives 422 `volume_index: a number like 3 or 3.5`.
    - All three empty gives 422 `give a kind, number or subtitle`.
    - NUL in any field is refused via `reject_nul`.
  - **The lookup key, everywhere:** `(series_id, lower(kind), volume_index)` when the index is set, else `(series_id, lower(kind), subtitle)` with a null index.

- [ ] **Step 1: Write the failing tests.**
  - `test_epub_import_reuses_volume_by_kind_and_index`: importing twice with `Volume`/`2`, the second time with subtitle `"Other"`, lands in the same volume and keeps the first subtitle.
  - `test_epub_import_new_volume_is_placed`: with V1, V3, importing `Volume`/`2` creates a volume between them.
  - `test_epub_import_bad_index_422`: `"2,5"` gives 422.
  - `test_tadb_volume_titles_are_parsed`: desktop titles `"Volume 2"` and `"Prologue"` give `("Volume", 2, "")` and `("", None, "Prologue")`. A re-import reuses both and creates no new volumes.
  - `test_heading_volume_is_unnamed_kind`:
    - A fetch with headings 第一章 and 第二章 creates volumes with `kind == ""`, a null index and subtitles equal to the headings, in arc order.
    - A pre-existing hand-made `("", None, "第一章")` volume makes the new one `"第一章 (2)"`.
  - `test_merge_keeps_survivor_names`: merging `Side Story 1` into `Volume 2` leaves `Volume 2`'s kind, index, subtitle and `wp_volume_title`.
- [ ] **Step 2: Run them and see them fail.** Run `pytest tests/test_epub_api.py tests/test_import_tadb.py tests/test_scrape_api.py tests/test_volumes_merge.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - **EPUB `_volume(db, series, name: ParsedName, meta)`:** look up by the key; otherwise create the volume and call `place`.
  - **ta.db `_volume`:** parse with `parse_title(title, series.title)`. The import cache stays keyed by the original desktop title. Order stays "append in desktop order", as today; no `place`, so the desktop order survives. Report messages use `volume.label`.
  - **`group_volume`:** after creating the volume, call `place` instead of `max+1`. An empty-kind, unnumbered volume then goes after the last empty-kind volume, otherwise at the end.
  - Keep `tadb_rows.py` and `tadb_volumes.py` each under 400 lines.
- [ ] **Step 4: Run them and see them pass.** Run `pytest && ruff check .`. Expected: PASS.
- [ ] **Step 5: Commit.** Run `git add api tests && git commit -m "feat(api): imports and syosetu fetch find volumes by kind and number"`.

---

### Task 7: Freeze the WordPress volume name

**Files:**
- Modify: `api/publish.py` (new `freeze_volume_name`), `api/routers/wp.py:117`, `api/publish_job.py:50` and `publish_illustrations`
- Test: `tests/test_wp_volume_name.py`

**Interfaces:**
- Consumes: `Volume.wp_name` (Task 3).
- Produces: `freeze_volume_name(db: Session, volume_id: int | None) -> None`. If the volume exists and its `wp_volume_title is None`, it sets that to `wp_label(...)`, which is exactly what `wp_name` returned and was just sent.

- [ ] **Step 1: Write the failing tests.** Use the existing `httpx.MockTransport` WordPress fixtures from `tests/test_wp_publish.py` and `tests/test_wp_jobs.py`, and capture request bodies.
  - `test_first_chapter_publish_freezes_name`: a volume `Volume 3 / The Journey`, publishing one chapter, sends `volume_title == "Volume 3 - The Journey"` and then `wp_volume_title == "Volume 3 - The Journey"`.
  - `test_frozen_name_survives_renames`: after freezing, PATCH the subtitle to `"New"` and the series template. The next chapter publish **and** the illustrations job both send `"Volume 3 - The Journey"`.
  - `test_failed_or_409_publish_does_not_freeze`: when WordPress reports neither created nor updated, `wp_volume_title` stays `None`.
  - `test_illustrations_first_publish_freezes`: freezing happens after the first successful batch.
  - `test_volume_out_shows_frozen_name`: `GET /series/{id}/volumes` includes `wp_volume_title`.
- [ ] **Step 2: Run them and see them fail.** Run `pytest tests/test_wp_volume_name.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Call `freeze_volume_name(db, doc.volume_id)` where `publish.record(...)` returned `True` (both call sites), and in `publish_illustrations` after the first successful `wp_http.publish_illustrations`.
- [ ] **Step 4: Run them and see them pass.** Run `pytest tests/test_wp_volume_name.py tests/test_wp_publish.py tests/test_wp_jobs.py -v`. Expected: PASS.
- [ ] **Step 5: Commit.** Run `git add api tests && git commit -m "feat(api): freeze the WordPress volume name on first publish"`.

---

### Task 8: SPA name fields, labels and the template setting

**Files:**
- Modify: `web/src/api/schema.d.ts` (via `npm run gen:api`)
- Modify: `web/src/library/VolumeDetails.tsx`, `NewVolumeDialog.tsx`, `epubBook.tsx`, `ImportEpub.tsx` (if it passes a series title), `SeriesSettings.tsx`, `VolumeList.tsx:7`, `VolumePane.tsx:34,108`, `VolumesTab.tsx:66`, `MoveDialog.tsx:56`, `MergeVolumesDialog.tsx:30`, `VolumeDetails.tsx:74`
- Test: `web/src/library/volumeNames.test.ts` (already covers the logic). The UI is covered by Task 9's e2e.

**Interfaces:**
- Consumes: Task 2 (`render`, `label`, `parseTitle`, `templateError`, `nextVolumeIndex`, `DEFAULT_TEMPLATE`); `VolumeOut` and `SeriesOut` from Tasks 3, 4 and 7.
- Produces: a shared `VolumeNameFields({ value, onChange, kinds })` component in `web/src/library/VolumeNameFields.tsx`, used by Details, New volume and EPUB import. Its value is `{kind: string; index: string; subtitle: string}`.

- [ ] **Step 1: Regenerate the API types.** Run `cd web && npm run gen:api && npx tsc --noEmit`. Expected: type errors at every `volume.title` use. That's the to-do list for this task.
- [ ] **Step 2: Build `VolumeNameFields.tsx`.**
  - **Kind:** `<input list>` with a `<datalist>` of `Volume`, `Side Story`, `Short Stories` and `Extra`, plus the series' distinct kinds.
  - **Index:** `inputmode="decimal"`, `pattern="\d+(\.\d{1,3})?"`, may be empty.
  - **Subtitle:** a plain input.
- [ ] **Step 3: Volume details.** Use `VolumeNameFields`.
  - Set the EPUB title input's `placeholder` to the live `render(series.volume_title_template_effective, …)`.
  - When `wp_volume_title` is set, show it read-only, labelled `WordPress volume name` with the note `Fixed after first publish; WordPress finds the volume's pages by it.`
  - Send `volume_index: index || null`.
- [ ] **Step 4: New volume.** Use `VolumeNameFields`, defaulting to `kind "Volume"` and `index nextVolumeIndex(volumes)`.
- [ ] **Step 5: EPUB import.** In `useEpubBook`, replace the `volumeTitle` state with a `VolumeName`, pre-filled with `parseTitle(b.title, seriesTitle)`. `seriesTitle` is a new optional argument; `NewVolumeDialog` passes `series.title`. `importForm` sends `volume_kind`, `volume_index` and `volume_subtitle`.
- [ ] **Step 6: Series Settings.** Add a `Volume title template` input in the existing form. Its placeholder is `DEFAULT_TEMPLATE`, with the help text `Placeholders: {series} {kind} {index} {subtitle}`. Show `templateError(...)` inline and disable Save while it's non-null. Preview it with `render(...)` against the series' first volume by `volume_order`, or the sample `{kind:"Volume", index:"1", subtitle:"Subtitle"}`. Save sends `volume_title_template`.
- [ ] **Step 7: Use the label everywhere.** Replace the `volume.title` reads listed under Files with `volume.label`. The EPUB download name in `VolumePane.tsx:34` is `${volume.full_title}.epub`.
- [ ] **Step 8: Verify.** Run `cd web && npx tsc --noEmit && npm test`. Then, with `docker compose --profile dev up`, check in the browser:
  - In Volume details, set the index to `3.5`. The list shows `Volume 3.5 · …` and the EPUB title placeholder updates as you type.
  - A bad template shows the error and blocks Save.
- [ ] **Step 9: Commit.** Run `git add web && git commit -m "feat(web): volume kind, number and subtitle; series title template"`.

---

### Task 9: SPA volume drag, Sort by number, and e2e

**Files:**
- Modify: `web/src/library/VolumeList.tsx` (add `VOLUME_MIME` next to `CHAPTER_MIME`; a grip per row), `VolumesTab.tsx` (`onMoveVolume` calls `PUT …/volumes/order` with `moveItem` from `order.ts`), `VolumePane.tsx` (⋯ menu item `Sort volumes by number` with `ConfirmDialog`)
- Modify: `tools/e2e_seed.py` (new series `E2E volume naming series` with volumes `Volume 1`, `Volume 2` and `Volume 3`, one chapter each)
- Test: `web/e2e/volumes.spec.ts` (new; it owns the seed above)

**Interfaces:**
- Consumes: Task 5 routes; `moveItem(items, from, to)` (`web/src/library/order.ts`).
- Produces: none for later tasks.

- [ ] **Step 1: Seed and write the failing e2e** `web/e2e/volumes.spec.ts`:
  - `editing an index moves the volume`: open the series and set Volume 3's index to `1.5` in Volume details. The list order is `Volume 1`, `Volume 1.5`, `Volume 2`.
  - `a dragged volume keeps its place`: drag `Volume 1` below `Volume 2` with `locator.dragTo`. Create a new volume, which defaults to the next number. The order is `Volume 2`, `Volume 1`, `Volume 1.5`, `Volume 4`.
  - `Sort by number restores order`: ⋯ → `Sort volumes by number` → confirm. The order is `Volume 1`, `Volume 1.5`, `Volume 2`, `Volume 4`.
  - `a chapter can still be dropped on a volume`: drag a chapter row onto `Volume 2`. It moves, and no volume reorder request is sent.
- [ ] **Step 2: Run it and see it fail.** Run `cd web && npx playwright test e2e/volumes.spec.ts` with the e2e database reset per `CLAUDE.md`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Volume rows get a `draggable` grip that sets `VOLUME_MIME` to the volume id. They are hidden, with no drag at all, in Select mode and on the "No volume" row.
  - `onDragOver` accepts `VOLUME_MIME` only on volume rows, and `CHAPTER_MIME` as today.
  - On a drop, call `onMoveVolume(fromId, toId)`, then invalidate the library queries.
- [ ] **Step 4: Run it and see it pass.** Run `npx playwright test e2e/volumes.spec.ts e2e/library.spec.ts e2e/import.spec.ts`. Expected: PASS.
- [ ] **Step 5: Commit.** Run `git add web tools && git commit -m "feat(web): drag volumes to reorder; sort volumes by number"`.

---

### Task 10: Docs

**Files:**
- Modify: `CLAUDE.md` (a "Volume naming" paragraph after "Syosetu heading volumes"), `docs/TODO.md`

- [ ] **Step 1: Update `CLAUDE.md`.** In ≤ 6 lines, cover:
  - kind/index/subtitle
  - `api/core/volume_names.py` and its TS twin, sharing `volumeNames.cases.json`
  - `full_title` and the template
  - `api/volume_order.place` as the only way a new volume gets its position
  - `wp_volume_title` frozen on first publish
- [ ] **Step 2: Update `docs/TODO.md`.** Remove "WordPress plugin: how it uses `volume_title`" and add "EPUB: series position metadata" (`calibre:series_index` / EPUB3 `belongs-to-collection` with `group-position` from `volume_index`).
- [ ] **Step 3: Run the full suite.** Run `pytest && ruff check . && cd web && npm test && npx tsc --noEmit && npm run e2e`. Expected: all PASS.
- [ ] **Step 4: Commit.** Run `git add CLAUDE.md docs/TODO.md && git commit -m "docs: volume naming"`.
