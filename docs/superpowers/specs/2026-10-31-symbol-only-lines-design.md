# Symbol-only lines: skip them in Ollama and translation memory

Date: 2026-10-31. Replaces the TODO entry "Ollama and translation memory: skip symbol-only lines".

## Why

Scene breaks such as `■`, `◇◇◇` or a lone `……` have nothing to translate. Today they are sent to Ollama, which uses
resources for nothing, and they appear as translation memory matches: a series that reuses the same symbol for every scene
break fills the panel with identical matches.

## Goals

1. Ollama never asks the model about a symbol-only line, in the background queue or by hand.
2. Such a line still ends up translated as itself, so it appears in the published chapter and the EPUB: its source is
   copied into `translated_text`. (The user chose "count as translated, source copied".)
3. Translation memory returns nothing for a symbol-only line.

## Non-goals

- No change to the editor, to blank-line handling, or to lines you already translated. A line with a translation is never
  overwritten.
- No migration. No SPA change.
- The editor does not fill these lines just by opening a chapter; the copy happens in Ollama's flow only.

## Design

### The rule

One pure function in `api/core/text.py`:

```python
def has_letter(text: str) -> bool: ...
```

True when the text contains a letter in the Unicode sense (`str.isalpha()` is true for Latin, kana, kanji and `ー`).
Digits and punctuation do not count, so `12`, `■`, `◇◇◇`, `……` and `***` are symbol-only. The designer's choice that digits
alone do not count was confirmed with the user.

A line is **symbol-only** when its text is non-blank and `not has_letter(text)`. Blank lines keep their current handling.
Which text is tested: the line's `raw_text`.

### Ollama (`api/ollama/work.py`)

- `rows_for`: a symbol-only line's row gets `known = line.translated_text or <the line's text>` so it is never asked and
  still serves as context. (A row's `known` is what marks it as not needing a request.) Use the stripped
  `replace_and_parse` text or `raw_text.strip()`; builder's call, but a scene break needs no glossary.
- A new function (say `fill_symbol_lines(db, doc)`) writes `translated_text = raw_text.strip()` for the document's
  symbol-only lines whose `translated_text` is empty, in one UPDATE. It is called in `next_plan` right before `rows_for` for
  each pending chapter. It flushes only (the runner owns the transaction).
- `translated_at` stays NULL for these copied lines (designer's call): the statistics heatmap and counts must not credit
  you for work you did not do. The builder must check how `/stats` and the chapter progress count a line
  (`translated_text != ''`, `translated_at`, or both) and confirm the copied lines show as translated in the chapter
  progress and publish, and are not counted as a day's work. If the stats count by `translated_text` alone, report that
  instead of silently changing the rule, and keep the copy (the user's decision stands).
- `lines_left`: do not count symbol-only lines.
- `_with_work` (SQL): stays an upper bound, as its docstring says. It still treats a symbol-only line with no translation
  as work; `next_plan` then runs `fill_symbol_lines`, after which the line has a translation and the SQL no longer sees
  it, and a chapter with only scene breaks left is cleared without a request. Keep the docstring accurate; do not try to
  port `has_letter` to SQL regexes (Postgres `[[:alpha:]]` depends on the locale).
- `plan_for_line` (by hand): a symbol-only line asked by hand raises the same kind of `ValueError` it raises for a line
  with no text ("has nothing to translate"); the by-hand route already reports that error, so check its message reads
  sensibly for this case. Do not write anything in `rows_for` (it is read-only).
- A drained queue item must still be removed (the `if item.kind != "series" and not skipped` path).

### Translation memory (`api/routers/memory.py`, `/tm/matches`)

After the existing `raw is None` and `not raw.strip()` checks, return `[]` when `not has_letter(raw)`. Candidates are
other lines with the identical source (`Line.raw_text == raw`), so a symbol-only query already excludes every symbol-only
candidate; no separate candidate filter is needed.

## Tests (pytest, `tests/`)

- `has_letter`: kanji, kana, `ー`, Latin letters true; `■`, `◇◇◇`, `……`, `12`, `***`, `「……！」` false; blank false.
- Ollama: a chapter with text lines and a `■` line: the prompt never contains `■`; after `next_plan` the `■` line's
  `translated_text` is `■` and `translated_at` is NULL; an already-translated symbol line is untouched; a chapter that
  has only scene breaks left is cleared and its queue item removed; `lines_left` does not count them; by-hand on a
  symbol-only line gives the "nothing to translate" error.
- Translation memory: two chapters share a `■` line, one translated: `/tm/matches` for the other returns `[]`; a
  letter-bearing shared line still matches.
- Follow the repo's conventions: per-test transaction `db` fixture, `jobs.run_next`/runner seams as in
  `tests/test_ollama_*`. Gate: `pytest` for the touched files, `ruff check .`, no module over ~400 lines
  (`api/ollama/work.py` is 257 lines, `api/core/text.py` is ~330).

## Left to the builder

Where exactly the fill call sits in `next_plan`, the names, and the error wording for the by-hand case. Update the
`CLAUDE.md` Ollama paragraph with one sentence (symbol-only lines are never asked and are filled with their source), and
delete the TODO entry.

## Delegation

One plan, backend only. Suitable for DeepSeek V4.1 Flash on its own branch and worktree; Claude reviews.
