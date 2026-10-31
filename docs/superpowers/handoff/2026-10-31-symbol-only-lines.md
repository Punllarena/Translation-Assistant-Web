# Symbol-only lines (Ollama + translation memory) — handover

**Branch:** `opencode/symbol-only-lines`, created from `t3/symbol-only-lines` at `b3fe7f1`
(`docs: specs and plans for settings sidebar, symbol-only lines, editor glossary ruby`). Not pushed, no PR.

**Commits** (`git log --oneline b3fe7f1..HEAD`):

```
b556c5e feat(ollama): skip symbol-only lines and fill them with their source
1f8031f feat(tm): no matches for symbol-only lines
```

plus this handover as its own `docs(handoff): symbol-only lines plan` commit. The plan file
(`docs/superpowers/plans/2026-10-31-symbol-only-lines.md`) has every checkbox ticked, each tick committed with
its task. Backend only: nothing under `web/` was touched.

## Environment

- Postgres had to be reached at `127.0.0.1`. `docker compose up -d postgres` **failed** in this worktree:
  `Bind for 127.0.0.1:5432 failed: port is already allocated` — the main checkout's `ta-web-postgres-1`
  (compose project `ta-web`) already publishes `127.0.0.1:5432`. Confirmed it answers as the app's user
  (`docker exec ta-web-postgres-1 psql -U ta -d postgres -c "select version()"` → `PostgreSQL 16.15 …`),
  so the suite used that server. The container and network my failed command created
  (`t3-896e3da6-postgres-1`, `t3-896e3da6_default`) were removed again.
- This worktree has no `.venv`. Runs used `C:\dev\ta-web\.venv\Scripts\python.exe` (Python 3.14.7) with the
  working directory at the worktree; `api.__file__` resolved to the worktree's `api/__init__.py`, so the
  worktree's code is what ran.
- Every run set `$env:TA_DATABASE_URL="postgresql+psycopg://ta:ta@127.0.0.1:5432/ta_test"` first. No
  Playwright run, no `ta_e2e` use.

## Task 1 — `has_letter` and translation memory: done

`has_letter(text) -> bool` is `any(ch.isalpha() for ch in text)`, in `api/core/text.py` next to
`line_has_content`. `tm_matches` (`api/routers/memory.py`) returns `[]` right after the blank check when
`not has_letter(raw)`. Tests: `test_core_text.py::test_has_letter` and
`test_memory_tm.py::test_symbol_only_line_has_no_matches` (a shared `■` line yields nothing; a shared `文。`
line still matches).

Commands and real output:

| Command | Output |
| --- | --- |
| `pytest tests/test_core_text.py tests/test_memory_tm.py -v` (tests only, before the code) | exit 1 — `ImportError: cannot import name 'has_letter'` (collection error) |
| `pytest tests/test_memory_tm.py -q` (before the code) | exit 1 — `1 failed`: `test_symbol_only_line_has_no_matches`, `assert [{'translated_text': 'tr:■', …}] == []` |
| `pytest tests/test_core_text.py tests/test_memory_tm.py -v` (after) | **84 passed in 8.47s** |
| `ruff check api/core/text.py api/routers/memory.py tests/test_core_text.py tests/test_memory_tm.py` | `All checks passed!` |

## Task 2 — Ollama skips and fills symbol-only lines: done

`api/ollama/work.py`:

- `rows_for`: a symbol-only line with no translation gets `known = raw_text.strip()`, so it is never asked
  and still serves as context. The symbol branch sits before the suggestion branch, so a leftover
  suggestion on a scene break cannot make it be asked.
- New `fill_symbol_lines(db, doc) -> int`: selects the chapter's lines whose `translated_text == ""`, keeps
  the non-blank ones with no letter in Python, and writes `translated_text = raw_text.strip()` with one
  `db.execute(update(Line), values)`; flushes only, leaves `translated_at` untouched, returns the count.
- `next_plan` calls `fill_symbol_lines` for each pending chapter, immediately before `rows_for`.
- `lines_left` skips symbol-only lines.
- `plan_for_line` raises `SymbolOnly` (a `ValueError` subclass) with
  `f"line {line_number} has nothing to translate"` for a symbol-only line.
- `_with_work` is unchanged and its docstring now says it is an upper bound that still flags a symbol-only
  line as work, which `next_plan` then fills before reading the chapter (no regex port, as the plan asks).
- A drained non-series item is still deleted through the existing `if item.kind != "series" and not skipped`
  path; `test_next_plan_drains_item_with_only_scene_breaks_left` pins it.

Tests added: in `tests/test_ollama_work.py` the seven the plan names; in `tests/test_ollama_runner.py`
`test_a_symbol_line_is_filled_and_never_asked` (a run over `a b c d` plus a `■` line asks `[0, 1, 2, 3]`,
no request body contains `■`, and the `■` line ends up `translated_text == "■"` with `translated_at` NULL);
in `tests/test_ollama_editor.py` `test_a_symbol_only_line_by_hand_answers_nothing_to_translate`; in
`tests/test_stats_api.py` `test_a_filled_symbol_line_is_no_days_work`.

Commands and real output:

| Command | Output |
| --- | --- |
| `pytest tests/test_ollama_work.py tests/test_ollama_runner.py -v` (tests only, before the code) | exit 1 — `ImportError: cannot import name 'fill_symbol_lines'` (collection error, 15 items collected) |
| `pytest tests/test_ollama_runner.py -q` (before the code) | exit 1 — `1 failed`: `assert [0, 1, 2, 3, 4] == [0, 1, 2, 3]` (`4` was the `■` line) |
| `pytest tests/test_ollama_work.py tests/test_ollama_runner.py -q` (after) | **37 passed** |
| `pytest tests/test_ollama_editor.py -q -k symbol` (after Step 3, before the route change) | exit 1 — `1 failed`: `[('done', {})] == [('error', {'message': 'line 1 has nothing to translate'})]` |
| `pytest tests/test_ollama_editor.py -q` (after the route change) | **14 passed** |
| `pytest tests/test_stats_api.py -q` | **7 passed** |
| `ruff check .` (first) | exit 1 — 1 error, `F841` local `doc` unused in `test_lines_left_ignores_symbol_lines` |
| `ruff check .` (after dropping the assignment) | **All checks passed!** |
| `pytest -q` (whole suite) | `exit=0`, **1779 passed, 91 warnings in 591.66s (0:09:51)** |

The full run came after the lint fix and after every test above. The two documentation edits
(`CLAUDE.md`, `docs/TODO.md`) landed after that run; they touch no code.

## The statistics check (plan Task 2, step 5) — finding, no rule changed

Read both counters:

- **Day heatmap and every `/stats` bucket** (`api/routers/stats.py`) filter on
  `Line.translated_at IS NOT NULL`, not on `translated_text`: `mine = (Line.translated_at.is_not(None),
  Document.user_id == user.id)` feeds the daily history, the series breakdown, the summary, the streaks and
  the comparisons. `translated_at` is stamped only when a line goes from empty to translated through
  `PATCH /documents/{id}/lines` (`api/routers/lines.py`). A copied scene break keeps `translated_at` NULL,
  so it is **not** credited as a day's work. No counting rule was changed.
- **Chapter progress** (`progress()` in `api/routers/documents.py`) counts lines with
  `trimmed raw_text != ''` and `translated_text != ''`, so a filled line **does** count the chapter as
  translated, and publish/export (`calculate_progress` in `api/core/text.py`, `api/routers/exports.py`,
  `api/routers/epub.py`) see it as translated text too.

`tests/test_stats_api.py::test_a_filled_symbol_line_is_no_days_work` proves both sides: after
`fill_symbol_lines` and one hand-translated line, `/stats` `daily` has one paragraph (not two) while the
chapter's `progress` is 100.

## Decisions worth reviewing

1. **`SymbolOnly(ValueError)`** (`api/ollama/work.py`). The plan asks for a `ValueError` "has nothing to
   translate", but the by-hand route (`api/routers/ollama_editor.py`) used to swallow every `ValueError`
   into a silent `("done", {})` — so the message the plan wants reported never reached the card. A
   `ValueError` subclass lets `_prepare` tell a scene break (reported as
   `("error", {"message": "line 1 has nothing to translate"})`, which the card shows via
   `ollamaCardState.ts`) from a blank line, whose behaviour stays exactly as it was (`[("done", {})]`,
   pinned by the untouched `test_stream_blank_line_unset_and_errors`). The spec's "no change to blank-line
   handling" drove this. `_reread`'s `except ValueError` still covers it.
2. **`known` uses `raw_text.strip()`** for a symbol-only line in `rows_for` (the spec left "the stripped
   `replace_and_parse` text or `raw_text.strip()`" to the builder). Chosen so `rows_for` and
   `fill_symbol_lines` agree on the exact string, which is also what the user sees after the fill.
3. **`docs/TODO.md`: the whole entry is gone**, heading included, as "delete the TODO entry" says. (An
   earlier cleanup, `c37b287`, kept a heading with a "fixed in PR #31" note; no stub was left here.)
4. `fill_symbol_lines` filters in Python on `raw.strip()` and `has_letter(raw)`, then issues one
   executemany UPDATE. A `%`-only or whitespace-only line is never filled (whitespace is blank; a bare
   marker is left alone, as before).
5. No schema change, so `npm run gen:api` was not needed; `web/` is untouched.

## What I could not verify

- Playwright / `ta_e2e`: not run (another agent owns the SPA and that database; the task forbade it).
  Nothing user-visible in the SPA was changed, but no browser ever showed the new `error` event on a scene
  break.
- No live Ollama server: the run and by-hand paths are exercised only through the `httpx.MockTransport`
  seams the existing tests use.
- A real chapter imported with legacy marker-bearing `raw_text` (e.g. `raw_text == "%"`) was not exercised;
  by the rule such a line would be filled with `%`. Every line the app writes keeps markers in `prefix`,
  not `raw_text`, so this is a data-historical edge only.
- Nothing was pushed; no CI ran on this branch.
