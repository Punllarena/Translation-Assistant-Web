# Series Page Critique Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the control clutter above the series page's chapter list and fix the naming, grouping and keyboard gaps found by the 2026-11-03 critique.

**Architecture:** SPA-only changes under `web/src/library/` and `web/src/styles/`. No API, schema or migration changes. Each task is a small edit to one component plus the Playwright spec that covers it; one pure helper (`shiftIndex`) gets a vitest.

**Tech Stack:** React, react-router, TanStack Query, Vitest (pure modules), Playwright (UI), plain CSS tokens.

**Spec:** none written; the findings are the 2026-11-03 critique of the series page, stored as the summary snapshot `.impeccable/critique/2026-11-03T00-15-32Z__web-src-library-seriespage-tsx.md`. Related: `docs/superpowers/specs/2026-10-30-series-page-revision-design.md` (it already puts series-wide Ollama queue/flush in Tools).

## Global Constraints

- CSS uses tokens from `web/src/styles/tokens.css`, never literal colours (CLAUDE.md, Phase 7a).
- Dialogs stay `ConfirmDialog` / `PromptDialog` and none closes while its action is busy.
- Select mode keeps its contract: row click ticks, shift-click ranges cover rendered rows only, Esc / Done / Clear leave the mode (`ChapterTable.tsx`).
- Syosetu series keep syosetu's numbering: no drag grip, no reorder (so no Move up / Move down either).
- No Python change: the repo's Python size and commit-boundary rules are untouched.
- Work on a new branch off `main`, not `claude/admin-branding`. Run `npm test`, `npm run e2e` (venv active, Postgres up, `ta_e2e` reset, `TA_DATABASE_URL` / `TA_E2E_DATABASE_URL` at 127.0.0.1) and `npx tsc --noEmit` before the last commit.

## Review Focus

- A series with no volumes: the volume pane shows "Chapters" and its own New volume / Renumber by title buttons; Task 2 must not hide them.
- Select mode entered with zero ticked rows: the user still needs the quick picks (All, Untranslated, Not posted) to start, so Task 3 cannot hide them with the selection bar.
- A volume with 0 chapters: Publish volume… and Queue volume are disabled and must say why.
- A syosetu series: no Move up / Move down on rows.
- A volume over 100 chapters: Move up on the first row of a block, and Move down on the last, must still reorder across the block boundary (indices are global in `shown`).

---

### Task 1: Remove the duplicate series-wide Ollama buttons from the Volumes tab

`SeriesTools.tsx` already has an Ollama section with the same two buttons and the same flush dialog, so this is a deletion.

**Files:**
- Modify: `web/src/library/VolumesTab.tsx:14,30-32,81-87,101-105`
- Test: `web/e2e/series-page.spec.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `VolumesTab` no longer imports `useFlushOllama`, `useQueueOllama` or `ConfirmDialog`. Nothing else imports from it.

- [ ] **Step 1: Write the failing e2e test** in `series-page.spec.ts` (new test after the existing serial ones, before the delete test): `"the Volumes tab has no series-wide Ollama buttons, and the Tools tab has them"`. Assert `getByRole("button", { name: "Queue series for Ollama" })` has count 0 on the Volumes tab, then click the `Tools` tab and assert both "Queue series for Ollama" and "Flush Ollama output…" are visible.
- [ ] **Step 2: Run it to see it fail:** `cd web && npm run e2e -- series-page.spec.ts -g "series-wide Ollama"`. Expected: FAIL on the count-0 assertion.
- [ ] **Step 3: Delete from `VolumesTab.tsx`** the toolbar `<div className="toolbar">` at 81-87, the `ollama` / `flushing` / `flush` state at 30-32, the flush `ConfirmDialog` block at 101-105, and the three imports they used. Keep `assign`, `reorder`, merge and new-volume handling unchanged.
- [ ] **Step 4: Run the test again and `npx tsc --noEmit`.** Expected: PASS, no type errors.
- [ ] **Step 5: Commit**

```bash
git add web/src/library/VolumesTab.tsx web/e2e/series-page.spec.ts
git commit -m "refactor(library): series-wide Ollama actions live only in Tools"
```

---

### Task 2: Volume header menu: group the series-wide items and say why actions are disabled

**Files:**
- Modify: `web/src/library/VolumePane.tsx:76-121`
- Modify: `web/src/styles/controls.css` (after the `.menu [role^="menuitem"]` rules, line ~75)
- Test: `web/e2e/volumes.spec.ts` (the "Sort volumes by number" test around line 53), `web/e2e/library.spec.ts:65-69`

**Interfaces:**
- Consumes: `Menu` from `web/src/ui/Menu.tsx` (children are free JSX; keyboard focus only visits `[role^="menuitem"]`, so a separator and a heading are skipped).
- Produces: CSS classes `.menu-sep` (a 1px `var(--line)` rule with 4px vertical margin) and `.menu-label` (12px, `var(--muted)`, 6px 10px padding), reused by Task 4.

The ⋯ menu order becomes, volume items first: Edit volume details, Queue volume for Ollama, Flush Ollama output…, Use as series cover (when offered); then `<div role="separator" className="menu-sep" />` and `<div className="menu-label">All volumes</div>`; then Renumber all volumes by title (non-syosetu), Sort volumes by number; then another separator; then Delete volume (`danger`) last. Existing item labels and roles do not change, so the Sort e2e keeps working.

For a volume with `count === 0`, the disabled Publish volume… button gets `title="This volume has no chapters yet."`; the disabled Queue volume item gets the same title. A disabled button's `title` is not shown by every browser, but the existing `meta` line ("0 chapters · …") already states the reason on screen, so no extra text is added.

- [ ] **Step 1: Write the failing e2e test** in `volumes.spec.ts`: `"the volume menu lists series-wide items under an All volumes heading, and Delete is last"`. Open the volume actions menu, read `getByRole("menuitem")` texts, assert the last is "Delete volume", and that "Renumber all volumes by title" and "Sort volumes by number" both come after "Use as series cover" or "Flush Ollama output…" and are preceded in the DOM by text "All volumes" (`menu.getByText("All volumes")` visible).
- [ ] **Step 2: Run it to see it fail:** `npm run e2e -- volumes.spec.ts -g "All volumes heading"`. Expected: FAIL, heading not found.
- [ ] **Step 3: Reorder and group the menu items in `VolumePane.tsx`** as described above; add the two CSS classes with token colours.
- [ ] **Step 4: Run `npm run e2e -- volumes.spec.ts library.spec.ts`** and confirm the existing Sort and "Publish volume…" tests still pass.
- [ ] **Step 5: Commit**

```bash
git add web/src/library/VolumePane.tsx web/src/styles/controls.css web/e2e/volumes.spec.ts
git commit -m "feat(library): group series-wide items in the volume menu, Delete last"
```

---

### Task 3: One tools row; the selection bar appears only when rows are ticked

**Files:**
- Modify: `web/src/library/ChapterTable.tsx:181-233`
- Modify: `web/src/styles/library.css:83,107` (`.ch-tools`, `.ch-summary`)
- Test: `web/e2e/series-page.spec.ts`

**Interfaces:**
- Consumes: `QUICK_PICKS`, `QUICK_LABEL`, `quickPick` from `chapterPicks.ts`; `summaryText(volumeSummary(shown, new Date()), wpConfigured, nextSlot)`.
- Produces: `.ch-tools` becomes a flex row with the summary text on the left (`flex: 1`, `.muted`, 13px) and, on the right, Select/Done, then (only while `selecting`) the `Select ▾` quick-pick menu, then `Columns ▾`. The `.ch-summary` paragraph is removed and its rule folded into `.ch-tools`. `barVisible` becomes `n > 0`.

Review Focus pin: entering Select mode with nothing ticked must show the `Select ▾` menu in the tools row, and ticking via it must make the bar appear.

- [ ] **Step 1: Write the failing e2e tests** in `series-page.spec.ts`: (a) `"Select mode with nothing ticked shows quick picks but no selection bar"`: click Select, assert `getByRole("toolbar", { name: "Selected chapters" })` count 0 and `getByRole("button", { name: "Select ▾" })` visible; choose "All" from it and assert the toolbar is visible and "N selected" matches the chapter count. (b) extend the existing select-mode test so `Clear` is still found once a row is ticked.
- [ ] **Step 2: Run them to see them fail:** `npm run e2e -- series-page.spec.ts -g "quick picks"`. Expected: FAIL (toolbar is present with zero ticked).
- [ ] **Step 3: Rewrite the block at 181-194** as a single `div.ch-tools` per the Interfaces block, and drop the quick-pick `Menu` from the bar (it moves to the tools row). Set `barVisible = n > 0`. The Esc handler and `leave()` are untouched.
- [ ] **Step 4: Run `npm run e2e -- series-page.spec.ts narrow.spec.ts`.** `narrow.spec.ts` checks horizontal overflow, which the wider row can break, so confirm it passes at the narrow width (the row must `flex-wrap`).
- [ ] **Step 5: Commit**

```bash
git add web/src/library/ChapterTable.tsx web/src/styles/library.css web/e2e/series-page.spec.ts
git commit -m "feat(library): one chapter tools row; selection bar only with ticked rows"
```

---

### Task 4: Slim selection bar and unambiguous publish names

**Files:**
- Modify: `web/src/library/ChapterTable.tsx:195-232` (the bar from Task 3)
- Modify: `web/e2e/publish.spec.ts:72`
- Test: `web/e2e/series-page.spec.ts`

**Interfaces:**
- Consumes: `.menu-sep` / `.menu-label` from Task 2; `FORMATS`, `exportZip`, `setOpen("move" | "merge")`.
- Produces: bar order `N selected`, `Publish selected…` (primary, only with a WordPress credential), `Check status` / the running "Checking x / y…" + Stop pair, one `Organise ▾` menu, `Delete` (danger), spacer, `Clear`. The `Organise ▾` menu holds, in order: an "Export as" label then three `menuitem`s "TXT", "Markdown", "Ruby Markdown" (same `FORMATS` and `exportZip.mutate(f)`), a separator, `Move to…`, `Merge` (disabled when `n < 2`). While exporting the menu label reads `Exporting…`. The header button in `VolumePane.tsx` keeps the name `Publish volume…`.

- [ ] **Step 1: Write the failing e2e test** in `series-page.spec.ts`: `"the selection bar offers Organise with Move to and Merge, and Merge needs two rows"`. Tick one row; assert `getByRole("button", { name: "Move to…" })` is gone from the bar, open `Organise ▾`, assert menuitem "Merge" has `aria-disabled` or `disabled`, tick a second row, assert it is enabled; press Escape and assert focus returns to the `Organise ▾` button.
- [ ] **Step 2: Run it to see it fail.** Expected: FAIL (`Move to…` is a bar button).
- [ ] **Step 3: Restructure the bar** as above. Keep `Delete` and `Clear` as visible buttons; do not touch the dialogs below.
- [ ] **Step 4: Update `publish.spec.ts:72`** to `{ name: "Publish selected…", exact: true }`, then run `npm run e2e -- series-page.spec.ts publish.spec.ts library.spec.ts`. Expected: PASS (library.spec.ts:47 clicks the exact `Delete` button, which stays).
- [ ] **Step 5: Commit**

```bash
git add web/src/library/ChapterTable.tsx web/e2e/series-page.spec.ts web/e2e/publish.spec.ts
git commit -m "feat(library): slim selection bar, Organise menu, Publish selected"
```

---

### Task 5: Tab order follows the workflow

**Files:**
- Modify: `web/src/library/SeriesPage.tsx:12-19`
- Test: `web/e2e/series-page.spec.ts`

**Interfaces:**
- Produces: `TABS` order Volumes, Glossary, WordPress (`wp: true`), Gallery, Tools, Settings. Tab ids and `?tab=` values do not change, so saved links keep working.

- [ ] **Step 1: Write the failing e2e test:** `"series tabs read Volumes, Glossary, Gallery, Tools, Settings in that order"` (the e2e user has no WordPress credential): `getByRole("tab")` all-text-contents equals that list.
- [ ] **Step 2: Run it to see it fail.** Expected: FAIL (Gallery is second today).
- [ ] **Step 3: Reorder the `TABS` array.**
- [ ] **Step 4: Run `npm run e2e -- series-page.spec.ts gallery.spec.ts`.** Expected: PASS.
- [ ] **Step 5: Commit**

```bash
git add web/src/library/SeriesPage.tsx web/e2e/series-page.spec.ts
git commit -m "refactor(library): series tabs in workflow order"
```

---

### Task 6: Keyboard route to reorder chapters

The drag grip is `aria-hidden` with no alternative. Add Move up / Move down to each row's ⋯ menu.

**Files:**
- Modify: `web/src/library/order.ts` (add `shiftIndex`)
- Create: `web/src/library/order.test.ts` additions (file exists; append)
- Modify: `web/src/library/ChapterMenu.tsx:21` (new optional prop)
- Modify: `web/src/library/ChapterTable.tsx:122-129,164`
- Test: `web/e2e/series-page.spec.ts`

**Interfaces:**
- Produces: `export function shiftIndex(index: number, delta: -1 | 1, length: number): number | null` in `order.ts`: the new index, or `null` when it would fall outside `0..length-1`.
- `ChapterMenu` gains `onMove?: (delta: -1 | 1) => void` and `canMove?: { up: boolean; down: boolean }`. When `onMove` is given it renders `Move up` / `Move down` menuitems (disabled per `canMove`), at the top of the menu. Omitted for syosetu series, so those rows show neither.
- `ChapterTable` passes `onMove={(delta) => { const i = shown.findIndex((x) => x.id === d.id); const to = shiftIndex(i, delta, shown.length); if (to !== null) { dragged.current = d.id; drop(to); } }}`. `drop` already does the optimistic order and `seriesOrder` PUT, and the index is global in `shown`, so it works across 100-chapter blocks.

- [ ] **Step 1: Write the failing vitest** in `order.test.ts`: `shiftIndex(0, -1, 3)` is `null`; `shiftIndex(2, 1, 3)` is `null`; `shiftIndex(1, 1, 3)` is `2`; `shiftIndex(1, -1, 3)` is `0`.
- [ ] **Step 2: Run `cd web && npm test -- order`.** Expected: FAIL, `shiftIndex` not exported.
- [ ] **Step 3: Implement `shiftIndex`**, then run again. Expected: PASS.
- [ ] **Step 4: Write the failing e2e test:** `"Move down in a chapter's menu reorders it and survives a reload"`: open the first row's ⋯ menu, press Move down, assert the row order changed, reload, assert it persisted; also assert a syosetu series' row menu has no "Move up" item (use the seeded Syosetu series from `tools/e2e_seed.py`; if none has chapters, add one row to that spec's own seed, per the E2E conventions).
- [ ] **Step 5: Wire `onMove` / `canMove`** into `ChapterMenu` and `ChapterTable`, omitting both when `syosetu`. Run `npm run e2e -- series-page.spec.ts volumes.spec.ts`. Expected: PASS.
- [ ] **Step 6: Commit**

```bash
git add web/src/library/order.ts web/src/library/order.test.ts web/src/library/ChapterMenu.tsx web/src/library/ChapterTable.tsx web/e2e/series-page.spec.ts tools/e2e_seed.py
git commit -m "feat(library): Move up / Move down in the chapter menu"
```

---

### Task 7: Empty-volume state and final check

**Files:**
- Modify: `web/src/library/VolumePane.tsx:79,95`
- Modify: `CLAUDE.md` (one sentence in the "Series page revision" paragraph)
- Test: `web/e2e/volumes.spec.ts`

**Interfaces:**
- Consumes: Task 2's menu structure.

- [ ] **Step 1: Write the failing e2e test:** `"an empty volume says why Publish volume is disabled"`: create a volume with no chapters (via New volume), assert `getByRole("button", { name: "Publish volume…" })` is disabled and has `title` "This volume has no chapters yet.", and that the volume menu's "Queue volume for Ollama" has the same title.
- [ ] **Step 2: Run it to see it fail.** Expected: FAIL, no title.
- [ ] **Step 3: Add the `title` attributes** (Task 2 specified the copy; if Task 2 already added them, this task only adds the test).
- [ ] **Step 4: Update `CLAUDE.md`'s "Series page revision" paragraph** to say the Volumes tab no longer carries series-wide Ollama actions, the selection bar shows only with ticked rows, and rows have Move up / Move down.
- [ ] **Step 5: Run the full gate:** `cd web && npx tsc --noEmit && npm test && npm run e2e`. Expected: all green. Re-run `/impeccable critique` against the live app to get rendered checks and compare against the 24/36 baseline.
- [ ] **Step 6: Commit**

```bash
git add web/src/library/VolumePane.tsx web/e2e/volumes.spec.ts CLAUDE.md
git commit -m "feat(library): explain disabled actions on an empty volume"
```

---

## Self-Review

- **Coverage:** P1 Ollama duplication → Task 1. P1 header overload and menu scope → Task 2 (+ Task 7 disabled copy). P2 three control rows → Task 3. P2 selection bar and publish naming → Task 4. P3 tab order → Task 5. Persona flags (keyboard reorder, empty volume) → Tasks 6 and 7.
- **Deliberately not done:** moving Renumber / Sort to the Tools tab. They need a volume present and are tested where they are (`volumes.spec.ts`), so they are grouped and labelled instead of relocated. Revisit if the grouped menu still reads as crowded in the live critique.
- **Type consistency:** `shiftIndex` and the `onMove` / `canMove` props are defined in Task 6 only; `.menu-sep` / `.menu-label` are defined in Task 2 and used in Task 4.
- **Order:** Tasks 2 → 4 share CSS; Task 3 must land before Task 4 (it edits the same bar). Tasks 1, 5 are independent of the rest.
- **Open check:** `narrow.spec.ts` overflow after Task 3, and the e2e seed for a syosetu series with chapters in Task 6, are the two places a first run is likely to need adjusting.
