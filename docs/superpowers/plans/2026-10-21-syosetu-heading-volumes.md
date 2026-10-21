# Syosetu Heading Volumes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-series choice of which syosetu headings start a volume (every heading / one marker / off), a confirmed regroup of existing chapters when it changes, and merging several volumes at once.

**Architecture:** One pure module (`api/core/syosetu_volumes.py`) decides markers and each chapter's target heading from the heading sequence stored on the series; the fetch job and a new regroup module both call it, so they always agree. Heading→volume links move from `volumes.syosetu_group` to a `volume_syosetu_groups` table so a merged volume can stand for several headings. The fetch dialog gains the setting select; the volume list gains a select mode with a merge bar.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres, pytest; React 19 + TanStack Query, vitest.

**Spec:** `docs/superpowers/specs/2026-10-21-syosetu-heading-volumes-design.md`

## Global Constraints

- Handlers `flush()`, never `commit()`; routers built with `api_router()`; tenancy via `scoped()` (404 for another user's id in the path, 422 for ids in a body).
- No Python module over ~400 lines (`api/routers/volumes.py` is 178, `api/routers/scrape.py` 120, `api/fetch_job.py` 85).
- Migrations: change the models, autogenerate, then add the data step by hand. Name every new constraint in the model.
- Run backend checks in the tools container (local `alembic` hangs on this machine): `docker compose run --rm tools sh -c "ruff check . && pytest -q"`. Generate migrations against a scratch database: `docker exec ta-web-postgres-1 psql -U ta -d postgres -c "create database ta_autogen_test"`, then `docker compose run --rm -e TA_DATABASE_URL=postgresql+psycopg://ta:ta@postgres:5432/ta_autogen_test tools sh -c "alembic upgrade head && alembic revision --autogenerate -m '<msg>'"`, then `ruff check --fix` the new file and drop the scratch database.
- After API changes: `docker compose run --rm tools sh -c "cd web && npm run gen:api && npx tsc --noEmit && npm test"`.
- Stylesheets use tokens only (`web/src/styles/tokens.css`); new styles go in `web/src/styles/library.css`.
- Mode values: `'all'`, `'marker'`, `'off'`. Constraint name: `uq_volume_syosetu_groups_series_heading`.
- Exact copy:
  - Select label `Volumes from syosetu headings`; options `Every heading`, `Only headings starting with <marker> (<n> headings)` (`1 heading` when n is 1), `Off`.
  - Regroup confirm: `Creates <a> volumes and moves <b> chapters.` plus, when `volumes_emptied > 0`, ` <c> volumes will be left empty; they're kept so switching back finds them.` (singulars: `1 volume`, `1 chapter`).
  - Merge bar `Merge <n> volumes`; dialog `Keep the name and details of:` and `The other <n−1> volumes are deleted; their chapters move into it.`; volume-list buttons `Select` / `Done`.

## Review Focus

- **A saved marker the index no longer uses** (the author renamed headings): the select still shows it, as `(0 headings)`, and fetches put chapters under no starting heading into No volume. → Task 2 `test_offered_markers_keeps_the_saved_one`; Task 3 `test_marker_mode_with_no_starting_heading_creates_no_volumes`.
- **A series fetched before this feature** (`syosetu_headings` null) regrouped: the index is read once, then the preview counts are right and apply moves nothing beyond them. → Task 4 `test_regroup_reads_the_index_once_when_no_sequence_is_stored`.
- **Merging volumes that include the selected one, or merging twice in a row:** the survivor gets every heading row; a fetch of any merged heading lands in it. → Task 6 `test_a_later_fetch_of_a_merged_heading_lands_in_the_survivor`.
- **Shift-click with no previous tick, or upward ranges:** a plain toggle, and ranges work in both directions. → Task 7 vitest `rangeToggle`.
- **Regroup in a series with hand-made volumes and No-volume chapters without headings** (chapters before the first heading): hand-made stays, headingless stays in No volume. → Task 4 `test_regroup_leaves_hand_made_volumes_and_headingless_chapters`.

---

### Task 1: Heading-group table, series columns, migration

**Files:**
- Modify: `api/models/content.py` (Series, Volume; new `VolumeSyosetuGroup`)
- Modify: `api/models/__init__.py` (export `VolumeSyosetuGroup`)
- Modify: `api/schemas/series.py` (`SeriesOut`)
- Modify: `api/fetch_job.py` (`group_volume` uses the table)
- Create: `migrations/versions/<rev>_syosetu_heading_volumes.py`
- Test: `tests/test_scrape_api.py`, `tests/test_series*.py` (whichever holds `SeriesOut` field tests)

**Interfaces:**
- Produces: `Series.syosetu_volume_mode: str` (default `'all'`), `Series.syosetu_volume_marker: str` (default `''`), `Series.syosetu_headings: list[list] | None` (`JSONB`); model `VolumeSyosetuGroup(id, series_id, volume_id, heading)` with `UniqueConstraint("series_id", "heading", name="uq_volume_syosetu_groups_series_heading")`, both FKs `ondelete="CASCADE"`, `volume_id` indexed; `Volume.syosetu_group` removed. `SeriesOut` gains `syosetu_volume_mode: str`, `syosetu_volume_marker: str` (not in `SeriesUpdate`). `group_volume(db, series_id: int, heading: str) -> Volume` keeps its signature and behaviour, looking up and inserting `VolumeSyosetuGroup` rows.

- [ ] **Step 1: Write the failing tests**

```python
def test_series_out_reports_the_heading_setting(app_client, me, make_series):
    s = make_series(me, "S")
    body = app_client.get(f"/series/{s.id}").json()
    assert body["syosetu_volume_mode"] == "all" and body["syosetu_volume_marker"] == ""

def test_patch_series_cannot_set_the_heading_setting(app_client, me, make_series, db):
    s = make_series(me, "S")
    app_client.patch(f"/series/{s.id}", json={"syosetu_volume_mode": "off"})
    db.refresh(s)
    assert s.syosetu_volume_mode == "all"
```

In `tests/test_scrape_api.py`, `test_a_renamed_group_volume_still_receives_its_chapters` stays as is (it must still pass); add `assert db.query(VolumeSyosetuGroup).filter_by(series_id=s.id).count() == 2` to `test_fetch_puts_grouped_chapters_into_volumes_in_order`.

- [ ] **Step 2: Run them and see them fail** — `docker compose run --rm tools pytest -q tests/test_scrape_api.py tests/test_series.py` → FAIL (missing fields / model).
- [ ] **Step 3: Change the models, `SeriesOut` and `group_volume`** as in Interfaces.
- [ ] **Step 4: Autogenerate the migration** (Global Constraints recipe). Then hand-add, in `upgrade()` between `create_table` and `drop_column('volumes','syosetu_group')`: `INSERT INTO volume_syosetu_groups (series_id, volume_id, heading) SELECT series_id, id, syosetu_group FROM volumes WHERE syosetu_group IS NOT NULL`; in `downgrade()` after re-adding the column: `UPDATE volumes v SET syosetu_group = g.heading FROM (SELECT DISTINCT ON (volume_id) volume_id, heading FROM volume_syosetu_groups ORDER BY volume_id, id) g WHERE g.volume_id = v.id`. Verify on the scratch DB: insert a volume with `syosetu_group` at the previous head, `alembic upgrade head`, check the row moved, `alembic downgrade -1`, check it's back, `alembic upgrade head`.
- [ ] **Step 5: Run backend checks** — ruff + full pytest → PASS.
- [ ] **Step 6: Commit** — `feat(api): volume_syosetu_groups table and series heading-volume setting`

### Task 2: Pure heading rules

**Files:**
- Create: `api/core/syosetu_volumes.py`
- Test: `tests/test_core_syosetu_volumes.py`

**Interfaces:**
- Produces:
  - `marker_of(heading: str) -> str | None` — first char after `lstrip()` when `unicodedata.category(ch)[0] in "SP"`.
  - `heading_sequence(chapters: list[dict]) -> list[list]` — from `fetch_series_index` output (index order, `group` key), `[[first_num, heading], …]`, one entry each time `group` changes to a non-None value.
  - `offered_markers(sequence: list[list], saved: str = "") -> list[dict]` — `[{"marker": m, "headings": n}]`, markers starting ≥2 headings, first-appearance order; `saved` (if non-empty and absent) appended with its real count (0 or 1).
  - `targets(sequence: list[list], nums: Iterable[int], mode: str, marker: str) -> dict[int, str | None]` — per spec "Target of a chapter": chapter's heading is the entry with the greatest `first_num` ≤ num; walk entries in order keeping the latest starting heading at or before that entry.

- [ ] **Step 1: Write the failing tests**

```python
SEQ = [[2, "★ 一日"], [5, "◇ 編A"], [8, "★ 二日"], [9, "◇ 編B"], [12, "※"]]

def test_marker_of():
    assert marker_of("  ★ 一日") == "★" and marker_of("※") == "※"
    assert marker_of("第一章") is None and marker_of("1. a") is None and marker_of("あ") is None

def test_heading_sequence_from_index():
    idx = [{"num": 1, "group": None}, {"num": 2, "group": "A"}, {"num": 3, "group": "A"}, {"num": 4, "group": "B"}]
    assert heading_sequence(idx) == [[2, "A"], [4, "B"]]

def test_offered_markers():
    assert offered_markers(SEQ) == [{"marker": "★", "headings": 2}, {"marker": "◇", "headings": 2}]

def test_offered_markers_keeps_the_saved_one():
    assert offered_markers(SEQ, "◎")[-1] == {"marker": "◎", "headings": 0}

def test_targets_all():
    assert targets(SEQ, [1, 2, 6, 12], "all", "") == {1: None, 2: "★ 一日", 6: "◇ 編A", 12: "※"}

def test_targets_marker_uses_earlier_starting_heading_even_if_unfetched():
    assert targets(SEQ, [1, 6, 10, 13], "marker", "★") == {1: None, 6: "★ 一日", 10: "★ 二日", 13: "★ 二日"}

def test_targets_off():
    assert set(targets(SEQ, [2, 9], "off", "").values()) == {None}
```

- [ ] **Step 2: Run and see it fail** — `pytest -q tests/test_core_syosetu_volumes.py` (no DB needed; local venv is fine) → ImportError.
- [ ] **Step 3: Implement** the four functions.
- [ ] **Step 4: Run** → PASS; `ruff check api/core/syosetu_volumes.py`.
- [ ] **Step 5: Commit** — `feat(api): syosetu heading-volume rules`

### Task 3: Fetch follows the setting; chapter list reports markers

**Files:**
- Modify: `api/fetch_job.py`, `api/routers/scrape.py`, `api/schemas/scrape.py`
- Modify: `web/src/library/SyosetuFetch.tsx` (read `data.chapters`), `web/src/api/schema.d.ts` (regenerated)
- Test: `tests/test_scrape_api.py`

**Interfaces:**
- Consumes: Task 1 `group_volume`, series columns; Task 2 `heading_sequence`, `targets`, `offered_markers`.
- Produces: `GET /series/{id}/syosetu/chapters` → `ChapterList {chapters: list[IndexChapter], markers: list[Marker{marker: str, headings: int}]}`. The fetch job sets `series.syosetu_headings = heading_sequence(full_index)` and places each new chapter in `group_volume(db, series.id, t)` where `t = targets(seq, nums, series.syosetu_volume_mode, series.syosetu_volume_marker)[num]` (None → no volume).

- [ ] **Step 1: Write the failing tests** (reuse `GROUPED` / `_grouped_series` / `_fetch` / `_placement`; extend `GROUPED` with a `※` heading pair where needed or add `MARKED`):

```python
MARKED = ('<div class="p-eplist__chapter-title">★ 一日</div>'
          '<div class="p-eplist__sublist"><a href="/n1/1/">One</a></div>'
          '<div class="p-eplist__chapter-title">◇ 編</div>'
          '<div class="p-eplist__sublist"><a href="/n1/2/">Two</a></div>'
          '<div class="p-eplist__chapter-title">★ 二日</div>'
          '<div class="p-eplist__sublist"><a href="/n1/3/">Three</a></div>')

def test_marker_mode_folds_other_headings_into_the_previous_volume(...):
    # series.syosetu_volume_mode = "marker", marker "★"; fetch [2, 3] only
    assert _placement(db, s) == [(2, "★ 一日"), (3, "★ 二日")]
    assert s.syosetu_headings == [[1, "★ 一日"], [2, "◇ 編"], [3, "★ 二日"]]

def test_off_creates_no_volumes(...):          # mode "off": [(1, None), (2, None), (3, None)], 0 Volume rows
def test_marker_mode_with_no_starting_heading_creates_no_volumes(...):  # marker "◎": all None
def test_chapter_list_reports_markers(...):
    body = app_client.get(f"/series/{s.id}/syosetu/chapters").json()
    assert body["markers"] == [{"marker": "★", "headings": 2}]
    assert [c["group"] for c in body["chapters"]] == ["★ 一日", "◇ 編", "★ 二日"]
```

Change `test_chapter_list_marks_fetched` and `test_chapter_list_reports_groups` to read `body["chapters"]`.

- [ ] **Step 2: Run and see them fail.**
- [ ] **Step 3: Implement** job and route per Interfaces; `offered_markers(seq, series.syosetu_volume_marker)` feeds `markers` (the list GET computes `seq` from the index it read but does not store it).
- [ ] **Step 4: Regenerate types; change `SyosetuFetch.tsx`** to use `list.data.chapters` (no new UI yet). Run gen:api + tsc + vitest.
- [ ] **Step 5: Run backend checks** → PASS.
- [ ] **Step 6: Commit** — `feat: syosetu fetch follows the heading-volume setting`

### Task 4: Regroup endpoint

**Files:**
- Create: `api/syosetu_regroup.py`
- Modify: `api/routers/scrape.py` (route), `api/schemas/scrape.py`
- Test: `tests/test_syosetu_regroup.py` (reuse the `site` fixture: move it and the page helpers from `tests/test_scrape_api.py` into `tests/conftest.py` or import them)

**Interfaces:**
- Consumes: Task 2 `targets`, `heading_sequence`; Task 1 `group_volume`, `VolumeSyosetuGroup`; `scrape.fetch_series_index`, the router's `_slot()` and `http_client`.
- Produces: `regroup(db, series: Series, mode: str, marker: str, apply: bool, read_index: Callable[[], list[dict]]) -> RegroupCounts` in `api/syosetu_regroup.py` (`read_index` is called only when `series.syosetu_headings is None`). Route `POST /series/{series_id}/syosetu/volume-headings`, body `VolumeHeadings{mode: Literal["all","marker","off"], marker: str = Field("", max_length=1), apply: bool = False}`, response `RegroupCounts{volumes_created: int, chapters_moved: int, volumes_emptied: int}`. 422: marker not one S/P char when mode is `marker`, or non-empty otherwise. 409 `"a fetch for this series is already queued or running"` when a `syosetu_fetch` job is active (factor the query out of `fetch_series` into `_fetch_active(db, user_id, series_id) -> bool`).

Preview counts must not create volumes: compute target headings, then for each distinct target look up the existing `VolumeSyosetuGroup` row; a missing one counts toward `volumes_created`. Movable = `volume_id is None` or the volume has a group row.

- [ ] **Step 1: Write the failing tests**

```python
def test_preview_changes_nothing_but_the_sequence(...)        # counts right; Volume rows and volume_ids unchanged; mode still "all"
def test_apply_switches_to_marker_and_keeps_emptied_volumes(...)  # 3 'all' volumes → marker ★: chapter 2 into "★ 一日", "◇ 編" kept with 0 chapters, counts {0, 1, 1}
def test_switching_back_reuses_the_renamed_volume(...)        # rename "◇ 編" to "Arc"; back to "all": chapter 2 in "Arc", volumes_created 0
def test_regroup_leaves_hand_made_volumes_and_headingless_chapters(...)
def test_regroup_reads_the_index_once_when_no_sequence_is_stored(...)  # syosetu_headings None; count index GETs in `calls` == 1 across preview + apply
def test_off_sends_heading_chapters_to_no_volume(...)
@pytest.mark.parametrize("body", [{"mode": "marker", "marker": ""}, {"mode": "marker", "marker": "あ"}, {"mode": "all", "marker": "★"}, {"mode": "x"}])
def test_bad_settings_are_422(...)
def test_regroup_is_409_while_a_fetch_runs(...)
def test_regroup_needs_your_series_with_a_url(...)             # 404 other user's; 422 no syosetu_url
```

- [ ] **Step 2: Run and see them fail.**
- [ ] **Step 3: Implement** `regroup` and the route; apply runs `arrange(db, series)` and `flush()`.
- [ ] **Step 4: Run backend checks** → PASS.
- [ ] **Step 5: Commit** — `feat(api): regroup a syosetu series when its heading setting changes`

### Task 5: Setting select in the fetch dialog

**Files:**
- Create: `web/src/library/HeadingVolumes.tsx`, `web/src/library/headingCopy.ts`, `web/src/library/headingCopy.test.ts`
- Modify: `web/src/library/SyosetuFetch.tsx`

**Interfaces:**
- Consumes: Task 3 `ChapterList.markers`, `SeriesOut.syosetu_volume_mode/marker`; Task 4 route and `RegroupCounts`.
- Produces: `HeadingVolumes({ series, markers }: { series: SeriesRow; markers: Marker[] })`, rendered by `SyosetuFetch` above the chapter list when any chapter has a `group`. Pure helpers in `headingCopy.ts`: `optionLabel(m: Marker): string`, `regroupMessage(c: RegroupCounts): string` (exact copy from Global Constraints), `encode(mode, marker) / decode(value)` for the select's value (`"all"`, `"off"`, `"marker:★"`).

Behaviour (spec "Fetch dialog"): change → `apply:false`; all counts 0 → `apply:true` straight away; else `ConfirmDialog` (`title "Regroup chapters"`, `confirmLabel "Regroup"`) → `apply:true`; cancel leaves the select on the saved value (it's controlled by `series`); select disabled while either call runs; on success `invalidateLibrary`. Errors show as `<p className="error" role="alert">`.

- [ ] **Step 1: Write the failing vitest**

```ts
expect(optionLabel({ marker: "★", headings: 14 })).toBe("Only headings starting with ★ (14 headings)");
expect(optionLabel({ marker: "◎", headings: 1 })).toBe("Only headings starting with ◎ (1 heading)");
expect(regroupMessage({ volumes_created: 20, chapters_moved: 1483, volumes_emptied: 78 }))
  .toBe("Creates 20 volumes and moves 1483 chapters. 78 volumes will be left empty; they're kept so switching back finds them.");
expect(regroupMessage({ volumes_created: 1, chapters_moved: 1, volumes_emptied: 0 })).toBe("Creates 1 volume and moves 1 chapter.");
expect(decode(encode("marker", "★"))).toEqual({ mode: "marker", marker: "★" });
```

(Number formatting: plain integers, as above.)

- [ ] **Step 2: Run** `npm test` → FAIL.
- [ ] **Step 3: Implement** helpers and component.
- [ ] **Step 4: Run** gen:api (if not already current) + tsc + vitest → PASS. Then check in the browser (dev SPA :5173, a scratch syosetu series): the select lists the markers, a change shows the confirm with counts, confirm moves chapters; delete the scratch series afterwards.
- [ ] **Step 5: Commit** — `feat(web): choose which syosetu headings start a volume`

### Task 6: Merge endpoint

**Files:**
- Modify: `api/routers/volumes.py`, `api/schemas/volumes.py`
- Test: `tests/test_volumes_merge.py`

**Interfaces:**
- Consumes: Task 1 `VolumeSyosetuGroup`; `arrange` from `api/library.py`.
- Produces: `POST /series/{series_id}/volumes/merge`, body `VolumeMerge{volume_ids: list[int] = Field(min_length=2, max_length=1000), into: int}`, response `VolumeOut` (the survivor). 422 `"volume_ids: every volume must be in this series"` / `"into must be one of volume_ids"` / duplicates collapse then fewer than 2 → `"volume_ids: pick at least two volumes"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_merge_moves_chapters_and_groups_and_deletes_the_others(...)
def test_the_survivor_keeps_its_title_and_epub_fields(...)
def test_merge_keeps_reading_order_in_a_plain_series(...)       # series_order of merged chapters follows prior order, renumbered 1..N
def test_merge_keeps_syosetu_numbers(...)
def test_a_later_fetch_of_a_merged_heading_lands_in_the_survivor(...)  # uses the scrape `site` fixture
@pytest.mark.parametrize(...) def test_bad_merges_are_422(...)  # one id; into not in ids; id from another series
def test_merge_in_another_users_series_is_404(...)
```

- [ ] **Step 2: Run and see them fail.**
- [ ] **Step 3: Implement**: update `Document.volume_id` and `VolumeSyosetuGroup.volume_id` for the others (Core `update`), delete the others, `db.flush(); db.expire_all(); arrange(db, series); db.flush()` (as `delete_volume` does).
- [ ] **Step 4: Run backend checks; regenerate types** → PASS.
- [ ] **Step 5: Commit** — `feat(api): merge several volumes into one`

### Task 7: Select mode and merge in the volume list; docs

**Files:**
- Create: `web/src/library/rangeToggle.ts`, `web/src/library/rangeToggle.test.ts`, `web/src/library/MergeVolumesDialog.tsx`
- Modify: `web/src/library/VolumeList.tsx`, `web/src/library/VolumesTab.tsx`, `web/src/styles/library.css`
- Modify: `CLAUDE.md` (one paragraph after "Library redesign")

**Interfaces:**
- Consumes: Task 6 route.
- Produces: `rangeToggle(order: number[], picked: Set<number>, id: number, anchor: number | null, shift: boolean): Set<number>` — without shift (or no anchor, or anchor not in `order`) toggles `id`; with shift sets every id between anchor and `id` (inclusive, either direction) to the new state of `id`. `VolumeList` gains `selecting: boolean`, `picked: Set<number>`, `onPick(id, shift)`; while `selecting`, entries render a checkbox (not for "No volume"), clicking picks instead of selecting, and drop handlers are not attached. `VolumesTab` owns the state, the `Select`/`Done` button, the `Merge <n> volumes` bar (n ≥ 2), and `MergeVolumesDialog({ volumes, onClose, onMerged })` with a radio per picked volume (default the first in list order) and the exact copy; on success it leaves select mode, `invalidateLibrary`, and selects the survivor.

- [ ] **Step 1: Write the failing vitest**

```ts
const order = [10, 11, 12, 13];
expect([...rangeToggle(order, new Set(), 11, null, true)]).toEqual([11]);
expect([...rangeToggle(order, new Set([10]), 12, 10, true)].sort()).toEqual([10, 11, 12]);
expect([...rangeToggle(order, new Set([13]), 11, 13, true)].sort()).toEqual([11, 12, 13]);
expect([...rangeToggle(order, new Set([10, 11, 12]), 12, 10, true)]).toEqual([]);
expect([...rangeToggle(order, new Set([10]), 10, 10, false)]).toEqual([]);
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** helper, list, tab, dialog, styles.
- [ ] **Step 4: Run** tsc + vitest → PASS; browser check on a scratch series with 4 volumes: Select, tick one, shift-tick a third, merge keeping the second; survivor selected, chapters inside, others gone. Delete the scratch series.
- [ ] **Step 5: Update `CLAUDE.md`** — after the Library redesign paragraph: the heading-volume setting (`series.syosetu_volume_mode/marker`, sequence in `series.syosetu_headings`, rules in `api/core/syosetu_volumes.py`), `volume_syosetu_groups`, regroup (`api/syosetu_regroup.py`, never deletes volumes, never moves chapters out of hand-made volumes), and `POST /series/{id}/volumes/merge`.
- [ ] **Step 6: Full checks** — ruff, pytest, tsc, vitest → PASS.
- [ ] **Step 7: Commit** — `feat(web): merge selected volumes; document heading volumes`
