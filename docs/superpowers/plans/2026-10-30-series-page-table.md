# Series page: chapter table, WordPress tags, Ollama, delete — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The series page's chapter table gets select mode, no overflow, account-saved toggleable columns, a
summary line, honest WordPress tags with a detail popover and Reschedule, series-wide Ollama in Tools, and a
delete that asks what happens to a chapter's images.

**Architecture:** Three small API changes (new counts on `DocumentListItem`, `DELETE /documents/{id}?images=`,
validation for the `series_columns` setting) and SPA work in `web/src/library/` and `web/src/publish/`. Rules
that can be pure (column ids, tag state, summary counts, quick picks) live in pure TS modules with vitest tests;
an account-saved preference hook is built here and reused by the third plan.

**Tech Stack:** FastAPI, SQLAlchemy 2, Postgres; React 19, TanStack Query, react-router; vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-series-page-revision-design.md` (§1, §2, §5 for `series_columns`, §6).
This is the first of three plans; the others are `2026-10-30-series-gallery.md` and
`2026-10-30-account-saved-views.md`.

## Global Constraints

- Every router is built with `api_router()`; handlers `flush()`, never `commit()`.
- User-owned rows by id through `scoped()` / `scoped_image()`; another user's id is 404, never 403.
- No Python module over ~400 lines.
- Stylesheets under `web/src/styles/` use tokens from `tokens.css`, never literal colours.
- Dialogs are `ConfirmDialog` / `PromptDialog` (`web/src/ui/Dialog.tsx`) or native `<dialog>` with `showModal()`;
  no `window.confirm` / `window.prompt` in code this plan touches.
- After any API schema change run `npm run gen:api` (regenerates `web/src/api/schema.d.ts`) and commit it.
- Default columns: `num`, `title`, `progress`, `edited`, `wp`. `num` and `title` cannot be hidden.
- Check status caps at 50 chapters per click.
- E2E seed rows for this plan's spec belong to a series titled `Series page spec`; no seed name contains "E2E chapter".

## Review Focus

1. A chapter whose `wp_status` is `future` but whose `wp_scheduled_for` is NULL (older rows) — the tag must fall
   back to `wp_published_at`, and with both NULL show Scheduled, never crash. Test in Task 5.
2. Delete with `images=move` where the Illustrations chapter already holds an image of the same `src_path` — the
   moved one is renamed, never dropped. Test in Task 2.
3. A saved `series_columns` value naming a column that no longer exists, or a non-list — dropped / defaults, never
   a blank table. Tests in Tasks 3 and 4.
4. Shift-click in select mode across a collapsed block of 100 — only rendered rows' ids take part (the order is
   the shown rows). Test in Task 6.
5. Multi-select delete mixing chapters that can move images and ones that cannot (loose, syosetu) — the
   movable ones move, the others lose their images, and the dialog says how many. Test in Task 8.

---

## File map

| File | Change |
|---|---|
| `api/routers/documents.py` | `list_documents` adds `char_count`, `word_count`, `ollama_waiting`; `delete_document` takes `images` |
| `api/schemas/documents.py` | three fields on `DocumentListItem` |
| `api/image_moves.py` | **new**: `free_name`, `check_can_move`, `move_images` (shared with the Gallery plan) |
| `api/settings_rules.py` | **new**: `check(key, value) -> str \| None`, rule for `series_columns` |
| `api/routers/settings.py` | `put_settings` calls `settings_rules.check` per key |
| `web/src/settings/useAccountPref.ts` | **new**: account-saved preference hook |
| `web/src/library/chapterColumns.ts` (+ test) | **new**: column ids, defaults, `parseColumns` |
| `web/src/library/chapterCells.tsx` | **new**: one cell renderer per column id (keeps `ChapterTable.tsx` small) |
| `web/src/library/chapterPicks.ts` (+ test) | **new**: quick picks |
| `web/src/library/volumeSummary.ts` (+ test) | **new**: summary line counts and text |
| `web/src/publish/wpTag.ts` (+ test) | **new**: tag state and label |
| `web/src/publish/WpTagButton.tsx` | **new**: the tag button + popover |
| `web/src/publish/useWpConfigured.ts` | **new**: `GET /credentials` → has a usable `wordpress` credential |
| `web/src/publish/useStatusCheck.ts` | **new**: the selection bar's Check status loop |
| `web/src/library/DeleteChaptersDialog.tsx` | **new**: delete with the images choice (single and multi) |
| `web/src/library/ChapterTable.tsx`, `ChapterMenu.tsx`, `SeriesTools.tsx`, `SeriesPage.tsx`, `publish/PublishDialog.tsx` | modified |
| `web/src/styles/library.css` | table layout, sticky bars, progress bar, popover |
| `tools/e2e_seed.py`, `web/e2e/series-page.spec.ts` | seed + spec |
| `docs/TODO.md`, `CLAUDE.md` | docs |

---

### Task 1: Character, word and Ollama counts on the chapter list

**Files:**
- Modify: `api/routers/documents.py` (`list_documents`, the `lines` subquery and a new suggestions subquery)
- Modify: `api/schemas/documents.py` (`DocumentListItem`)
- Test: `tests/test_documents.py`

**Interfaces:**
- Produces: `DocumentListItem.char_count: int`, `.word_count: int`, `.ollama_waiting: int` (and in `schema.d.ts`).

- [ ] **Step 1: Write the failing tests**

```python
def test_list_counts_characters_without_whitespace(app_client, me, make_doc):
    make_doc(me, ["一 二　三", "", "  ", "abc"], translated=False)
    row = app_client.get("/documents").json()[0]
    assert row["char_count"] == 6  # 一二三 + abc; blank and whitespace-only lines add nothing

def test_list_counts_translated_words(app_client, me, make_doc):
    make_doc(me, ["a", "b", "c"])  # translations "tr:a" ...
    doc = app_client.get("/documents").json()[0]
    assert doc["word_count"] == 3

def test_word_count_ignores_blank_translations_and_runs_of_space(app_client, db, me, make_doc):
    d = make_doc(me, ["a", "b"], translated=False)
    d_lines = sorted(d.lines, key=lambda l: l.line_number)
    d_lines[0].translated_text = "  Hello   there\nfriend "
    db.flush()
    assert app_client.get("/documents").json()[0]["word_count"] == 3

def test_list_counts_waiting_ollama_suggestions(app_client, db, me, make_doc):
    # two suggestions on one chapter, one already flushed (text NULL) -> 1 waiting
    ...  # build OllamaChunk + two OllamaSuggestion rows as tests/test_ollama_editor.py does
    assert row["ollama_waiting"] == 1
```

(Use the chunk/suggestion builder from `tests/test_ollama_editor.py`; if it is a local helper, copy its shape.
Check `Document.lines` exists as a relationship; if not, select the lines by `document_id`.)

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/test_documents.py -k "counts or word_count" -v` — Expected: FAIL (`KeyError: 'char_count'`).

- [ ] **Step 3: Implement**

In the existing `lines` subquery add, over non-blank lines only (`has_text`):
- `char_count`: `sum(length(regexp_replace(raw_text, '\s', '', 'g')))` (Postgres `\s` with the `g` flag; also
  strip U+3000 — use the pattern `[\s　]`).
- `word_count`: `sum(coalesce(array_length(regexp_split_to_array(trim(translated_text), '\s+'), 1), 0))` filtered
  to `trim(translated_text) != ''` (an empty string would otherwise count 1).

Add a subquery: `OllamaSuggestion` join `Line` on `line_id`, `text IS NOT NULL`, grouped by `Line.document_id`,
`count()` as `ollama_waiting`. Outer-join it like `images`; `coalesce(..., 0)` all three. Add the three `int` fields
to `DocumentListItem`.

- [ ] **Step 4: Run the tests** — `pytest tests/test_documents.py -v` — Expected: PASS.

- [ ] **Step 5: Regenerate types and commit**

```bash
cd web && npm run gen:api && cd ..
git add api/routers/documents.py api/schemas/documents.py tests/test_documents.py web/src/api/schema.d.ts
git commit -m "feat(library): character, word and Ollama counts on the chapter list"
```

---

### Task 2: Delete a chapter and move its images to the Illustrations chapter

**Files:**
- Create: `api/image_moves.py`
- Modify: `api/routers/documents.py` (`delete_document`)
- Test: `tests/test_image_moves.py`

**Interfaces:**
- Consumes: `api.illustrations` (`IllustrationsRule`, `rule_conflict`, `SYOSETU`, `TITLE`, `_syosetu` → make it
  public as `is_syosetu` while here).
- Produces (the Gallery plan uses these):
  - `free_name(held: set[str], name: str) -> str` — `name` if free, else `stem-2.ext`, `stem-3.ext`, …
  - `check_can_move(db: Session, doc: Document) -> Volume` — raises `IllustrationsRule` with
    `NO_VOLUME = "a chapter outside a volume has no Illustrations chapter"`, `illustrations.SYOSETU`, or
    `IS_ILLUSTRATIONS = "these images are already in the Illustrations chapter"`; returns the volume.
  - `move_images(db: Session, user: User, volume: Volume, images: list[DocumentImage], order: int) -> Document`
    — appends to the end of the volume's Illustrations chapter (creating it at `series_order=order`, titled
    `illustrations.TITLE`), renames clashing `src_path`s with `free_name`, keeps `exclude_export`, moves the rows
    (re-point `document_id`, set `anchor_position` to the chapter's max anchor, flush one at a time so ids keep
    order). Returns the Illustrations chapter. The caller arranges.
  - `DELETE /documents/{id}?images=delete|move` (default `delete`).

- [ ] **Step 1: Write the failing tests**

```python
def test_free_name():
    assert free_name(set(), "a.jpg") == "a.jpg"
    assert free_name({"a.jpg"}, "a.jpg") == "a-2.jpg"
    assert free_name({"a.jpg", "a-2.jpg"}, "a.jpg") == "a-3.jpg"
    assert free_name({"noext"}, "noext") == "noext-2"

def test_delete_move_appends_to_existing_illustrations(app_client, db, lib):  # fixture as in test_illustrations_mark
    # V1 has Illustrations chapter `a` with img x.png (anchor 0); chapter t has y.png and x.png
    r = app_client.delete(f"/documents/{t.id}?images=move")
    assert r.status_code == 204
    names = [i.src_path for i in images_of(db, a)]       # ordered by anchor, id
    assert names == ["x.png", "y.png", "x-2.png"]

def test_delete_move_creates_illustrations_chapter(app_client, db, lib): ...
    # no Illustrations chapter in V2: deleting d with images creates one, is_illustrations, title "Illustrations",
    # first in the volume after arrange()

def test_delete_move_refused_outside_volume(app_client, ...):   # 409 NO_VOLUME; chapter NOT deleted
def test_delete_move_refused_in_syosetu_series(app_client, ...): # 409 SYOSETU; chapter NOT deleted
def test_delete_move_refused_for_illustrations_chapter(...):     # 409 IS_ILLUSTRATIONS
def test_delete_default_still_drops_images(app_client, db, ...): # no query -> images gone (cascade)
def test_delete_move_without_images_creates_nothing(...):        # no Illustrations chapter appears
```

- [ ] **Step 2: Run them** — `pytest tests/test_image_moves.py -v` — Expected: FAIL (import error).

- [ ] **Step 3: Implement** `api/image_moves.py` with the interfaces above, and in `delete_document` add
`images: Literal["delete", "move"] = "delete"` (query). For `move`: `check_can_move` first (map
`IllustrationsRule` through `rule_conflict`), load the doc's images (`defer` nothing — bytes move with the row
since we re-point, not copy), `move_images(..., order=doc.series_order)` only when there are any, then delete and
`arrange()` as today.

- [ ] **Step 4: Run** — `pytest tests/test_image_moves.py tests/test_illustrations_mark.py tests/test_documents.py -v` — PASS.

- [ ] **Step 5: Commit**

```bash
cd web && npm run gen:api && cd ..
git add api/image_moves.py api/illustrations.py api/routers/documents.py tests/test_image_moves.py web/src/api/schema.d.ts
git commit -m "feat(library): delete a chapter and move its images to the Illustrations chapter"
```

---

### Task 3: Validate the `series_columns` setting

**Files:**
- Create: `api/settings_rules.py`
- Modify: `api/routers/settings.py` (`put_settings`)
- Test: `tests/test_settings.py` (create if absent; follow `tests/test_auth.py`'s client use)

**Interfaces:**
- Produces: `settings_rules.check(key: str, value: object) -> str | None` (the 422 message, or None). The schedule
  rule moves here too (`schedule.KEY` → `BAD_SCHEDULE`), so `put_settings` loops `check` over `body.items()`.
  `null` always passes (it clears). The third plan adds the library keys to the same table.
- `SERIES_COLUMNS = ("num", "title", "progress", "edited", "wp", "original", "images", "lines", "translated", "chars", "words", "wp_date", "ollama", "source", "added")`

- [ ] **Step 1: Failing tests**

```python
def test_series_columns_accepts_known_ids(app_client, me):
    r = app_client.put("/settings", json={"series_columns": ["num", "title", "images"]})
    assert r.status_code == 200 and r.json()["series_columns"] == ["num", "title", "images"]

@pytest.mark.parametrize("bad", ["images", ["num", 3], ["nope"], {"a": 1}])
def test_series_columns_rejects_malformed(app_client, me, bad):
    assert app_client.put("/settings", json={"series_columns": bad}).status_code == 422

def test_schedule_rule_still_applies(app_client, me):
    assert app_client.put("/settings", json={"ollama_schedule": {"enabled": True}}).status_code == 422
```

(Unknown ids are 422 on write; the SPA drops unknown ids on read — a column removed later must not break an
old saved value, Task 4.)

- [ ] **Step 2: Run** — `pytest tests/test_settings.py -v` — FAIL.
- [ ] **Step 3: Implement** as in Interfaces.
- [ ] **Step 4: Run** — `pytest tests/test_settings.py tests/test_ollama_api.py -v` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(settings): validate series_columns"` (with the three files).

---

### Task 4: Account-saved toggleable columns, fixed layout

**Files:**
- Create: `web/src/settings/useAccountPref.ts`, `web/src/library/chapterColumns.ts`, `chapterColumns.test.ts`,
  `web/src/library/chapterCells.tsx`
- Modify: `web/src/library/ChapterTable.tsx`, `web/src/styles/library.css`

**Interfaces:**
- Produces:
  - `useAccountPref<T>(opts: { key: string; local: string; parse: (v: unknown) => T; fallback: T }): [T, (v: T) => void]`
    — first render reads `localStorage[local]` through `parse` (try/catch, fallback); once `["settings"]` loads,
    the account's value wins (parsed) and is mirrored to `localStorage`; if the account has no value and
    `localStorage` has one, PUT it up once (`{[key]: value}`) — the migration of §5; `set` writes both and
    updates the `["settings"]` query cache. Same query key and fetch as `useThemeSync`.
  - `chapterColumns.ts`: `type ColumnId` (the 15 ids of Task 3), `COLUMNS: { id: ColumnId; label: string; wp?: true }[]`
    in display order, `DEFAULT_COLUMNS: ColumnId[] = ["num","title","progress","edited","wp"]`,
    `parseColumns(v: unknown): ColumnId[]` (non-array → defaults; unknown ids dropped; `num` and `title` always
    added; result in `COLUMNS` order), `shownColumns(chosen: ColumnId[], wpConfigured: boolean): ColumnId[]`
    (drops `wp` and `wp_date` when not configured).
  - `chapterCells.tsx`: `cell(id: ColumnId, ctx: { doc: Doc; group: VolumeGroup; syosetu: boolean; selecting: boolean; queued: Set<number> }): ReactNode`
    and `HEADERS: Record<ColumnId, string>`.

- [ ] **Step 1: Failing vitest**

```ts
test("defaults when nothing or garbage is saved", () => {
  expect(parseColumns(undefined)).toEqual(DEFAULT_COLUMNS);
  expect(parseColumns("images")).toEqual(DEFAULT_COLUMNS);
});
test("drops unknown ids, forces num and title, keeps display order", () => {
  expect(parseColumns(["images", "gone", "progress"])).toEqual(["num", "title", "progress", "images"]);
});
test("hides WordPress columns when WordPress is not set up", () => {
  expect(shownColumns(["num", "title", "wp", "wp_date"], false)).toEqual(["num", "title"]);
});
```

- [ ] **Step 2: Run** — `cd web && npx vitest run src/library/chapterColumns.test.ts` — FAIL.
- [ ] **Step 3: Implement** the modules. Cells: Original title = `doc.title` when `doc.chapter_title && doc.chapter_title !== doc.title`;
  Translated = `${translated_count} / ${line_count}`; WP date = `wp_scheduled_for ?? wp_published_at` as local
  date+time; Ollama = `N waiting` when `ollama_waiting > 0`, else `Queued` when the id is in `queued` (ids from
  `GET /ollama/queue` items of kind `documents`, plus every doc of a queued `volume`/`series` item), else blank;
  Source = a "syosetu" link to `source_url` when set; Added = `created_at` date. The WordPress cell stays the old
  badge until Task 7. In `ChapterTable`: a **Columns ▾** `Menu` with `menuitemcheckbox` items (`aria-checked`),
  `num`/`title` disabled; `colSpan` computed from the shown count.
  CSS: `.chapters { table-layout: fixed; width: 100%; }`, the title cell
  `overflow: hidden; text-overflow: ellipsis; white-space: nowrap;` with `title={shownTitle(d)}`, fixed widths
  per column class (e.g. `.ch-num` 3.5em, numbers 5–6em, dates 7–9em); wrap the table in `.chapters-wrap { overflow-x: auto; }`
  so only the wrapper scrolls on narrow screens; `thead th { position: sticky; top: var(--selbar-h, 0); }`.
  Remove the `overflow-wrap: anywhere` on `.row-link`.
- [ ] **Step 4: Run** — `npx vitest run` and `npm run build` (tsc) — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(series): toggleable chapter columns saved on the account"`.

---

### Task 5: WordPress tag states and the tag popover

**Files:**
- Create: `web/src/publish/wpTag.ts`, `wpTag.test.ts`, `web/src/publish/WpTagButton.tsx`, `web/src/publish/useWpConfigured.ts`
- Modify: `web/src/library/chapterCells.tsx` (WordPress cell), `web/src/publish/PublishDialog.tsx`,
  `web/src/library/ChapterMenu.tsx`, `web/src/library/SeriesPage.tsx`, `web/src/styles/library.css`

**Interfaces:**
- Produces:
  - `type WpTag = "published" | "scheduled" | "due" | "none"`;
    `wpTag(doc: Pick<Doc, "wp_status" | "wp_scheduled_for" | "wp_published_at">, now: Date): WpTag`
    (`future` with `wp_scheduled_for ?? wp_published_at` ≤ now → `due`; `future` with both NULL → `scheduled`);
    `WP_TAG_LABEL: Record<WpTag, string> = { published: "Published", scheduled: "Scheduled", due: "Published?", none: "Not posted" }`;
    `wpTagTone(t: WpTag): "ok" | "warn" | "muted" | ""`.
  - `useWpConfigured(): boolean | undefined` — `GET /credentials`, true when a row has `kind === "wordpress"`,
    `name === ""` and a non-empty `endpoint_url` (the rule of `publish.wp_config`); `undefined` while loading
    (callers treat it as not configured for hiding, so nothing flashes in).
  - `PublishDialog` gains `mode?: "publish" | "reschedule" | "update"`: `reschedule` titles the dialog
    "Reschedule", forces Schedule on, prefills from `doc.wp_scheduled_for`, and sends `confirm_republish: true`
    on the first request; `update` is today's flow titled "Update post". The 409 retry's `window.confirm` becomes
    a `ConfirmDialog` ("Publish anyway").
  - `menuPublishLabel(tag: WpTag): "Publish…" | "Reschedule…" | "Update post…"` in `wpTag.ts`
    (`scheduled` → Reschedule…, `published`/`due` → Update post…).

- [ ] **Step 1: Failing vitest**

```ts
const now = new Date("2026-11-01T12:00:00Z");
test("scheduled in the future", () => expect(wpTag({ wp_status: "future", wp_scheduled_for: "2026-11-02T00:00:00Z", wp_published_at: null }, now)).toBe("scheduled"));
test("scheduled time passed reads Published?", () => expect(wpTag({ wp_status: "future", wp_scheduled_for: "2026-10-31T00:00:00Z", wp_published_at: null }, now)).toBe("due"));
test("falls back to wp_published_at", () => expect(wpTag({ wp_status: "future", wp_scheduled_for: null, wp_published_at: "2026-10-31T00:00:00Z" }, now)).toBe("due"));
test("future with no dates stays scheduled", () => expect(wpTag({ wp_status: "future", wp_scheduled_for: null, wp_published_at: null }, now)).toBe("scheduled"));
test("other statuses", () => { expect(wpTag({ wp_status: "publish", wp_scheduled_for: null, wp_published_at: null }, now)).toBe("published"); expect(wpTag({ wp_status: "", wp_scheduled_for: null, wp_published_at: null }, now)).toBe("none"); });
test("menu label", () => { expect(menuPublishLabel("scheduled")).toBe("Reschedule…"); expect(menuPublishLabel("due")).toBe("Update post…"); });
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Check the plugin before building Reschedule.** In the plugin repo
  (Punllarena/translation-assistant-publisher, the publish REST handler), confirm that publishing an existing
  chapter with a new `scheduled_date` changes the post's date (and keeps it `future`). If it does not, stop and
  report to the user; do not ship Reschedule.
- [ ] **Step 4: Implement.** `WpTagButton({ doc })`: a `button.badge` with the label and tone; on click opens a
  popover (`role="dialog"`, anchored, closes on Esc/outside press, focus returns to the button) that runs the
  `POST /documents/{id}/wp/status` query (same key and `tz` as `PublishDialog`) and shows the live status label,
  the post link, "Checked just now" or `remote_error`, and the stored date labelled "Scheduled for" /
  "Published" (local); when the stored status was `future` and live is `publish`: "Scheduled for <date>, now live".
  After the check, `invalidateLibrary`. Actions: Reschedule… (scheduled, not `is_illustrations`), Update post…
  (published/due, or scheduled Illustrations chapter → `IllustrationsPublish`), Publish… (none), opening
  `PublishDialog` with the mode. `ChapterMenu`'s Publish… item uses `menuPublishLabel` and the same mode, and is
  hidden when not configured. `SeriesPage` hides the WordPress tab when `useWpConfigured()` is not true.
- [ ] **Step 5: Run** — `npx vitest run`, `npm run build` — PASS.
- [ ] **Step 6: Commit** — `git commit -m "feat(series): WordPress tag states, detail popover and Reschedule"`.

---

### Task 6: Select mode, quick picks and the selection bar

**Files:**
- Create: `web/src/library/chapterPicks.ts`, `chapterPicks.test.ts`, `web/src/publish/useStatusCheck.ts`
- Modify: `web/src/library/ChapterTable.tsx`, `web/src/library/chapterCells.tsx`, `web/src/styles/library.css`

**Interfaces:**
- Produces:
  - `type QuickPick = "all" | "none" | "untranslated" | "unposted"` (not `Pick`: that shadows TypeScript's built-in);
    `quickPick(docs: Doc[], pick: QuickPick): Set<number>` (`untranslated`: `progress < 100`; `unposted`: `wp_status === ""`).
  - `useStatusCheck(): { run(ids: number[]): void; stop(): void; done: number; total: number; capped: boolean; running: boolean }`
    — first 50 ids, sequential `POST /documents/{id}/wp/status`, `invalidateLibrary` after each, `capped` when
    more than 50 were given.

- [ ] **Step 1: Failing vitest**

```ts
test("untranslated and unposted picks", () => {
  const docs = [doc({ id: 1, progress: 100, wp_status: "publish" }), doc({ id: 2, progress: 40, wp_status: "" })];
  expect([...quickPick(docs, "untranslated")]).toEqual([2]);
  expect([...quickPick(docs, "unposted")]).toEqual([2]);
  expect(quickPick(docs, "none").size).toBe(0);
});
test("range over shown rows only", () => {
  // order = ids of rendered rows (closed blocks excluded)
  expect([...rangeToggle([1, 2, 5, 6], new Set([1]), 6, 1, true)].sort()).toEqual([1, 2, 5, 6]);
});
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** State `selecting: boolean` and `anchor: number | null`. A **Select** toggle button
  sits beside Columns ▾; ticking a checkbox sets `selecting`. In select mode the row gets
  `onClick={(e) => toggle via rangeToggle(shownIds, ticked, d.id, anchor, e.shiftKey)}` (ignore clicks from inside
  `.ch-menu`), the title renders as plain text (no `Link`, so no stretched `::after`), the grip column is hidden,
  and `user-select: none` on rows avoids shift-click text selection. Esc (keydown on `document` while selecting
  and no dialog open) and Clear leave the mode and clear ticks. The selection bar moves out of `<thead>` into a
  `div.selbar` above the table wrapper, `position: sticky; top: 0`, and sets `--selbar-h` on the wrapper for the
  sticky header. Contents in order: "N selected", Select ▾ (All / None / Untranslated / Not posted —
  All covers closed blocks too), Publish…, Check status (shows "Checking 12 / 50…", Stop, and
  "Checked the first 50 of N" when capped), Export ▾, Move to…, Merge, Delete, spacer, Clear. Publish… and Check
  status only when WordPress is configured. Queue / Flush for Ollama are removed.
- [ ] **Step 4: Run** — `npx vitest run`, `npm run build` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(series): select mode, quick picks and a sticky selection bar"`.

---

### Task 7: Summary line and progress bar

**Files:**
- Create: `web/src/library/volumeSummary.ts`, `volumeSummary.test.ts`
- Modify: `web/src/library/ChapterTable.tsx`, `web/src/library/chapterCells.tsx`, `web/src/styles/library.css`

**Interfaces:**
- Produces: `volumeSummary(docs: Doc[], now: Date): { chapters: number; progress: number; posted: number; scheduled: number; next: string | null }`
  (`posted` counts `published` and `due` tags; `scheduled` counts `scheduled`; `next` = the earliest
  scheduled time still in the future; `progress` via `progressOf`), and
  `summaryText(s, wp: boolean, fmt: (iso: string) => string): string`.

- [ ] **Step 1: Failing vitest**

```ts
test("summary text with WordPress", () => {
  expect(summaryText({ chapters: 42, progress: 68, posted: 30, scheduled: 5, next: "2026-11-02T09:00:00Z" }, true, () => "Nov 2, 18:00"))
    .toBe("42 chapters · 68% translated · 30 posted · 5 scheduled (next: Nov 2, 18:00)");
});
test("without WordPress, and nothing scheduled", () => {
  expect(summaryText({ chapters: 1, progress: 0, posted: 0, scheduled: 0, next: null }, false, String)).toBe("1 chapter · 0% translated");
});
test("a passed schedule counts as posted", () => { /* one future doc dated yesterday -> posted 1, scheduled 0 */ });
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement**; the line shows above the table (date format `Intl.DateTimeFormat` month short, day,
  hour, minute). Progress cell: `<span class="pbar"><span style="width: N%"></span></span> N%` with token colours.
- [ ] **Step 4: Run** — PASS. **Step 5: Commit** — `git commit -m "feat(series): volume summary line and progress bars"`.

---

### Task 8: Ollama in Tools, delete dialog with the images choice

**Files:**
- Create: `web/src/library/DeleteChaptersDialog.tsx`, `web/src/library/deletePlan.ts`, `deletePlan.test.ts`
- Modify: `web/src/library/SeriesTools.tsx`, `ChapterTable.tsx`, `ChapterMenu.tsx`

**Interfaces:**
- Consumes: `DELETE /documents/{id}?images=` (Task 2), `useQueueOllama` / `useFlushOllama`.
- Produces: `deletePlan(docs: Doc[], syosetu: boolean): { withImages: number; movable: number; stuck: number; images: number }`
  (`movable`: has images, `volume_id !== null`, not syosetu, not `is_illustrations`; `stuck`: has images but not movable).
  `DeleteChaptersDialog({ docs, syosetu, onDone, onClose })` — one dialog for one or many chapters.

- [ ] **Step 1: Failing vitest**

```ts
test("mixed selection", () => {
  const docs = [doc({ image_count: 2, volume_id: 1 }), doc({ image_count: 1, volume_id: null }), doc({ image_count: 0 })];
  expect(deletePlan(docs, false)).toEqual({ withImages: 2, movable: 1, stuck: 1, images: 3 });
});
test("syosetu series never moves", () => expect(deletePlan([doc({ image_count: 1, volume_id: 1 })], true).movable).toBe(0));
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** With `withImages === 0` the dialog is today's plain confirm. Otherwise radio
  choices "Move their images to the volume's Illustrations chapter" (only when `movable > 0`; default) and
  "Delete the images too"; when `stuck > 0` a note "N chapters are outside a volume or in a syosetu series; their
  images will be deleted." Deleting sends `images=move` for movable chapters when Move is chosen, else
  `images=delete`; one request per chapter as today; a failure stops and shows its message, the list is
  invalidated either way. Both `ChapterTable` (multi) and `ChapterMenu` (single) use it.
  `SeriesTools` gets an "Ollama" section: **Queue series for Ollama** (`{ kind: "series", series_id }`, shows the
  hook's note/error) and **Flush Ollama output…** (`ConfirmDialog`, "Clear Ollama's saved suggestions for every
  chapter of this series? Your own translation is not touched.", `{ series_id }`).
- [ ] **Step 4: Run** — `npx vitest run`, `npm run build` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(series): Ollama in Tools, delete asks about images"`.

---

### Task 9: E2E and docs

**Files:**
- Modify: `tools/e2e_seed.py`, `docs/TODO.md`, `CLAUDE.md`
- Create: `web/e2e/series-page.spec.ts`

- [ ] **Step 1: Seed** a series `Series page spec` with one volume, three chapters, one titled with 200 characters
  (`"長" * 200`), one with a `document_images` row (a small PNG).
- [ ] **Step 2: Write the spec**:
  - select mode: tick one box, then click another row's title area → it is ticked and the URL is still the series page;
  - shift-click ticks the range;
  - at 1280×800 and at 375×812: `document.documentElement.scrollWidth <= window.innerWidth`;
  - Columns ▾ → tick Images → the Images header shows; reload → still shown;
  - Delete the chapter with an image → the dialog offers "Move their images…"; confirm → Illustrations chapter appears.
- [ ] **Step 3: Run** — `cd web && npm run e2e -- series-page` (venv active, Postgres up) — PASS; then the full
  `npm run e2e` once.
- [ ] **Step 4: Docs.** `docs/TODO.md`: delete "Series page: chapter table columns and Ollama actions"; add
  "WordPress plugin: series-wide status route" (one request for every chapter and illustrations page of a series:
  status, post URL, live date; ta-web then checks on page load, shows live dates, drops the 50 cap). `CLAUDE.md`:
  a "Series page revision" paragraph — select mode, `series_columns` (account setting, `useAccountPref`),
  tag states incl. Published?, Reschedule, `DELETE /documents/{id}?images=move` (`api/image_moves.py`),
  Ollama in Tools, spec path.
- [ ] **Step 5: Full check** — `ruff check .`, `pytest`, `cd web && npm test && npm run build` — all PASS.
- [ ] **Step 6: Commit** — `git commit -m "test(e2e): series page table; docs"`.
