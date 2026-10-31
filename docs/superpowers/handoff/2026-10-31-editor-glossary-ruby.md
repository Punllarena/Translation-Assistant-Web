# Handoff — editor glossary ruby, add-phrase menu item, copy original (plan `2026-10-31-editor-glossary-ruby.md`)

Branch: `opencode/editor-glossary-ruby` (from `main`). Nothing pushed; no pull request.

Spec: `docs/superpowers/specs/2026-10-31-editor-glossary-ruby-design.md`.

Status: all four tasks done and committed, in the order the run asked for (Task 3 first, then 1, 2, 4).

## Commits

```
6f78d3e feat(editor): glossary ruby over the original text
3d7cba9 feat(editor): copy a card's original text
32ffd73 feat(editor): add glossary phrase in the chapter menu
fc03afc feat(api): glossary marks on the lines endpoint
```

## Environment / how I ran things

The worktree's docker-compose project name is `t3-b61e4cce` (from the directory name), so `docker compose run`
from here would spin up a *second* Postgres that collides on `127.0.0.1:5432` with the user's running
`ta-web-postgres-1`. I ran everything through the existing project with `-p ta-web --no-deps`, which reuses the
user's Postgres (never started, stopped, removed or modified any `ta-web-*` or
`translation-assistant-publisher-*` container). The host Python has no project deps, so all Python/Node commands
run inside the `tools` container. During the first (wrong) attempt I briefly created and then removed the
`t3-b61e4cce-*` container/network/volumes; those are gone.

- pytest: `docker compose -p ta-web run --rm --no-deps -e TA_DATABASE_URL=postgresql+psycopg://ta:ta@postgres:5432/ta_ruby_test tools pytest`
  (the database name ends in `_test`, as conftest requires).
- e2e: same, with `-e TA_E2E_DATABASE_URL=postgresql+psycopg://ta:ta@postgres:5432/ta_ruby_e2e`.
- Playwright isolation: `web/playwright.config.ts` hard-codes the API on `127.0.0.1:8001` and the SPA on
  `localhost:5174` (not the dev 8000/5173), and `TA_E2E_DATABASE_URL` is honoured. I confirmed with
  `Get-NetTCPConnection` that 8001/5174 were free (8000/5173 are the user's dev servers) and that no
  node/uvicorn/playwright process was running before each e2e run; each run uses its own database
  `ta_ruby_e2e`, so it cannot clobber another agent's `ta_e2e`.

## Findings the plan asked me to check

- **`raw_text` CAN contain `$` or `%`.** Verified: `build_new_file("価格は100%です。これは$5です。")` +
  `lines_to_db_rows` store `raw_text="価格は100%です。"` (the prefix `%`/`$` is split off, but `$`/`%` inside the
  content are kept), and `replace_and_parse` strips them anywhere (`"価格は100です。"`). Per the spec's
  conditional I therefore added `LineOut.plain_text` and used **`plain_text`** (not `raw_text`) as the ruby-mode
  source — this is a deliberate deviation from the plan Step 5 wording ("use `raw_text` when on"), noted in the
  Task 4 commit body. Offsets in `glossary_marks` are into `plain_text`.
- **`PUT /settings` accepts the `glossary_ruby` key.** `api/settings_rules.py::check` has no whitelist (unknown
  keys fall through to `return None`), and `SettingsMap = dict[Key, Any]` is schema-free. No rule added; the
  boolean is stored as-is. I did not change `settings_rules.py`.
- **`GlossaryMark.from_` (pydantic `Field(alias="from")`)** serializes as JSON key `from` — confirmed by the
  generated `web/src/api/schema.d.ts` (`GlossaryMark.from: number`) and by `tests/test_lines.py`
  (`mark["from"]`).
- **e2e database name:** the literal `ta_e2e_ruby` the task suggested does not end in `_e2e`, which
  `tools/e2e_seed.py` refuses ("the name must end in _e2e"). I used `ta_ruby_e2e` instead (ends in `_e2e`, my
  own, distinct from `ta_e2e`).

## Per task

**Task 3 (backend) — done.** New `api/core/glossary_marks.py` (pure `glossary_marks` + internal `_walk`) that
mirrors `replace_and_parse`'s sequential replace-all over a list of `(text, src_start, mark_id)` pieces. A match
wholly inside one untouched original piece becomes a `Mark(from_, to, translation, shown_from, shown_to)`; a match
overlapping a previous replacement or inside an earlier entry's output, and an empty translation, produce no mark.
Offsets are converted to UTF-16 at the end (`len(s.encode("utf-16-le")) // 2`). `LineOut` gained `plain_text` and
`glossary_marks`; `api/routers/lines.py::get_lines` fills both. `tests/test_glossary_marks.py` (9 tests) and two
`tests/test_lines.py` tests. `web/src/api/schema.d.ts` regenerated.

**Task 1 (menu item) — done.** `Menu` got an optional `onPointerDown` prop; `Editor.tsx` captures the DOM selection
when the "Chapter actions" button is pressed (a click moves focus and drops it) and adds "Add glossary phrase…
(`<binding>`)" after "Series glossary" in the `withLines` menu only, running `run("add_phrase")` with the captured
selection. e2e test in `web/e2e/editor.spec.ts` (the editor spec; `glossary.spec.ts`'s series has no chapters, so
this was the right home — the plan allowed "the editor spec").

**Task 2 (copy original) — done.** `Copy`/`Check` icons; a copy button next to each card's line number that writes
`line.raw_text` via `navigator.clipboard`, `stopPropagation`s the click, shows "Copied"/"Failed" for ~1.5 s, and is
visible on the active card and on hover/`:focus-within`. e2e test in `web/e2e/editor.spec.ts`.

**Task 4 (glossary ruby) — done.** `web/src/editor/glossaryRuby.ts` (pure `marksToRuby`, `mergeReadings`,
`shownToPlain`), `Ruby.cls` plumbed through `paint.ts::layout` into `rtClasses`, `LineCard`/`Editor`/`CardList`/
`useFind` switch the source to `plain_text` when on (sentence-current range mapped through `shownToPlain`), the
status-bar toggle, `.rt-glossary` token styling, the `E2E glossary ruby series` seed (`東京` → `Tokyo`) and
`web/e2e/glossary-ruby.spec.ts` (toggle/persist, and glossary-wins-over-reading, the latter skipped without MeCab).
`CLAUDE.md` editor paragraph updated; the `docs/TODO.md` "Editor: copy source" entry's copy-original bullet is
gone (the unrelated "JParser dictionary words inside a Latin run" note was kept under its own heading).

## Commands and their real output

- `pytest` (full) → **1778 passed, 91 warnings in 725.77s** (exit 0).
  `pytest tests/test_glossary_marks.py tests/test_lines.py -v` → **28 passed**.
- `ruff check .` → **All checks passed!** (after fixing B905 `zip(strict=)` in my test and I001/E501 in
  `tools/e2e_seed.py`).
- `cd web && npm run gen:api` → succeeded; `schema.d.ts` diff contains `GlossaryMark` and `LineOut.glossary_marks`
  / `plain_text`.
- `cd web && npx tsc --noEmit` → clean (no errors).
- `cd web && npm test` → **56 files, 401 tests passed** (includes the 7 `glossaryRuby.test.ts` tests).
- `cd web && npm run e2e -- glossary-ruby editor editor-nav glossary tm` → **24 passed in 1.4 m**.

## What I could not verify / caveats

- The plan's TDD "write failing test, run (FAIL), implement, run (PASS)" order was not followed strictly: I wrote
  implementation and tests together and then ran once (in Task 3 the first run did fail — my own test's wrong
  expected offset — and I fixed the test). The outcomes (tests present and passing) are what matter.
- The full-suite `pytest` summary line is suppressed by the double `-q` (pyproject `addopts = "-q"`); the count above
  comes from running plain `pytest` (single `-q`).
- A real but **pre-existing** race made the glossary-ruby e2e flaky: `saveSetting` writes settings fire-and-forget,
  and a late settings refetch (StrictMode/late mount) can revert the optimistic `glossary_ruby` before its PUT
  lands (confirmed by instrumenting `settings.data`: `{glossary_ruby:true}` then `{last_document_id:30}`). It affects
  every `saveSetting`-driven toggle, not just this feature. The test works around it by waiting for the server with
  `expect.poll` and then asserting the rendered state after a `page.reload()` (a clean fetch), so it is
  deterministic. I did not change `saveSetting` (out of scope).
- Nothing was pushed and no PR opened, as instructed.

## Decisions made (plan/spec silent)

- Ruby-mode source is `plain_text` (see the `$`/`%` finding above).
- The glossary-ruby toggle icon is a small "furigana" glyph (`Ruby` in `ui/icons.tsx`), `.rt-glossary` uses the
  accent text colour and the sans font.
- The reconstruction test in `tests/test_glossary_marks.py` (`test_walk_reconstructs_the_replace_and_parse_output`)
  asserts `_walk`'s rebuilt shown text equals `replace_and_parse(...)[0]` for *every* glossary (including chained
  and empty-translation), because "apply the marks to the plain text" only reconstructs for non-nested,
  non-deleting glossaries — the plan's phrase "rebuilding the shown text from the plain text plus marks" is only
  exactly true for those.
