# Symbol-only Lines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ollama never asks about symbol-only lines (scene breaks) and fills them with their source; translation memory returns nothing for them.

**Architecture:** One pure predicate `has_letter` in `api/core/text.py`; `api/ollama/work.py` uses it in `rows_for`, `lines_left`, `plan_for_line` and a new `fill_symbol_lines` called from `next_plan`; `/tm/matches` returns `[]` for such a line. Backend only, no migration.

**Tech Stack:** FastAPI, SQLAlchemy, pytest.

**Spec:** `docs/superpowers/specs/2026-10-31-symbol-only-lines-design.md`

## Global Constraints

- A symbol-only line is non-blank with no letter (`str.isalpha()`); digits and punctuation are not letters. Blank lines keep current handling.
- A line that already has a translation is never overwritten.
- Copied lines keep `translated_at` NULL.
- `_with_work` SQL stays an upper bound (no regex port); the Python layer is authoritative.
- Writes only `flush()`; the runner owns the transaction. No module over ~400 lines.

## Review Focus

- A line of only `……` or `「……！」` is symbol-only; `ー` alone or a Latin word is not.
- A chapter with only scene breaks left is drained and its queue item removed, with no model request.
- A symbol-only line the user already translated (even differently) is left alone.
- A by-hand ask on a symbol-only line gives a clear error, not a crash.
- A statistics view must not credit the copied lines as a day's work (check how counts work and report if they count `translated_text` alone).

---

### Task 1: `has_letter` and translation memory

**Files:**
- Modify: `api/core/text.py` (add `has_letter`), `api/routers/memory.py:44-50`
- Test: `tests/test_core_text.py`, `tests/test_memory_tm.py`

**Interfaces:**
- Produces: `has_letter(text: str) -> bool` in `api/core/text.py`.

- [x] **Step 1: Write failing tests.** `test_core_text.py::test_has_letter`: true for `"漢字"`, `"ひら"`, `"ー"`, `"abc"`; false for `"■"`, `"◇◇◇"`, `"……"`, `"12"`, `"***"`, `"「……！」"`, `""`, `"  "`. `test_memory_tm.py::test_symbol_only_line_has_no_matches`: two chapters of the user share a `■` line, one translated; the other's `/tm/matches` returns `[]`; and a shared letter-bearing line still returns its match (reuse the file's fixtures).
- [x] **Step 2: Run** `pytest tests/test_core_text.py tests/test_memory_tm.py -v`. Expected: FAIL.
- [x] **Step 3: Implement** `has_letter(text)` as `any(ch.isalpha() for ch in text)`, and in `tm_matches` return `[]` when `not has_letter(raw)` right after the blank check.
- [x] **Step 4: Run the same tests.** Expected: PASS.
- [x] **Step 5: Commit** `feat(tm): no matches for symbol-only lines`.

### Task 2: Ollama skips and fills symbol-only lines

**Files:**
- Modify: `api/ollama/work.py`
- Test: `tests/test_ollama_work.py`, `tests/test_ollama_runner.py`

**Interfaces:**
- Consumes: `has_letter` (Task 1).
- Produces: `fill_symbol_lines(db: Session, doc: Document) -> int` in `work.py` (sets `translated_text = raw_text.strip()` for the document's symbol-only lines with empty `translated_text`, one UPDATE, returns the count, flushes only; `translated_at` untouched).

- [x] **Step 1: Write failing tests** in `test_ollama_work.py` (use its `make_user`, `make_series`, `make_doc` fixtures): `test_rows_symbol_line_is_known` (a `■` line's `Row.known == "■"`); `test_fill_symbol_lines_copies_source_and_keeps_translated_at_null`; `test_fill_symbol_lines_never_overwrites` (a `■` line translated as `"*"` stays `"*"`); `test_lines_left_ignores_symbol_lines`; `test_next_plan_fills_and_never_asks_symbol_lines` (the returned plan's `asked` has no `■` row and the DB line now reads `■`); `test_next_plan_drains_item_with_only_scene_breaks_left` (the queue item is deleted, plan is `None`); `test_plan_for_line_symbol_only_raises` (`ValueError`). In `test_ollama_runner.py` add one test that a run over a chapter with a `■` line sends a prompt not containing `■` as an asked line (follow that file's fake-model seam).
- [x] **Step 2: Run** `pytest tests/test_ollama_work.py tests/test_ollama_runner.py -v`. Expected: the new tests FAIL.
- [x] **Step 3: Implement** in `work.py`: `rows_for` sets `known` to the line's stripped text for a symbol-only line with no translation; `fill_symbol_lines` as above (SQL UPDATE by line ids found with `has_letter` in Python); `next_plan` calls it before `rows_for` for each pending chapter; `lines_left` skips symbol-only lines; `plan_for_line` raises `ValueError(f"line {line_number} has nothing to translate")` for one; update the `_with_work` docstring to say symbol-only lines are filled after it flags them.
- [x] **Step 4: Check the by-hand route** `api/routers/ollama_editor.py` reports that `ValueError` message sensibly (a test in `tests/test_ollama_editor.py` that asking for a `■` line answers the message, not a 500). Adjust only if it does not.
- [x] **Step 5: Check statistics.** Read how `/stats` and chapter progress count translated lines; add a test in `tests/test_ollama_stats.py` or the stats test file proving a filled line is not counted in the day heatmap. If counts use `translated_text` alone, do not change the rule: write the finding in the commit message body and the final report.
- [x] **Step 6: Run** `pytest -q` and `ruff check .`. Expected: all pass, no lint errors.
- [x] **Step 7: Docs and commit.** One sentence in the `CLAUDE.md` Ollama paragraph; delete the TODO entry "Ollama and translation memory: skip symbol-only lines". Commit `feat(ollama): skip symbol-only lines and fill them with their source`.
