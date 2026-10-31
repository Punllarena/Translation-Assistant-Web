# Editor: Add-phrase Menu Item, Copy Original, Glossary Ruby Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "add glossary phrase" visible in the Chapter actions menu, add a copy-original button to each card, and show glossary translations as ruby over the original text behind a status-bar toggle.

**Architecture:** Tasks 1-2 are small `Editor.tsx` / `LineCard.tsx` edits. Task 3 adds a pure `glossary_marks` function next to `replace_and_parse` and a `glossary_marks` field on `LineOut`. Task 4 turns marks into `Ruby[]` in a pure client module, merges them with reading and author ruby, and wires the `glossary_ruby` setting and toggle.

**Tech Stack:** FastAPI, pydantic, pytest; React, CodeMirror, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-31-editor-glossary-ruby-design.md`

## Global Constraints

- `replace_and_parse` output must not change by a single character; Ollama and JParser keep the replaced text.
- Mark offsets are UTF-16 code units (JavaScript indexes), not Python code points.
- Setting key `glossary_ruby` (boolean), default off, saved with `saveSetting` like `tm_visible`.
- Glossary ruby wins over generated reading ruby; author ruby wins over glossary marks.
- The copy button copies `line.raw_text` as stored (no glossary, no prefix) and does not activate the card.
- Tokens only for colours; no Python module over ~400 lines (`api/core/text.py` is near 330: put the new logic in `api/core/glossary_marks.py`).
- E2E: seed rows in `tools/e2e_seed.py`; names must not contain "E2E chapter"; this spec's glossary phrases occur only in its own series; the `ta_e2e` database is reset once per run.
- Run Tasks in order; commit per task.

## Review Focus

- Overlapping glossary phrases (a short phrase listed before a longer one containing it) mark only what replacement actually replaced.
- A glossary entry with an empty translation produces no mark and no empty ruby.
- A character outside the BMP (`𠮷`) before a match: marks still land on the right characters in the browser.
- Toggling the setting off restores today's replaced-text card exactly, including phrase stepping and find.
- Selecting text, then choosing the menu item, prefills the dialog (the menu click must not drop the selection).

---

### Task 1: "Add glossary phrase…" in Chapter actions

**Files:**
- Modify: `web/src/editor/Editor.tsx` (`chapterMenu`, ~line 202)
- Test: `web/e2e/glossary.spec.ts` (or the editor spec that already covers `PhraseDialog`; extend, do not duplicate seed rows)

**Interfaces:**
- Consumes: `run("add_phrase")` and `useBindings()` already in `Editor.tsx`; the shortcut formatting used by `web/src/settings/ShortcutsPage.tsx`.

- [x] **Step 1: Write the failing e2e test** `"the chapter menu adds a glossary phrase from the selection"`: open a seeded chapter, select a word in a card's source text (triple/double-click), open "Chapter actions", click "Add glossary phrase…"; expect the dialog's phrase field to hold the selection and the menu item text to contain the key binding.
- [x] **Step 2: Run** `cd web && npm run e2e -- glossary`. Expected: the new test FAILS (no such menu item).
- [x] **Step 3: Implement** the item (after "Series glossary", only in the `withLines` menu) with a visible binding hint taken from `useBindings()` for `add_phrase`; if the selection is lost on menu open, capture it in the menu button's `onPointerDown`.
- [x] **Step 4: Run** the same command. Expected: PASS; also `npx tsc --noEmit`.
- [x] **Step 5: Commit** `feat(editor): add glossary phrase in the chapter menu`.

### Task 2: Copy original text button

**Files:**
- Modify: `web/src/editor/LineCard.tsx` (next to `card-number`, line 74), `web/src/styles/editor.css`
- Test: `web/e2e/editor.spec.ts`

**Interfaces:**
- Produces: a button with accessible name `Copy original text` inside each card; after a click it shows a "Copied" state for ~1.5 s.

- [x] **Step 1: Write the failing e2e test** `"copy original text puts the raw source on the clipboard"` (`context.grantPermissions(["clipboard-read","clipboard-write"])`; hover a non-active card, click the button, read `navigator.clipboard.readText()`, expect the line's original text; expect the active card unchanged and "Copied" visible, then gone).
- [x] **Step 2: Run** `cd web && npm run e2e -- editor`. Expected: FAIL.
- [x] **Step 3: Implement** the button: `navigator.clipboard.writeText(line.raw_text)`, `stopPropagation` on click, visible on the active card and on card hover/`:focus-within`, a failed state when the promise rejects. Existing icon set and tokens.
- [x] **Step 4: Run** the same command. Expected: PASS; `npx tsc --noEmit`.
- [x] **Step 5: Commit** `feat(editor): copy a card's original text`.

### Task 3: Server glossary marks

**Files:**
- Create: `api/core/glossary_marks.py`, `tests/test_glossary_marks.py`
- Modify: `api/schemas/lines.py` (`GlossaryMark`, `LineOut.glossary_marks`), `api/routers/lines.py:63-73`, `tests/test_lines.py`, `web/src/api/schema.d.ts` (generated)

**Interfaces:**
- Produces: `glossary_marks(text: str, glossary: list[tuple[str, str]]) -> list[Mark]` where `Mark` is a dataclass `(from_: int, to: int, translation: str, shown_from: int, shown_to: int)`; offsets are UTF-16 code units into `text.replace("$", "").replace("%", "")` (the plain text); marks sorted, non-overlapping. API model `GlossaryMark` has fields `from_` aliased to `from`, `to`, `translation`, `shown_from`, `shown_to`; `LineOut.glossary_marks: list[GlossaryMark]`.

- [x] **Step 1: Write failing tests** in `test_glossary_marks.py`: plain match gives one mark with right offsets; two entries where the shorter is listed first mark only the replaced text; two phrases with one translation; empty translation gives no mark; a phrase inside an earlier entry's output gives no mark and does not raise; `𠮷` before a match shifts offsets by 2 UTF-16 units; for each glossary above, rebuilding the shown text from the plain text plus marks equals `replace_and_parse(text, glossary, [])[0]` (keeps the two functions in step); `test_lines.py`: `GET /documents/{id}/lines` returns `glossary_marks` for a seeded glossary entry.
- [x] **Step 2: Run** `pytest tests/test_glossary_marks.py tests/test_lines.py -v`. Expected: FAIL.
- [x] **Step 3: Implement** `glossary_marks` by walking the glossary in order over a list of pieces (original text with its source range, or inserted output with none), mirroring `replace_and_parse`'s replace-all; matches wholly inside an original piece become marks, others do not; convert code-point offsets to UTF-16 at the end (`len(s.encode("utf-16-le")) // 2`). Fill the field in `get_lines`. Check whether `raw_text` can contain `$` or `%`: if it can, add `plain_text: str` to `LineOut` and test it; if not, state so in the commit body.
- [x] **Step 4: Run** `pytest -q`, `ruff check .`, then `cd web && npm run gen:api`. Expected: pass, clean, schema diff contains `GlossaryMark`.
- [x] **Step 5: Commit** `feat(api): glossary marks on the lines endpoint`.

### Task 4: Glossary ruby in the editor

**Files:**
- Create: `web/src/editor/glossaryRuby.ts`, `web/src/editor/glossaryRuby.test.ts`
- Modify: `web/src/editor/ruby.ts` (optional `cls` on `Ruby`), `web/src/editor/paint.ts` (carry `cls` into `rtClasses`), `web/src/editor/LineCard.tsx`, `web/src/editor/Editor.tsx`, `web/src/editor/useFind.ts`, `web/src/styles/editor.css`, `tools/e2e_seed.py`, `web/e2e/glossary-ruby.spec.ts`, `CLAUDE.md`, `docs/TODO.md`

**Interfaces:**
- Consumes: `LineOut.glossary_marks` (Task 3); `authorRuby`, `generatedRuby`, `Ruby` from `ruby.ts`.
- Produces (pure, in `glossaryRuby.ts`): `marksToRuby(marks: GlossaryMark[], author: Ruby[]): Ruby[]` (each with `cls: "rt-glossary"`, dropping any overlapping an author range or its `hide` range); `mergeReadings(glossary: Ruby[], readings: Ruby[]): Ruby[]` (a reading overlapping a glossary entry is dropped, result sorted by `from`); `shownToPlain(marks: GlossaryMark[], pos: number): number` (maps a replaced-text offset to the original: outside marks shift by the cumulative length difference, inside a mark maps to the mark's start for the left edge and end for the right edge; never throws).

- [ ] **Step 1: Write failing vitest tests** in `glossaryRuby.test.ts`: `marksToRuby` places `rt` text, drops a mark overlapping `authorRuby("漢字(かんじ)")`; `mergeReadings` keeps a reading outside a mark and drops one inside it; `shownToPlain` before, inside and after a mark and with no marks.
- [ ] **Step 2: Run** `cd web && npx vitest run src/editor/glossaryRuby.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement** the three functions and the `cls` plumbing (`Ruby.cls?: string`; `layout` adds it to `rtClasses`).
- [ ] **Step 4: Run** the test. Expected: PASS.
- [ ] **Step 5: Wire the toggle.** In `Editor.tsx`: `const glossaryRuby = settings.data?.glossary_ruby === true;` a button before the "Translation memory" one with `aria-label="Glossary ruby"`, `aria-pressed`, `onClick={() => saveSetting("glossary_ruby", !glossaryRuby)}`; the `shown` text and the `useFind` source field use `raw_text` when on; pass the flag to `LineCard`. In `LineCard.tsx`: when on, `source = line.raw_text`, ruby = `mergeReadings(marksToRuby(line.glossary_marks, authorRuby(source)), readings ?? [])` (glossary ruby on every card, readings active card only), and the `sentence-current` range goes through `shownToPlain`. Off: current code path untouched. Style `.rt-glossary` in `editor.css` with tokens.
- [ ] **Step 6: Seed and e2e.** Add a series to `tools/e2e_seed.py` with a glossary entry whose phrase occurs only in its own chapters. Test `"the toggle shows the original with the glossary on top"`: off shows the replaced text; on shows the original with `rt.rt-glossary` holding the translation; reload keeps it; with a reading aid on, the active card keeps the glossary `rt` and loses the reading over that range.
- [ ] **Step 7: Run** `cd web && npm test && npx tsc --noEmit && npm run e2e -- glossary-ruby editor editor-nav glossary tm`. Expected: all pass.
- [ ] **Step 8: Docs and commit.** `CLAUDE.md` editor paragraph (glossary ruby, the marks field, the setting); delete the TODO entry "Editor: copy source". Commit `feat(editor): glossary ruby over the original text`.
