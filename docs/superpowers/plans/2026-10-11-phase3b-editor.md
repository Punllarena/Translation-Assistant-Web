# Phase 3b — Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the editor: a chapter's lines as cards, a CodeMirror translation input on the active card, debounced saving with a visible save state that never loses typing, the rebindable keymap with parse navigation and punctuation inserts, a find bar, server spellcheck with suggestions and add-to-dictionary, Japanese character-class highlighting, progress, inline images, and an Edit Source / Split view, plus two Playwright smoke flows.

**Architecture:** The editor is `web/src/editor/`. Pure logic lives in small tested modules: row layout and navigation, parse pointer, find, painting spans, split cuts, keymap, and the save store. Components stay thin. One CodeMirror view exists at a time, on the active card; inactive cards are plain text painted with spans. A window-level capture `keydown` listener dispatches bound actions before CodeMirror sees them. Unsaved edits are flushed with `fetch` `keepalive` on page hide and stashed in `sessionStorage`, so a closed tab or an expired session cannot drop them. The server gains one endpoint, `PUT /documents/{id}/source`.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / Postgres 16 (one endpoint). React 19, react-router 8, @tanstack/react-query 5, openapi-fetch, TypeScript ~5.9, vitest 5. New: `@codemirror/state`, `@codemirror/view`, `@codemirror/commands` (spec §5), and dev `@playwright/test` (spec §12).

**Spec:** `docs/superpowers/specs/2026-10-10-web-app-port-design.md` §5 (editor), §12 (testing), §15 phase 3. Phase 3a (`docs/superpowers/plans/2026-10-11-phase3a-editor-api-and-spa.md`) built the endpoints this uses: `GET/PATCH /documents/{id}/lines`, `POST /spell/check`, `/profiles/{id}/words`, `/documents/{id}/images`, `/images/{id}`. Desktop reference: `../TranslationAssistant-PySide6-Port` at `f1a96ce` (`ui/main_widget.py` `_handle_key`/navigation/parse, `ui/card_list.py`, `ui/dlg_open.py` `_EditSourceDialog`/`_SplitChapterDialog`, `ui/dlg_shortcuts.py`). Carry-over from 3a review: memory note `phase3b-carryover`.

## Global Constraints

- Everything in the phase 1, 2 and 3a Global Constraints still applies: SQLAlchemy 2.0 style, real Postgres tests, cross-user 404, body-id 422 with one message, `api_router()` + handlers only `flush()`, no Python module over ~400 lines, **no React component file over ~300 lines**, Conventional Commits, every task ends on a commit.
- **Frontend dependencies** are the 3a list plus exactly: `@codemirror/state`, `@codemirror/view`, `@codemirror/commands`; dev `@playwright/test`. No virtualization library, no UI kit, no CodeMirror language/search packages.
- **vitest covers pure TypeScript modules** (environment `node`). Components are verified by `npm run build` and by Playwright (Task 11).
- The SPA talks to the API through `web/src/api/client.ts` (`api`, `call`). Raw `fetch` is allowed only where openapi-fetch cannot express the request: multipart uploads (3a) and the `keepalive` save on page hide (Task 4).
- **Offsets are UTF-16 code units everywhere** (JS string indices, CodeMirror positions, and the spell API since 3a). No code-point conversion anywhere in the client.
- After any API schema change, regenerate the client: `cd web && TA_SECRET_KEY=dev-secret-key-at-least-32-characters-long npm run gen:api`, and commit `web/src/api/schema.d.ts`.

**Deviations, decided here:**

1. **Japanese highlighting is character classes** (kanji / hiragana / katakana / Japanese punctuation), client-side, as spec §5 says. The desktop colours by MeCab part of speech with a token tooltip; that arrives with MeCab in phase 5 (user decision, 2026-10-11).
2. **Edit Source is built** (user decision): spec §5 puts the find bar in "the source-editing views". Unlike the desktop, the edited text is **not re-split** by `build_new_file`. Each line stays one line, and `$` continuation lines are shown and kept with their `$`, so paragraph structure survives an edit. A save that changes the line count is refused (409) until the user confirms, because translations stay attached by line position.
3. **The find bar follows the spec.** The desktop editor had none; its `Ctrl+F` copied the translation to the clipboard, and clipboard copying is out of scope (§14). Find searches source and translation, case-insensitively, wrapping, with an `n/total` counter.
4. **Every editor key is rebindable** (spec §5). On the desktop only menu actions were. The desktop's document-level shortcuts (`Ctrl+N/O/S/P`, `Ctrl+Shift+W` …) are not editor bindings: browsers reserve `Ctrl+N`/`Ctrl+T`/`Ctrl+W`, and those actions live in the picker. A binding the browser reserves is refused.
5. **Nine punctuation inserts on F1–F9**, matching the desktop's nine (`「」 『』 【】 … 〜 〈〉 《》 ー ♡`). The spec says F1–F8.
6. **Word count ignores empty translations.** The desktop's `"".split(" ")` counted one word for every untranslated line.
7. **"Virtualized list" is CSS `content-visibility: auto`** on each card, with no library. The desktop builds every card too (chunked); a chapter is a few hundred lines.
8. **Two of the three Playwright flows.** The third, find and replace across a series, is a phase 4 feature.
9. **Moving the active line writes `documents.last_position`**, which also bumps `updated_at` (the model's `onupdate`), so the picker's "last edited" time also moves when a chapter is only read. Accepted: one column, and the picker already sorts by it.

## Review Focus

1. **Closing the tab, or the session expiring, within the 800 ms save debounce.** The typed text must survive. It is sent with `keepalive` on page hide, stashed in `sessionStorage`, and restored and re-sent the next time the chapter opens. (Task 4)
2. **Typing while a save is in flight, or a save failing** (offline, 422). The indicator must never say "Saved" for text the server has not accepted, the text must stay, and Retry must resend it. (Task 3)
3. **Rebinding a key to a combination another action already uses (including an unchanged default), or to one the browser reserves.** Refused with a reason; it must not silently shadow another action. (Tasks 3, 5)
4. **An Edit Source save that changes the number of lines.** Explicit confirmation before translations shift position; no silent misalignment. (Tasks 1, 9)
5. **Source or translation containing astral characters (𠮷, emoji).** Highlight, spell underline and find ranges land on the right characters. (Task 2)

---

## File Structure

| File | Responsibility |
|---|---|
| `api/schemas/lines.py` (modify) | `SourceUpdate` |
| `api/routers/lines.py` (modify) | `PUT /documents/{id}/source` |
| `tests/test_source.py` | Edit Source tests |
| `web/src/editor/rows.ts` | `hasContent`, `buildRows`, navigation, `progress`, `sourceText` |
| `web/src/editor/parse.ts` | Parse pointer and sentence ranges |
| `web/src/editor/find.ts` | `findIn`, `findHits`, `wrapStep`, `firstFrom` |
| `web/src/editor/paint.ts` | `jpSpans`, `segments` |
| `web/src/editor/cuts.ts` | `SPLIT_MARKER`, `cutsFromText`, `insertMarker` |
| `web/src/editor/keymap.ts` | `ACTIONS`, `PUNCTUATIONS`, `bindingOf`, `effective`, `actionOf`, `bindingProblem` |
| `web/src/editor/saveStore.ts` | Debounced save store |
| `web/src/editor/spell.ts` | `spellBatches` |
| `*.test.ts` beside each | vitest |
| `web/src/editor/useEditor.ts` | Active line, parse, texts, save store wiring, stash, last position |
| `web/src/editor/useEditorKeys.ts` | Window capture keydown → action; `useBindings` |
| `web/src/editor/useSpell.ts` | Spellcheck cache and batching |
| `web/src/editor/EditorPage.tsx` | Route, loads lines, mounts `Editor` |
| `web/src/editor/Editor.tsx` | Composition and action dispatch |
| `web/src/editor/CardList.tsx`, `LineCard.tsx`, `ImageCard.tsx` | Cards |
| `web/src/editor/CodeEditor.tsx` | CodeMirror view, `setMarks`, `insertAtCursor` |
| `web/src/editor/StatusBar.tsx`, `FindBar.tsx`, `SpellMenu.tsx` | Chrome |
| `web/src/editor/SourcePage.tsx` | Edit Source and Split |
| `web/src/settings/ShortcutsPage.tsx` | Rebinding screen |
| `web/src/App.tsx`, `Shell.tsx`, `styles.css`, `auth/Login.tsx`, `library/*` (modify) | Routes, links, restore last opened, carry-over |
| `web/playwright.config.ts`, `web/e2e/*`, `tools/e2e_seed.py` | Smoke flows |
| `.github/workflows/ci.yml`, `web/vite.config.ts`, `README.md`, `CLAUDE.md` (modify) | CI, proxy target, docs |

---

### Task 1: Edit Source endpoint

**Files:**
- Modify: `api/schemas/lines.py`, `api/routers/lines.py`, `web/src/api/schema.d.ts` (regenerated)
- Create: `tests/test_source.py`

**Interfaces:**
- Consumes: `lines_to_db_rows`, `check_line_count`, `scoped`, `DocumentOut`, `MAX_RAW_CHARS` (`api/schemas/documents.py`).
- Produces: `PUT /documents/{document_id}/source`, body `SourceUpdate {text: str, force: bool = false}` → `DocumentOut`. 409 when the line count would change and `force` is false; 422 for empty text or too many lines.

- [ ] **Step 1: Write the failing tests in `tests/test_source.py`**

```python
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from api.models import Line


def rows(db, doc):
    db.expire_all()
    return [
        (line.prefix, line.raw_text, line.translated_text)
        for line in db.scalars(
            select(Line).where(Line.document_id == doc.id).order_by(Line.line_number)
        )
    ]


def put(client, doc, text, **body):
    return client.put(f"/documents/{doc.id}/source", json={"text": text, **body})


def test_edit_keeps_translations_and_history_by_position(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。", "二。"])
    stamp = datetime(2026, 1, 2, tzinfo=UTC)
    for line in db.scalars(select(Line).where(Line.document_id == doc.id)):
        line.translated_at = stamp
    db.flush()
    r = put(app_client, doc, "壱。\n$弐。")
    assert r.status_code == 200
    assert rows(db, doc) == [("%", "壱。", "tr:一。"), ("$", "弐。", "tr:二。")]
    assert {line.translated_at for line in db.scalars(select(Line))} == {stamp}


def test_lines_are_not_resplit(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。"])
    assert put(app_client, doc, "壱。弐。").status_code == 200
    assert rows(db, doc) == [("%", "壱。弐。", "tr:一。")]


def test_line_count_change_needs_force(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。", "二。"])
    r = put(app_client, doc, "壱。")
    assert r.status_code == 409
    assert "from 2 to 1" in r.json()["detail"]
    assert rows(db, doc) == [("%", "一。", "tr:一。"), ("%", "二。", "tr:二。")]


def test_force_applies_a_shorter_and_a_longer_source(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。", "二。"])
    assert put(app_client, doc, "壱。", force=True).status_code == 200
    assert rows(db, doc) == [("%", "壱。", "tr:一。")]
    assert put(app_client, doc, "壱。\n\n参。", force=True).status_code == 200
    assert rows(db, doc) == [("%", "壱。", "tr:一。"), ("%", "", ""), ("%", "参。", "")]


@pytest.mark.parametrize("text", ["", "   \n  "])
def test_empty_source_is_422(app_client, me, make_doc, text):
    doc = make_doc(me, ["一。"])
    assert put(app_client, doc, text, force=True).status_code == 422


def test_line_cap(app_client, me, make_doc, monkeypatch):
    from api import library

    monkeypatch.setattr(library, "MAX_LINES", 2)
    doc = make_doc(me, ["一。", "二。"])
    r = put(app_client, doc, "a\nb\nc", force=True)
    assert (r.status_code, r.json()["detail"]) == (422, "too many lines (max 2)")


def test_another_users_document_is_404(app_client, me, make_user, make_doc):
    theirs = make_doc(make_user(email="other@example.com"), ["x"])
    assert put(app_client, theirs, "y").status_code == 404
```

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/test_source.py -v`
Expected: FAIL (405 Method Not Allowed: no PUT route)

- [ ] **Step 3: Add `SourceUpdate` to `api/schemas/lines.py`**

```python
from api.schemas.documents import MAX_RAW_CHARS


class SourceUpdate(BaseModel):
    text: str = Field(max_length=MAX_RAW_CHARS)
    force: bool = False  # confirm a change in the number of lines
```

(Merge the import with the existing `from api.schemas.documents import DocumentOut`.)

- [ ] **Step 4: Add the endpoint to `api/routers/lines.py`**

Add the imports (`lines_to_db_rows` from `api.core.text`, `check_line_count` from `api.library`, `DocumentOut` from `api.schemas.documents`, `SourceUpdate` from `api.schemas.lines`) and:

```python
@router.put("/documents/{document_id}/source", response_model=DocumentOut)
def replace_source(
    document_id: int,
    body: SourceUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Document:
    """Edit Source (the desktop replace_raw_content). One text line is one line, a leading
    $ marks a continuation; lines are not re-split. Translations and translated_at stay
    attached by position, so a change in line count is refused unless forced."""
    doc = scoped(db, Document, document_id, user.id)
    if not body.text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "source text is empty")
    raw = body.text.splitlines()
    check_line_count(raw)
    rows = lines_to_db_rows(raw, [])
    existing = {
        line.line_number: line
        for line in db.scalars(select(Line).where(Line.document_id == doc.id))
    }
    if len(rows) != len(existing) and not body.force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"line count changes from {len(existing)} to {len(rows)}; translations stay "
            "attached by line position",
        )
    for row in rows:
        line = existing.pop(row["line_number"], None)
        prefix = row["prefix"] or "%"
        if line is None:
            db.add(Line(document_id=doc.id, line_number=row["line_number"], prefix=prefix,
                        raw_text=row["raw_text"], translated_text=""))
        else:
            line.prefix, line.raw_text = prefix, row["raw_text"]
    for line in existing.values():
        db.delete(line)
    doc.updated_at = func.now()
    db.flush()
    return doc
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_source.py tests/test_commit_boundary.py -v && ruff check .`
Expected: all PASS

- [ ] **Step 6: Regenerate the client**

Run: `cd web && TA_SECRET_KEY=dev-secret-key-at-least-32-characters-long npm run gen:api && npm run build`
Expected: `schema.d.ts` gains `"/documents/{document_id}/source"`; build passes.

- [ ] **Step 7: Commit**

```bash
git add api/schemas/lines.py api/routers/lines.py tests/test_source.py web/src/api/schema.d.ts
git commit -m "feat(lines): edit a chapter's source with translations kept by position"
```

---

### Task 2: Editor text helpers

**Files:**
- Create: `web/src/editor/rows.ts`, `parse.ts`, `find.ts`, `paint.ts`, `cuts.ts`, and `rows.test.ts`, `parse.test.ts`, `find.test.ts`, `paint.test.ts`, `cuts.test.ts`

**Interfaces:**
- Consumes: `Schemas` (`web/src/api/client.ts`).
- Produces (all pure):
  - `rows.ts`: `type Line = Schemas["LineOut"]`, `type Image = Schemas["ImageOut"]`, `type Row = {kind:"line"; line: Line; index: number} | {kind:"image"; image: Image}`, `hasContent(raw)`, `buildRows(lines, images)`, `nextContent(lines, from)`, `prevContent(lines, from)`, `firstContent(lines)`, `firstUntranslated(lines, texts)`, `lineAtOrAfter(lines, n)`, `progress(lines, texts) -> {percent, words}`, `sourceText(lines)`. Navigation returns an array index or `null`; `texts` is `Record<line_number, string>`.
  - `parse.ts`: `advanceParse(p, count)`, `retreatParse(p, replaced)`, `sentenceRanges(display, sentences) -> [number, number][]`.
  - `find.ts`: `findIn(text, needle) -> [number, number][]`, `type Hit = {index; field: "source"|"translation"; from; to}`, `findHits(items, needle)`, `wrapStep(current, total, dir)`, `firstFrom(hits, active)`.
  - `paint.ts`: `type Span = {from; to; cls}`, `jpSpans(text)`, `type Segment = {text; classes: string[]}`, `segments(text, spans)`.
  - `cuts.ts`: `SPLIT_MARKER`, `cutsFromText(text) -> {start; title}[]`, `insertMarker(text, caret) -> {text; caret}`.

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/editor/rows.test.ts
import { describe, expect, it } from "vitest";
import {
  buildRows, firstContent, firstUntranslated, hasContent, lineAtOrAfter, nextContent,
  prevContent, progress, sourceText, type Image, type Line,
} from "./rows";

const line = (n: number, raw: string, prefix = "%") =>
  ({ line_number: n, prefix, raw_text: raw, display_text: raw, sentences: [raw], replaced: false, translated_text: "" }) as Line;
const image = (id: number, anchor: number) => ({ id, anchor_position: anchor }) as Image;
const L = [line(0, "一"), line(1, ""), line(2, "二"), line(3, "  "), line(4, "三")];

describe("rows", () => {
  it("hasContent ignores markers and whitespace", () => {
    expect([hasContent("一"), hasContent(""), hasContent("%$ "), hasContent("%$")]).toEqual([true, false, false, false]);
  });
  it("buildRows skips blank lines and anchors images before their line", () => {
    const rows = buildRows(L, [image(9, 99), image(7, 2), image(8, 0)]);
    expect(rows.map((r) => (r.kind === "line" ? `L${r.index}` : `I${r.image.id}`))).toEqual(["I8", "L0", "I7", "L2", "L4", "I9"]);
  });
  it("navigates over translatable lines only", () => {
    expect([nextContent(L, 0), nextContent(L, 2), nextContent(L, 4)]).toEqual([2, 4, null]);
    expect([prevContent(L, 4), prevContent(L, 2), prevContent(L, 0)]).toEqual([2, 0, null]);
    expect(firstContent(L)).toBe(0);
  });
  it("firstUntranslated searches from the top", () => {
    expect(firstUntranslated(L, { 0: "a", 2: "", 4: "" })).toBe(2);
    expect(firstUntranslated(L, { 0: "a", 2: "b", 4: "c" })).toBeNull();
  });
  it("lineAtOrAfter clamps and moves to the next translatable line", () => {
    expect([lineAtOrAfter(L, 1), lineAtOrAfter(L, 2), lineAtOrAfter(L, 99), lineAtOrAfter(L, -5)]).toEqual([0, 2, 4, 0]);
  });
  it("progress counts translatable lines and words of non-empty translations", () => {
    expect(progress(L, { 0: "two words", 2: "", 4: "x" })).toEqual({ percent: 66, words: 3 });
    expect(progress([line(0, "")], {})).toEqual({ percent: 0, words: 0 });
  });
  it("sourceText keeps $ continuations", () => {
    expect(sourceText([line(0, "一。"), line(1, "二。", "$"), line(2, "")])).toBe("一。\n$二。\n");
  });
});
```

```ts
// web/src/editor/parse.test.ts
import { describe, expect, it } from "vitest";
import { advanceParse, retreatParse, sentenceRanges } from "./parse";

describe("parse pointer", () => {
  it("advances to the last sentence and stops", () => {
    expect([advanceParse(-1, 2), advanceParse(0, 2), advanceParse(1, 2), advanceParse(-2, 2)]).toEqual([0, 1, 1, -1]);
  });
  it("retreats to -1, or to -2 (raw text) only when the glossary replaced something", () => {
    expect([retreatParse(1, false), retreatParse(-1, false), retreatParse(-1, true), retreatParse(-2, true)]).toEqual([0, -1, -2, -2]);
  });
  it("maps repeated sentences to their own occurrence", () => {
    expect(sentenceRanges("はい、はい、", ["はい", "はい"])).toEqual([[0, 2], [3, 5]]);
  });
  it("marks a sentence it cannot find as empty", () => {
    expect(sentenceRanges("abc", ["zz"])).toEqual([[0, 0]]);
  });
});
```

```ts
// web/src/editor/find.test.ts
import { describe, expect, it } from "vitest";
import { findHits, findIn, firstFrom, wrapStep } from "./find";

describe("find", () => {
  it("is case-insensitive and escapes regex characters", () => {
    expect(findIn("Taro taro TARO", "taro")).toEqual([[0, 4], [5, 9], [10, 14]]);
    expect(findIn("a.b axb", "a.b")).toEqual([[0, 3]]);
    expect(findIn("abc", "")).toEqual([]);
  });
  it("uses UTF-16 offsets past astral characters", () => {
    expect(findIn("𠮷野家の𠮷", "𠮷")).toEqual([[0, 2], [5, 7]]);
  });
  it("lists source hits before translation hits per line", () => {
    const hits = findHits([{ index: 3, source: "犬", translation: "a dog 犬" }], "犬");
    expect(hits).toEqual([
      { index: 3, field: "source", from: 0, to: 1 },
      { index: 3, field: "translation", from: 6, to: 7 },
    ]);
  });
  it("wraps in both directions and starts from either end", () => {
    expect([wrapStep(2, 3, 1), wrapStep(0, 3, -1), wrapStep(-1, 3, 1), wrapStep(-1, 3, -1), wrapStep(0, 0, 1)]).toEqual([0, 2, 0, 2, -1]);
  });
  it("firstFrom picks the first hit at or after the active line, else the first", () => {
    const hits = [{ index: 1 }, { index: 5 }].map((h) => ({ ...h, field: "source" as const, from: 0, to: 1 }));
    expect([firstFrom(hits, 3), firstFrom(hits, 9), firstFrom([], 0)]).toEqual([1, 0, -1]);
  });
});
```

```ts
// web/src/editor/paint.test.ts
import { describe, expect, it } from "vitest";
import { jpSpans, segments } from "./paint";

describe("paint", () => {
  it("classifies runs of kanji, hiragana, katakana and Japanese punctuation", () => {
    expect(jpSpans("漢字とカナー、abc")).toEqual([
      { from: 0, to: 2, cls: "jp-kanji" },
      { from: 2, to: 3, cls: "jp-hiragana" },
      { from: 3, to: 6, cls: "jp-katakana" },
      { from: 6, to: 7, cls: "jp-punct" },
    ]);
  });
  it("counts astral kanji as two UTF-16 units", () => {
    expect(jpSpans("𠮷野")).toEqual([{ from: 0, to: 3, cls: "jp-kanji" }]);
  });
  it("segments overlapping spans into classed pieces", () => {
    expect(segments("abcdef", [{ from: 1, to: 4, cls: "x" }, { from: 3, to: 5, cls: "y" }])).toEqual([
      { text: "a", classes: [] },
      { text: "bc", classes: ["x"] },
      { text: "d", classes: ["x", "y"] },
      { text: "e", classes: ["y"] },
      { text: "f", classes: [] },
    ]);
  });
  it("clamps spans to the text and ignores empty ones", () => {
    expect(segments("ab", [{ from: 1, to: 9, cls: "x" }, { from: 0, to: 0, cls: "z" }])).toEqual([
      { text: "a", classes: [] },
      { text: "b", classes: ["x"] },
    ]);
  });
});
```

```ts
// web/src/editor/cuts.test.ts
import { describe, expect, it } from "vitest";
import { cutsFromText, insertMarker, SPLIT_MARKER } from "./cuts";

const M = SPLIT_MARKER;

describe("split cuts", () => {
  it("cuts before the line after each marker, with its title", () => {
    expect(cutsFromText(`a\nb\n${M} Two\nc\n${M}\nd`)).toEqual([{ start: 2, title: "Two" }, { start: 3, title: "" }]);
  });
  it("ignores a marker before the first line, at the end, or repeated", () => {
    expect(cutsFromText(`${M} x\na\n${M} y\n${M} z\nb\n${M} end`)).toEqual([{ start: 1, title: "y" }]);
  });
  it("inserts a marker at the start of the caret's line and puts the caret after it", () => {
    const { text, caret } = insertMarker("ab\ncd", 4);
    expect(text).toBe(`ab\n${M} \ncd`);
    expect(text.slice(0, caret)).toBe(`ab\n${M} `);
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd web && npm test`
Expected: the five new files FAIL to resolve their modules.

- [ ] **Step 3: Write `web/src/editor/rows.ts`**

```ts
import type { Schemas } from "../api/client";

export type Line = Schemas["LineOut"];
export type Image = Schemas["ImageOut"];
export type Row = { kind: "line"; line: Line; index: number } | { kind: "image"; image: Image };

/** A line with translatable text (desktop core.line_has_content). */
export const hasContent = (raw: string) => raw.replace(/^[%$]+/, "").trim() !== "";

/** Cards in reading order (desktop card_list.load): an image anchored at n sits before
 *  line n, images anchored past the end go last, and blank lines get no card. */
export function buildRows(lines: Line[], images: Image[]): Row[] {
  const sorted = [...images].sort((a, b) => a.anchor_position - b.anchor_position || a.id - b.id);
  const rows: Row[] = [];
  let next = 0;
  lines.forEach((line, index) => {
    while (next < sorted.length && sorted[next].anchor_position <= line.line_number) {
      rows.push({ kind: "image", image: sorted[next++] });
    }
    if (hasContent(line.raw_text)) rows.push({ kind: "line", line, index });
  });
  while (next < sorted.length) rows.push({ kind: "image", image: sorted[next++] });
  return rows;
}

export function nextContent(lines: Line[], from: number): number | null {
  for (let i = from + 1; i < lines.length; i++) if (hasContent(lines[i].raw_text)) return i;
  return null;
}

export function prevContent(lines: Line[], from: number): number | null {
  for (let i = from - 1; i >= 0; i--) if (hasContent(lines[i].raw_text)) return i;
  return null;
}

export const firstContent = (lines: Line[]) => nextContent(lines, -1);

/** The first translatable line without a translation, from the top (desktop
 *  _jump_to_next_untranslated). */
export function firstUntranslated(lines: Line[], texts: Record<number, string>): number | null {
  const i = lines.findIndex((l) => hasContent(l.raw_text) && !texts[l.line_number]);
  return i < 0 ? null : i;
}

/** Go to line: 1-based n, clamped, moved forward (else back) to a translatable line. */
export function lineAtOrAfter(lines: Line[], n: number): number | null {
  if (!lines.length) return null;
  const i = Math.max(0, Math.min(lines.length - 1, n - 1));
  return hasContent(lines[i].raw_text) ? i : (nextContent(lines, i) ?? prevContent(lines, i));
}

/** The desktop calculate_progress rules, except that an empty translation counts no
 *  words (the desktop's "".split(" ") counted one). */
export function progress(lines: Line[], texts: Record<number, string>) {
  let total = 0;
  let done = 0;
  let words = 0;
  for (const l of lines) {
    const t = texts[l.line_number] ?? "";
    if (t) words += t.split(" ").length;
    if (hasContent(l.raw_text)) {
      total++;
      if (t) done++;
    }
  }
  return { percent: total ? Math.floor((done * 100) / total) : 0, words };
}

/** The Edit Source text: one line per line, $ kept on continuation lines. */
export const sourceText = (lines: Line[]) =>
  lines.map((l) => (l.prefix === "$" ? "$" : "") + l.raw_text).join("\n");
```

- [ ] **Step 4: Write `parse.ts`, `find.ts`, `paint.ts`, `cuts.ts`**

```ts
// web/src/editor/parse.ts
/** Parse navigation (desktop _advance_parse / _retreat_parse). The pointer is a sentence
 *  index; -1 shows the glossary-substituted line, -2 the raw line (only reachable when
 *  the glossary changed something). */
export const advanceParse = (p: number, count: number) => (p + 1 < count ? p + 1 : p);

export const retreatParse = (p: number, replaced: boolean) =>
  p - 1 >= (replaced ? -2 : -1) ? p - 1 : p;

/** Each sentence's [from, to) in the display text, searched in order so a repeated
 *  sentence maps to its own occurrence (the desktop always found the first). */
export function sentenceRanges(display: string, sentences: string[]): [number, number][] {
  const ranges: [number, number][] = [];
  let at = 0;
  for (const s of sentences) {
    const i = display.indexOf(s, at);
    if (i < 0) {
      ranges.push([0, 0]);
      continue;
    }
    ranges.push([i, i + s.length]);
    at = i + s.length;
  }
  return ranges;
}
```

```ts
// web/src/editor/find.ts
export interface Hit {
  index: number; // array index of the line
  field: "source" | "translation";
  from: number;
  to: number;
}

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Case-insensitive occurrences of `needle`, as UTF-16 [from, to). */
export function findIn(text: string, needle: string): [number, number][] {
  if (!needle) return [];
  return [...text.matchAll(new RegExp(escape(needle), "giu"))].map(
    (m) => [m.index, m.index + m[0].length] as [number, number],
  );
}

export function findHits(
  items: { index: number; source: string; translation: string }[],
  needle: string,
): Hit[] {
  return items.flatMap((item) => [
    ...findIn(item.source, needle).map(([from, to]) => ({ index: item.index, field: "source" as const, from, to })),
    ...findIn(item.translation, needle).map(([from, to]) => ({ index: item.index, field: "translation" as const, from, to })),
  ]);
}

/** The next position after `current` in `dir`, wrapping; -1 when there is nothing. */
export function wrapStep(current: number, total: number, dir: 1 | -1): number {
  if (total === 0) return -1;
  if (current < 0) return dir === 1 ? 0 : total - 1;
  return (current + dir + total) % total;
}

/** The first hit on or after the active line, else the first hit; -1 when none. */
export function firstFrom(hits: Hit[], active: number): number {
  if (!hits.length) return -1;
  const i = hits.findIndex((h) => h.index >= active);
  return i < 0 ? 0 : i;
}
```

```ts
// web/src/editor/paint.ts
export interface Span {
  from: number;
  to: number;
  cls: string;
}

export interface Segment {
  text: string;
  classes: string[];
}

const CLASSES: [RegExp, string][] = [
  [/[\p{Script=Han}々〆ヵヶ]/u, "jp-kanji"],
  [/\p{Script=Hiragana}/u, "jp-hiragana"],
  [/[\p{Script=Katakana}ー]/u, "jp-katakana"],
  [/[　-〿！-／：-＠［-｀｛-･…‥]/u, "jp-punct"],
];

/** Runs of kanji, hiragana, katakana and Japanese punctuation, in UTF-16 offsets. */
export function jpSpans(text: string): Span[] {
  const spans: Span[] = [];
  let at = 0;
  for (const ch of text) {
    const cls = CLASSES.find(([re]) => re.test(ch))?.[1];
    const last = spans[spans.length - 1];
    if (cls && last && last.cls === cls && last.to === at) last.to += ch.length;
    else if (cls) spans.push({ from: at, to: at + ch.length, cls });
    at += ch.length;
  }
  return spans;
}

/** The text cut at every span edge; each piece carries the classes of the spans that
 *  cover it. Spans may overlap; they are clamped to the text and empty ones dropped. */
export function segments(text: string, spans: Span[]): Segment[] {
  const live = spans
    .map((s) => ({ ...s, from: Math.max(0, s.from), to: Math.min(text.length, s.to) }))
    .filter((s) => s.to > s.from);
  const cuts = [...new Set([0, text.length, ...live.flatMap((s) => [s.from, s.to])])].sort((a, b) => a - b);
  const out: Segment[] = [];
  for (let i = 0; i + 1 < cuts.length; i++) {
    const [a, b] = [cuts[i], cuts[i + 1]];
    out.push({ text: text.slice(a, b), classes: live.filter((s) => s.from <= a && s.to >= b).map((s) => s.cls) });
  }
  return out;
}
```

```ts
// web/src/editor/cuts.ts
export const SPLIT_MARKER = "---CHAPTER SPLIT---";

/** The desktop _SplitChapterDialog._cuts: the first line of each new chapter (counting
 *  non-marker lines) and the title typed after its marker. A marker before the first
 *  line, after the last, or repeating the previous position is ignored. */
export function cutsFromText(text: string): { start: number; title: string }[] {
  const cuts: { start: number; title: string }[] = [];
  let n = 0;
  for (const raw of text.split("\n")) {
    const s = raw.trim();
    if (s.startsWith(SPLIT_MARKER)) {
      if (n >= 1 && cuts[cuts.length - 1]?.start !== n) {
        cuts.push({ start: n, title: s.slice(SPLIT_MARKER.length).trim() });
      }
    } else {
      n++;
    }
  }
  return cuts.filter((c) => c.start <= n - 1);
}

/** A marker line at the start of the caret's line; the caret lands after it, ready for
 *  the title. */
export function insertMarker(text: string, caret: number) {
  const start = text.lastIndexOf("\n", caret - 1) + 1;
  const marker = `${SPLIT_MARKER} `;
  return { text: `${text.slice(0, start)}${marker}\n${text.slice(start)}`, caret: start + marker.length };
}
```

- [ ] **Step 5: Run the tests**

Run: `cd web && npm test && npx tsc --noEmit`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add web/src/editor
git commit -m "feat(editor): pure helpers for rows, navigation, parse, find, highlighting, and split cuts"
```

---

### Task 3: Keymap and save store

**Files:**
- Create: `web/src/editor/keymap.ts`, `keymap.test.ts`, `saveStore.ts`, `saveStore.test.ts`

**Interfaces:**
- Produces:
  - `keymap.ts`: `PUNCTUATIONS: string[]` (9), `ACTIONS: {key, label, binding}[]`, `RESERVED: Set<string>`, `bindingOf(e) -> string | null`, `effective(overrides) -> Record<action, binding>`, `actionOf(bindings, binding) -> string | undefined`, `bindingProblem(bindings, action, binding) -> string | null`.
  - `saveStore.ts`: `type SaveState = "saved" | "saving" | "unsaved" | "error"`, `type Edit = {line_number; translated_text}`, `createSaveStore({save, delayMs = 800}) -> SaveStore` where `SaveStore = {edit(n, text); flush(): Promise<void>; flushOnExit(); unsaved(): Edit[]; pending(): boolean; subscribe(fn): () => void; getState(): {state: SaveState; error: string | null}}`. `save(edits, keepalive)` rejects on failure.

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/editor/keymap.test.ts
import { describe, expect, it } from "vitest";
import { ACTIONS, actionOf, bindingOf, bindingProblem, effective, PUNCTUATIONS } from "./keymap";

const key = (k: string, mods: Partial<Record<"ctrlKey" | "altKey" | "shiftKey" | "metaKey", boolean>> = {}) =>
  ({ key: k, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods });

describe("keymap", () => {
  it("names key presses", () => {
    expect(bindingOf(key("Enter"))).toBe("Enter");
    expect(bindingOf(key("j", { ctrlKey: true }))).toBe("Ctrl+J");
    expect(bindingOf(key("ArrowRight", { ctrlKey: true, shiftKey: true }))).toBe("Ctrl+Shift+ArrowRight");
    expect(bindingOf(key("=", { metaKey: true }))).toBe("Ctrl+=");
    expect(bindingOf(key(" ", { altKey: true }))).toBe("Alt+Space");
    expect(bindingOf(key("Shift", { shiftKey: true }))).toBeNull();
  });
  it("has unique action keys and default bindings, nine F-key inserts", () => {
    expect(new Set(ACTIONS.map((a) => a.key)).size).toBe(ACTIONS.length);
    expect(new Set(ACTIONS.map((a) => a.binding)).size).toBe(ACTIONS.length);
    expect(PUNCTUATIONS).toHaveLength(9);
    expect(effective({}).punct_8).toBe("F9");
  });
  it("overrides replace defaults", () => {
    const b = effective({ next: "Ctrl+K" });
    expect([b.next, actionOf(b, "Ctrl+K"), actionOf(b, "PageDown")]).toEqual(["Ctrl+K", "next", undefined]);
  });
  it("refuses a binding another action uses, including a default", () => {
    const b = effective({});
    expect(bindingProblem(b, "next", "Ctrl+J")).toMatch(/already used by/);
    expect(bindingProblem(b, "add_word", "Ctrl+J")).toBeNull();
    expect(bindingProblem(b, "next", "Ctrl+K")).toBeNull();
  });
  it("refuses browser-reserved bindings", () => {
    expect(bindingProblem(effective({}), "next", "Ctrl+W")).toMatch(/reserved/);
  });
});
```

```ts
// web/src/editor/saveStore.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createSaveStore, type Edit } from "./saveStore";

function deferred() {
  let resolve!: () => void;
  let reject!: (e: Error) => void;
  const promise = new Promise<void>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

describe("save store", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("debounces edits into one save", async () => {
    const calls: Edit[][] = [];
    const store = createSaveStore({ save: async (edits) => { calls.push(edits); } });
    store.edit(1, "a");
    store.edit(2, "b");
    store.edit(1, "a2");
    expect(store.getState().state).toBe("unsaved");
    await vi.advanceTimersByTimeAsync(799);
    expect(calls).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls).toEqual([[{ line_number: 1, translated_text: "a2" }, { line_number: 2, translated_text: "b" }]]);
    expect(store.getState().state).toBe("saved");
    expect(store.pending()).toBe(false);
  });

  it("does not call an edit made during a save saved", async () => {
    const first = deferred();
    const calls: Edit[][] = [];
    const store = createSaveStore({
      save: (edits) => { calls.push(edits); return calls.length === 1 ? first.promise : Promise.resolve(); },
    });
    store.edit(1, "a");
    const flushing = store.flush();
    expect(store.getState().state).toBe("saving");
    store.edit(1, "ab");
    first.resolve();
    await flushing;
    expect(store.getState().state).toBe("unsaved");
    expect(store.unsaved()).toEqual([{ line_number: 1, translated_text: "ab" }]);
    await vi.advanceTimersByTimeAsync(800);
    expect(calls[1]).toEqual([{ line_number: 1, translated_text: "ab" }]);
    expect(store.getState().state).toBe("saved");
  });

  it("keeps edits and reports the error when a save fails, then retries", async () => {
    let fail = true;
    const store = createSaveStore({ save: async () => { if (fail) throw new Error("offline"); } });
    store.edit(3, "x");
    await store.flush();
    expect(store.getState()).toEqual({ state: "error", error: "offline" });
    expect(store.unsaved()).toEqual([{ line_number: 3, translated_text: "x" }]);
    fail = false;
    await store.flush();
    expect(store.getState()).toEqual({ state: "saved", error: null });
  });

  it("flush with nothing dirty saves nothing", async () => {
    const save = vi.fn(async () => {});
    const store = createSaveStore({ save });
    await store.flush();
    expect(save).not.toHaveBeenCalled();
    expect(store.getState().state).toBe("saved");
  });

  it("flushOnExit sends everything with keepalive", () => {
    const save = vi.fn(async () => {});
    const store = createSaveStore({ save });
    store.edit(1, "a");
    store.flushOnExit();
    expect(save).toHaveBeenCalledWith([{ line_number: 1, translated_text: "a" }], true);
  });

  it("notifies subscribers and keeps a stable snapshot between changes", () => {
    const store = createSaveStore({ save: async () => {} });
    const fn = vi.fn();
    const off = store.subscribe(fn);
    const before = store.getState();
    expect(store.getState()).toBe(before);
    store.edit(1, "a");
    expect(fn).toHaveBeenCalled();
    expect(store.getState()).not.toBe(before);
    off();
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd web && npm test` — Expected: FAIL to resolve `./keymap` and `./saveStore`.

- [ ] **Step 3: Write `web/src/editor/keymap.ts`**

```ts
/** The desktop's nine special-character inserts (main_widget._PUNCTUATIONS). */
export const PUNCTUATIONS = ["「」", "『』", "【】", "…", "〜", "〈〉", "《》", "ー", "♡"];
const PUNCT_NAMES = [
  "single quote", "double quote", "lenticular brackets", "ellipsis", "wave dash",
  "single title brackets", "double title brackets", "long dash", "heart",
];

export interface Action {
  key: string;
  label: string;
  binding: string; // the default
}

/** Every editor action and its default key (desktop _handle_key and the shortcut
 *  registry). All are rebindable. */
export const ACTIONS: Action[] = [
  { key: "save_next", label: "Save and go to the next line", binding: "Enter" },
  { key: "next", label: "Next line", binding: "PageDown" },
  { key: "next_alt", label: "Next line (second key)", binding: "Ctrl+ArrowDown" },
  { key: "prev", label: "Previous line", binding: "PageUp" },
  { key: "prev_alt", label: "Previous line (second key)", binding: "Ctrl+ArrowUp" },
  { key: "next_untranslated", label: "Next untranslated line", binding: "Ctrl+End" },
  { key: "first", label: "First line", binding: "Ctrl+Home" },
  { key: "parse_next", label: "Next phrase", binding: "Ctrl+ArrowRight" },
  { key: "parse_prev", label: "Previous phrase", binding: "Ctrl+ArrowLeft" },
  { key: "go_to_line", label: "Go to line", binding: "Ctrl+G" },
  { key: "find", label: "Find", binding: "Ctrl+F" },
  { key: "add_word", label: "Add the selected word to the dictionary", binding: "Ctrl+J" },
  { key: "font_larger", label: "Larger text", binding: "Ctrl+=" },
  { key: "font_smaller", label: "Smaller text", binding: "Ctrl+-" },
  ...PUNCTUATIONS.map((p, i) => ({
    key: `punct_${i}`,
    label: `Insert ${PUNCT_NAMES[i]} ${p}`,
    binding: `F${i + 1}`,
  })),
];

/** Combinations browsers do not let a page handle. */
export const RESERVED = new Set([
  "Ctrl+N", "Ctrl+Shift+N", "Ctrl+T", "Ctrl+Shift+T", "Ctrl+W", "Ctrl+Shift+W",
  "Ctrl+Tab", "Ctrl+Shift+Tab",
]);

const MODIFIERS = new Set(["Control", "Shift", "Alt", "Meta", "AltGraph", "CapsLock"]);

/** A key press as a binding string, e.g. "Ctrl+Shift+ArrowRight"; null for a bare
 *  modifier. Cmd counts as Ctrl so defaults work on macOS. */
export function bindingOf(
  e: Pick<KeyboardEvent, "key" | "ctrlKey" | "altKey" | "shiftKey" | "metaKey">,
): string | null {
  if (MODIFIERS.has(e.key)) return null;
  const key = e.key === " " ? "Space" : e.key.length === 1 ? e.key.toUpperCase() : e.key;
  return [e.ctrlKey || e.metaKey ? "Ctrl" : "", e.altKey ? "Alt" : "", e.shiftKey ? "Shift" : "", key]
    .filter(Boolean)
    .join("+");
}

/** Each action's binding: the user's override, else the default. */
export function effective(overrides: Record<string, string>): Record<string, string> {
  return Object.fromEntries(ACTIONS.map((a) => [a.key, overrides[a.key] ?? a.binding]));
}

export const actionOf = (bindings: Record<string, string>, binding: string) =>
  Object.keys(bindings).find((k) => bindings[k] === binding);

/** Why `binding` cannot be given to `action`, or null when it can. Checks the effective
 *  map, so an unchanged default counts (the server only sees overrides). */
export function bindingProblem(
  bindings: Record<string, string>,
  action: string,
  binding: string,
): string | null {
  if (RESERVED.has(binding)) return `${binding} is reserved by the browser`;
  const owner = actionOf(bindings, binding);
  if (owner && owner !== action) {
    return `${binding} is already used by "${ACTIONS.find((a) => a.key === owner)?.label ?? owner}"`;
  }
  return null;
}
```

- [ ] **Step 4: Write `web/src/editor/saveStore.ts`**

```ts
export type SaveState = "saved" | "saving" | "unsaved" | "error";
export interface Edit {
  line_number: number;
  translated_text: string;
}
interface Snapshot {
  state: SaveState;
  error: string | null;
}

/** The dirty-lines store (spec §5). Edits are kept per line; a debounced flush sends
 *  them, and an edit is forgotten only when the server accepted that exact text, so a
 *  keystroke during a save, or a failed save, is never reported as saved. */
export function createSaveStore({
  save,
  delayMs = 800,
}: {
  save: (edits: Edit[], keepalive: boolean) => Promise<void>;
  delayMs?: number;
}) {
  const dirty = new Map<number, string>();
  const listeners = new Set<() => void>();
  let snapshot: Snapshot = { state: "saved", error: null };
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inFlight: Promise<void> | null = null;
  let again = false;

  const set = (state: SaveState, error: string | null = null) => {
    snapshot = { state, error };
    listeners.forEach((fn) => fn());
  };
  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(() => void flush(), delayMs);
  };
  // ponytail: the API takes 5000 lines a batch; a chapter's dirty set is far smaller
  const unsaved = (): Edit[] =>
    [...dirty].slice(0, 5000).map(([line_number, translated_text]) => ({ line_number, translated_text }));

  function edit(line: number, text: string) {
    dirty.set(line, text);
    if (!inFlight) set("unsaved");
    schedule();
  }

  function flush(): Promise<void> {
    clearTimeout(timer);
    if (inFlight) {
      again = true;
      return inFlight;
    }
    if (!dirty.size) {
      set("saved");
      return Promise.resolve();
    }
    const sent = new Map(dirty);
    set("saving");
    inFlight = save(unsaved(), false)
      .then(
        () => {
          for (const [n, t] of sent) if (dirty.get(n) === t) dirty.delete(n);
          set(dirty.size ? "unsaved" : "saved");
          if (dirty.size) schedule();
        },
        (e: unknown) => set("error", e instanceof Error ? e.message : String(e)),
      )
      .finally(() => {
        inFlight = null;
        if (again) {
          again = false;
          void flush();
        }
      });
    return inFlight;
  }

  /** Page hide: send everything with keepalive; nothing can be awaited any more. */
  function flushOnExit() {
    if (dirty.size) save(unsaved(), true).catch(() => {});
  }

  return {
    edit,
    flush,
    flushOnExit,
    unsaved,
    pending: () => dirty.size > 0 || inFlight !== null,
    subscribe(fn: () => void) {
      listeners.add(fn);
      return () => void listeners.delete(fn);
    },
    getState: () => snapshot,
  };
}

export type SaveStore = ReturnType<typeof createSaveStore>;
```

- [ ] **Step 5: Run the tests**

Run: `cd web && npm test && npx tsc --noEmit` — Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/editor
git commit -m "feat(editor): rebindable keymap and a save store that never reports unsent text as saved"
```

---

### Task 4: Editor screen and saving

**Files:**
- Create: `web/src/editor/useEditor.ts`, `EditorPage.tsx`, `Editor.tsx`, `CardList.tsx`, `LineCard.tsx`, `CodeEditor.tsx`, `StatusBar.tsx`
- Modify: `web/package.json` (+ lock), `web/src/App.tsx`, `web/src/styles.css`, `web/src/library/DocumentRow.tsx`, `web/src/auth/Login.tsx`

**Interfaces:**
- Consumes: Task 2 (`rows`, `parse`, `paint`), Task 3 (`createSaveStore`); `GET/PATCH /documents/{id}/lines`, `PATCH /documents/{id}`, `GET/PUT /settings`.
- Produces:
  - Route `/documents/:id` → `EditorPage`; `Editor({id, data, onProfile})`.
  - `useEditor(id, lines, startAt) -> {store, save: {state, error}, active, activate(i | null), parse, setParse, texts, setText(n, t)}`.
  - `CodeEditor({initial, label, onChange, onBlur?, onReady, onContextMenu?})` with exports `setMarks` (StateEffect of `Span[]`) and `insertAtCursor(view, text, caretOffset)`.
  - `LineCard` props: `{index, line, active, parse, text, highlight: Hit | null, misspelled: Misspelling[], onActivate, editor?}`; `CardList` props: `{rows, active, parse, texts, onActivate, editor, highlight?, misspelled?, renderImage?}`.
  - `StatusBar` props as in Step 6; save indicator is the page's only `role="status"`.
  - Settings keys: `editor_font_px` (number), `last_document_id` (number).

- [ ] **Step 1: Install CodeMirror**

```bash
cd web && npm install @codemirror/state @codemirror/view @codemirror/commands
```

- [ ] **Step 2: Write `web/src/editor/useEditor.ts`**

```ts
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { api, call } from "../api/client";
import type { Line } from "./rows";
import { createSaveStore, type Edit } from "./saveStore";

const stashKey = (id: number) => `ta-unsaved-${id}`;

async function saveLines(id: number, edits: Edit[], keepalive: boolean) {
  if (keepalive) {
    // openapi-fetch cannot set keepalive, which lets the request outlive the page.
    await fetch(`/api/documents/${id}/lines`, {
      method: "PATCH",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines: edits }),
    });
    return;
  }
  await call(api.PATCH("/documents/{document_id}/lines", {
    params: { path: { document_id: id } },
    body: { lines: edits },
  }));
}

/** Unsaved edits survive the tab closing, a crash, or a sign-in redirect in this tab:
 *  they are stashed in sessionStorage and re-sent when the chapter next opens. */
function stash(id: number, edits: Edit[]) {
  try {
    if (edits.length) sessionStorage.setItem(stashKey(id), JSON.stringify(edits));
    else sessionStorage.removeItem(stashKey(id));
  } catch {
    // storage unavailable: the keepalive save is the only net
  }
}

function takeStash(id: number): Edit[] {
  try {
    const raw = sessionStorage.getItem(stashKey(id));
    sessionStorage.removeItem(stashKey(id));
    return raw ? (JSON.parse(raw) as Edit[]) : [];
  } catch {
    return [];
  }
}

export function useEditor(id: number, lines: Line[], startAt: number) {
  const store = useMemo(
    () => createSaveStore({ save: (edits, keepalive) => saveLines(id, edits, keepalive) }),
    [id],
  );
  const save = useSyncExternalStore(store.subscribe, store.getState);
  const [active, setActive] = useState(startAt);
  const [parse, setParse] = useState(-1);
  const [texts, setTexts] = useState<Record<number, string>>(() =>
    Object.fromEntries(lines.map((l) => [l.line_number, l.translated_text])),
  );
  const linesRef = useRef(lines);
  linesRef.current = lines;

  const setText = useCallback(
    (n: number, t: string) => {
      setTexts((prev) => ({ ...prev, [n]: t }));
      store.edit(n, t);
    },
    [store],
  );

  useEffect(() => {
    const known = new Set(linesRef.current.map((l) => l.line_number));
    takeStash(id)
      .filter((e) => known.has(e.line_number))
      .forEach((e) => setText(e.line_number, e.translated_text));
    const onHide = () => {
      stash(id, store.unsaved());
      store.flushOnExit();
    };
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (store.pending()) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("pagehide", onHide);
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      window.removeEventListener("pagehide", onHide);
      window.removeEventListener("beforeunload", onBeforeUnload);
      stash(id, store.unsaved());
      void store.flush().then(() => {
        if (!store.unsaved().length) stash(id, []);
      });
    };
  }, [id, store, setText]);

  useEffect(() => {
    void call(api.PUT("/settings", { body: { last_document_id: id } })).catch(() => {});
  }, [id]);

  useEffect(() => {
    const line = lines[active];
    if (!line) return;
    const timer = setTimeout(() => {
      void call(api.PATCH("/documents/{document_id}", {
        params: { path: { document_id: id } },
        body: { last_position: line.line_number },
      })).catch(() => {});
    }, 1000);
    return () => clearTimeout(timer);
  }, [id, lines, active]);

  const activate = useCallback((i: number | null) => {
    if (i === null) return;
    setActive(i);
    setParse(-1);
  }, []);

  return { store, save, active, activate, parse, setParse, texts, setText };
}
```

- [ ] **Step 3: Write `web/src/editor/CodeEditor.tsx`**

```tsx
import { defaultKeymap, history, historyKeymap, insertNewline } from "@codemirror/commands";
import { EditorState, StateEffect, StateField } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, keymap } from "@codemirror/view";
import { useEffect, useRef } from "react";
import type { Span } from "./paint";

/** Replace the editor's highlight marks (spell, find). */
export const setMarks = StateEffect.define<Span[]>();

const marks = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(deco, tr) {
    let next = deco.map(tr.changes);
    for (const e of tr.effects) {
      if (e.is(setMarks)) {
        next = Decoration.set(
          e.value
            .filter((m) => m.to > m.from && m.to <= tr.state.doc.length)
            .map((m) => Decoration.mark({ class: m.cls }).range(m.from, m.to)),
          true,
        );
      }
    }
    return next;
  },
  provide: (f) => EditorView.decorations.from(f),
});

/** Insert `text` over the selection; the caret lands `caretOffset` into it (the
 *  desktop puts it inside paired brackets). */
export function insertAtCursor(view: EditorView | null, text: string, caretOffset = text.length) {
  if (!view) return;
  const { from, to } = view.state.selection.main;
  view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: from + caretOffset } });
  view.focus();
}

interface Props {
  initial: string;
  label: string;
  onChange(text: string): void;
  onBlur?(): void;
  onReady(view: EditorView | null): void;
  onContextMenu?(view: EditorView, e: MouseEvent): boolean;
}

/** A CodeMirror view, created once per mount (key it to replace the document). */
export default function CodeEditor({ initial, label, onChange, onBlur, onReady, onContextMenu }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const latest = useRef({ onChange, onBlur, onContextMenu });
  latest.current = { onChange, onBlur, onContextMenu };
  useEffect(() => {
    const view = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: initial,
        extensions: [
          history(),
          keymap.of([{ key: "Shift-Enter", run: insertNewline }, ...historyKeymap, ...defaultKeymap]),
          EditorView.lineWrapping,
          marks,
          EditorView.contentAttributes.of({ "aria-label": label, spellcheck: "false" }),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) latest.current.onChange(u.state.doc.toString());
          }),
          EditorView.domEventHandlers({
            blur: () => latest.current.onBlur?.(),
            contextmenu: (e, v) => latest.current.onContextMenu?.(v, e) ?? false,
          }),
        ],
      }),
    });
    view.focus();
    onReady(view);
    return () => {
      onReady(null);
      view.destroy();
    };
    // Created once per mount by design; the parent keys this component per line.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <div ref={host} className="code-editor" />;
}
```

- [ ] **Step 4: Write `web/src/editor/LineCard.tsx` and `CardList.tsx`**

```tsx
// web/src/editor/LineCard.tsx
import { memo, useEffect, useMemo, useRef, type ReactNode } from "react";
import type { Schemas } from "../api/client";
import type { Hit } from "./find";
import { jpSpans, segments, type Span } from "./paint";
import { sentenceRanges } from "./parse";
import type { Line } from "./rows";

export type Misspelling = Schemas["Misspelling"];
export const NONE: Misspelling[] = [];

export function Painted({ text, spans }: { text: string; spans: Span[] }) {
  return (
    <>
      {segments(text, spans).map((s, i) =>
        s.classes.length ? <span key={i} className={s.classes.join(" ")}>{s.text}</span> : s.text,
      )}
    </>
  );
}

interface Props {
  index: number;
  line: Line;
  active: boolean;
  parse: number; // -1 unless active
  text: string;
  highlight: Hit | null;
  misspelled: Misspelling[];
  onActivate(index: number): void;
  editor?: ReactNode;
}

/** One source paragraph and its translation. The active card holds the CodeMirror
 *  editor; the others are painted text. */
function LineCard({ index, line, active, parse, text, highlight, misspelled, onActivate, editor }: Props) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "center" });
  }, [active]);
  const source = parse === -2 ? line.raw_text : line.display_text;
  const sourceSpans = useMemo(() => {
    const spans = jpSpans(source);
    if (parse >= 0) {
      const [from, to] = sentenceRanges(line.display_text, line.sentences)[parse] ?? [0, 0];
      spans.push({ from, to, cls: "sentence-current" });
    }
    if (highlight?.field === "source") spans.push({ from: highlight.from, to: highlight.to, cls: "find-current" });
    return spans;
  }, [source, parse, line, highlight]);
  const textSpans = useMemo(() => {
    const spans: Span[] = misspelled.map((m) => ({ from: m.start, to: m.end, cls: "misspelled" }));
    if (highlight?.field === "translation") spans.push({ from: highlight.from, to: highlight.to, cls: "find-current" });
    return spans;
  }, [misspelled, highlight]);
  return (
    <article ref={ref} className={active ? "card active" : "card"} aria-current={active || undefined}
      onClick={() => { if (!active) onActivate(index); }}>
      <span className="card-number">{line.line_number + 1}</span>
      <p className="source" lang="ja"><Painted text={source} spans={sourceSpans} /></p>
      {active ? (
        editor
      ) : (
        <p className="translation" lang="en">
          {text ? <Painted text={text} spans={textSpans} /> : <span className="muted">Type your translation…</span>}
        </p>
      )}
    </article>
  );
}

export default memo(LineCard);
```

```tsx
// web/src/editor/CardList.tsx
import type { ReactNode } from "react";
import type { Hit } from "./find";
import LineCard, { NONE, type Misspelling } from "./LineCard";
import type { Image, Row } from "./rows";

interface Props {
  rows: Row[];
  active: number;
  parse: number;
  texts: Record<number, string>;
  onActivate(index: number): void;
  editor: ReactNode;
  highlight?: Hit | null;
  misspelled?(text: string): Misspelling[];
  renderImage?(image: Image): ReactNode;
}

export default function CardList({ rows, active, parse, texts, onActivate, editor, highlight, misspelled, renderImage }: Props) {
  return (
    <>
      {rows.map((row) => {
        if (row.kind === "image") return renderImage?.(row.image) ?? null;
        const text = texts[row.line.line_number] ?? "";
        const isActive = row.index === active;
        return (
          <LineCard key={row.line.line_number} index={row.index} line={row.line} active={isActive}
            parse={isActive ? parse : -1} text={text}
            highlight={highlight?.index === row.index ? highlight : null}
            misspelled={misspelled?.(text) ?? NONE} onActivate={onActivate}
            editor={isActive ? editor : undefined} />
        );
      })}
    </>
  );
}
```

- [ ] **Step 5: Write `web/src/editor/StatusBar.tsx`**

```tsx
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { SaveState } from "./saveStore";

const SAVE_TEXT: Record<SaveState, string> = {
  saved: "Saved", saving: "Saving…", unsaved: "Unsaved changes", error: "Not saved",
};

interface Props {
  title: string;
  line: number; // 1-based
  total: number;
  percent: number;
  words: number;
  phrase: string | null;
  save: { state: SaveState; error: string | null };
  onRetry(): void;
  notice?: string | null;
  extra?: ReactNode; // later tasks add controls here
}

export default function StatusBar({ title, line, total, percent, words, phrase, save, onRetry, notice, extra }: Props) {
  return (
    <div className="statusbar">
      <Link to="/">Library</Link>
      <strong>{title}</strong>
      <span>Line {line}/{total}</span>
      <span>{percent}%</span>
      <span>{words.toLocaleString()} words</span>
      {phrase && <span>{phrase}</span>}
      <span role="status" className={save.state === "error" ? "error" : save.state === "saved" ? "muted" : undefined}>
        {save.state === "error" ? `${SAVE_TEXT.error}: ${save.error}` : SAVE_TEXT[save.state]}
      </span>
      {save.state === "error" && <button onClick={onRetry}>Retry</button>}
      {notice && <span className="muted">{notice}</span>}
      {extra}
    </div>
  );
}
```

- [ ] **Step 6: Write `web/src/editor/Editor.tsx` and `EditorPage.tsx`**

```tsx
// web/src/editor/Editor.tsx
import type { EditorView } from "@codemirror/view";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, type CSSProperties } from "react";
import { Link } from "react-router";
import { api, call, type Schemas } from "../api/client";
import CardList from "./CardList";
import CodeEditor from "./CodeEditor";
import { buildRows, firstContent, hasContent, progress } from "./rows";
import StatusBar from "./StatusBar";
import { useEditor } from "./useEditor";

type Data = Schemas["DocumentLines"];

export default function Editor({ id, data }: { id: number; data: Data; onProfile(id: number | null): void }) {
  const lines = data.lines;
  const startAt = useMemo(() => {
    const p = data.document.last_position;
    return lines[p] && hasContent(lines[p].raw_text) ? p : (firstContent(lines) ?? 0);
    // the opening position only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const ed = useEditor(id, lines, startAt);
  const view = useRef<EditorView | null>(null);
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const fontPx = Number(settings.data?.editor_font_px ?? 18);
  const rows = useMemo(() => buildRows(lines, []), [lines]);
  const stats = useMemo(() => progress(lines, ed.texts), [lines, ed.texts]);
  const onReady = useCallback((v: EditorView | null) => { view.current = v; }, []);
  const current = lines[ed.active];
  // Every hook stays above this early return; later tasks add theirs here too and read
  // `current?.` (it is undefined for a chapter with no lines).

  if (!rows.some((r) => r.kind === "line")) {
    return <main><p>This chapter has no source text yet. <Link to="/">Back to the library</Link></p></main>;
  }
  const n = current.line_number;
  const editor = (
    <CodeEditor key={n} initial={ed.texts[n] ?? ""} label="Translation"
      onChange={(t) => ed.setText(n, t)} onBlur={() => void ed.store.flush()} onReady={onReady} />
  );
  return (
    <div className="editor-page" style={{ "--editor-font": `${fontPx}px` } as CSSProperties}>
      <StatusBar title={data.document.title} line={n + 1} total={lines.length}
        percent={stats.percent} words={stats.words}
        phrase={ed.parse >= 0 ? `Phrase ${ed.parse + 1}/${current.sentences.length}` : null}
        save={ed.save} onRetry={() => void ed.store.flush()} />
      <div className="editor">
        <CardList rows={rows} active={ed.active} parse={ed.parse} texts={ed.texts}
          onActivate={ed.activate} editor={editor} />
      </div>
    </div>
  );
}
```

```tsx
// web/src/editor/EditorPage.tsx
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, call } from "../api/client";
import Editor from "./Editor";

export default function EditorPage() {
  const id = Number(useParams().id);
  const [profileId, setProfileId] = useState<number | null>(null);
  const doc = useQuery({
    queryKey: ["document", id, "lines", profileId],
    queryFn: () =>
      call(api.GET("/documents/{document_id}/lines", {
        params: { path: { document_id: id }, query: profileId === null ? {} : { profile_id: profileId } },
      })),
    placeholderData: keepPreviousData,
  });
  if (doc.isPending) return <main><p className="muted">Loading…</p></main>;
  if (doc.isError) {
    return <main><p className="error" role="alert">{doc.error.message}</p><Link to="/">Back to the library</Link></main>;
  }
  return <Editor key={id} id={id} data={doc.data} onProfile={setProfileId} />;
}
```

- [ ] **Step 7: Route, styles, open link, restore last opened**

`web/src/App.tsx`: inside the `Shell` route add `<Route path="documents/:id" element={<EditorPage />} />`.

`web/src/library/DocumentRow.tsx`: in the title cell, after the title text (non-editing branch), add `{" "}<Link to={`/documents/${doc.id}`} aria-label={`Open ${doc.title}`}>Open</Link>` (import `Link` from `react-router`).

`web/src/auth/Login.tsx`: replace the `onSuccess` body with:

```tsx
    onSuccess: async (user) => {
      forgetUserData(queryClient);
      queryClient.setQueryData(["me"], user);
      let target = next;
      if (next === "/") {
        // Restore the last opened chapter (spec §6); a deleted one just answers 404 there.
        const settings = await call(api.GET("/settings")).catch(() => null);
        const last = Number(settings?.last_document_id);
        if (Number.isInteger(last) && last > 0) target = `/documents/${last}`;
      }
      navigate(target, { replace: true });
    },
```

Append to `web/src/styles.css`:

```css
.editor-page { font-size: var(--editor-font, 18px); }
.statusbar { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 0.75rem;
  align-items: center; padding: 0.4rem 1rem; font-size: 0.875rem; background: Canvas;
  border-bottom: 1px solid color-mix(in srgb, currentColor 20%, transparent); }
.editor { max-width: 60rem; margin: 0 auto; padding: 1rem 1rem 45vh; }
.card { content-visibility: auto; contain-intrinsic-size: auto 6em; padding: 0.6em 0.8em;
  margin: 0.4em 0; border: 1px solid transparent; border-radius: 6px; cursor: pointer; }
.card.active { border-color: color-mix(in srgb, currentColor 35%, transparent); cursor: auto; }
.card-number { float: right; font-size: 0.7em; opacity: 0.5; }
.source { margin: 0 0 0.3em; font-family: "Noto Serif JP", serif; }
.translation { margin: 0; white-space: pre-wrap; }
.code-editor .cm-editor.cm-focused { outline: none; }
.code-editor .cm-content { font: inherit; padding: 0; }
.jp-katakana { color: color-mix(in srgb, #2563eb 55%, currentColor); }
.jp-kanji { color: color-mix(in srgb, #b45309 45%, currentColor); }
.jp-punct { opacity: 0.6; }
.sentence-current { background: color-mix(in srgb, #2563eb 25%, transparent); border-radius: 2px; }
.find-current { background: color-mix(in srgb, #f97316 50%, transparent); }
.misspelled { text-decoration: underline wavy #dc2626; text-decoration-skip-ink: none; }
```

- [ ] **Step 8: Build and test**

Run: `cd web && npm test && npm run build`
Expected: PASS. (Behaviour is exercised end-to-end in Task 11; the save store and helpers are unit-tested.)

- [ ] **Step 9: Commit**

```bash
git add web
git commit -m "feat(editor): line cards with a CodeMirror input, debounced saving, and unsaved-edit recovery"
```

---

### Task 5: Keyboard, shortcuts screen, punctuation, font size, go to line

**Files:**
- Create: `web/src/editor/useEditorKeys.ts`, `web/src/settings/ShortcutsPage.tsx`
- Modify: `web/src/editor/Editor.tsx`, `web/src/App.tsx`, `web/src/Shell.tsx`

**Interfaces:**
- Consumes: `ACTIONS`, `PUNCTUATIONS`, `bindingOf`, `actionOf`, `effective`, `bindingProblem` (Task 3); nav helpers (Task 2); `insertAtCursor` (Task 4); `GET/PUT /shortcuts`, `DELETE /shortcuts/{action_key}`, `PUT /settings`.
- Produces: `useBindings() -> Record<action, binding>` (query key `["shortcuts"]`); `useEditorKeys(bindings, run)`; route `/settings/shortcuts`.

- [ ] **Step 1: Write `web/src/editor/useEditorKeys.ts`**

```ts
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import { api, call } from "../api/client";
import { actionOf, bindingOf, effective } from "./keymap";

export function useBindings() {
  const overrides = useQuery({ queryKey: ["shortcuts"], queryFn: () => call(api.GET("/shortcuts")) });
  return useMemo(() => effective(overrides.data ?? {}), [overrides.data]);
}

// Controls that own their keys (find field, selects, buttons, the spell menu).
const OWN_KEYS = "input, select, textarea, button, a, summary, [role=menu]";

/** One window-level capture listener (the desktop _handle_key): a bound key runs its
 *  action before CodeMirror or the browser sees it. */
export function useEditorKeys(bindings: Record<string, string>, run: (action: string) => void) {
  const latest = useRef({ bindings, run });
  latest.current = { bindings, run };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as Element | null)?.closest?.(OWN_KEYS)) return;
      const binding = bindingOf(e);
      const action = binding && actionOf(latest.current.bindings, binding);
      if (!action) return;
      e.preventDefault();
      e.stopPropagation();
      latest.current.run(action);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
}
```

- [ ] **Step 2: Dispatch actions in `Editor.tsx`**

Add imports (`useQueryClient`; `firstUntranslated, lineAtOrAfter, nextContent, prevContent` from `./rows`; `advanceParse, retreatParse` from `./parse`; `PUNCTUATIONS` from `./keymap`; `insertAtCursor` from `./CodeEditor`; `useBindings, useEditorKeys` from `./useEditorKeys`). After `const current = …`, add:

```tsx
  const queryClient = useQueryClient();
  const setFont = (px: number) => {
    const size = Math.max(12, Math.min(32, px));
    queryClient.setQueryData(["settings"], { ...settings.data, editor_font_px: size });
    void call(api.PUT("/settings", { body: { editor_font_px: size } })).catch(() => {});
  };
  const run = (action: string) => {
    const at = ed.active;
    switch (action) {
      case "save_next":
        void ed.store.flush();
        ed.activate(nextContent(lines, at));
        break;
      case "next":
      case "next_alt":
        ed.activate(nextContent(lines, at));
        break;
      case "prev":
      case "prev_alt":
        ed.activate(prevContent(lines, at));
        break;
      case "first":
        ed.activate(firstContent(lines));
        break;
      case "next_untranslated":
        // desktop: only from a line that already has a translation
        if (ed.texts[lines[at].line_number]) ed.activate(firstUntranslated(lines, ed.texts));
        break;
      case "parse_next":
        ed.setParse((p) => advanceParse(p, lines[at].sentences.length));
        break;
      case "parse_prev":
        ed.setParse((p) => retreatParse(p, lines[at].replaced));
        break;
      case "go_to_line": {
        const answer = window.prompt(`Go to line (1–${lines.length})`);
        const k = Number(answer);
        if (answer && Number.isInteger(k)) ed.activate(lineAtOrAfter(lines, k));
        break;
      }
      case "font_larger":
        setFont(fontPx + 1);
        break;
      case "font_smaller":
        setFont(fontPx - 1);
        break;
      default:
        if (action.startsWith("punct_")) insertAtCursor(view.current, PUNCTUATIONS[Number(action.slice(6))], 1);
    }
  };
  useEditorKeys(useBindings(), run);
```

`insertAtCursor(view, "…", 1)` puts the caret after a single character and inside a bracket pair, as the desktop did. Actions added by later tasks (`find`, `add_word`) fall through the `default` branch until those tasks add their cases.

Keep `Editor.tsx` under ~300 lines; if it grows past that in later tasks, move `run` into `web/src/editor/actions.ts` as `makeRun(ctx)`.

- [ ] **Step 3: Write `web/src/settings/ShortcutsPage.tsx`**

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, call } from "../api/client";
import { ACTIONS, bindingOf, bindingProblem } from "../editor/keymap";
import { useBindings } from "../editor/useEditorKeys";

/** Rebind editor keys (desktop dlg_shortcuts): press "Change", then the new key. */
export default function ShortcutsPage() {
  const queryClient = useQueryClient();
  const bindings = useBindings();
  const [capturing, setCapturing] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["shortcuts"] });
  const bind = useMutation({
    mutationFn: ({ action, binding }: { action: string; binding: string }) =>
      call(api.PUT("/shortcuts", { body: { [action]: binding } })),
    onSuccess: refresh,
  });
  const reset = useMutation({
    mutationFn: (action: string) =>
      call(api.DELETE("/shortcuts/{action_key}", { params: { path: { action_key: action } } })),
    onSuccess: refresh,
  });
  useEffect(() => {
    if (!capturing) return;
    const onKey = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.key === "Escape") return setCapturing(null);
      const binding = bindingOf(e);
      if (!binding) return; // a bare modifier: wait for the key
      const why = bindingProblem(bindings, capturing, binding);
      setProblem(why);
      if (!why) bind.mutate({ action: capturing, binding });
      setCapturing(null);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [capturing, bindings, bind]);
  const error = problem ?? bind.error?.message ?? reset.error?.message;
  return (
    <main>
      <h1>Keyboard shortcuts</h1>
      {error && <p className="error" role="alert">{error}</p>}
      <table>
        <thead><tr><th>Action</th><th>Key</th><th /></tr></thead>
        <tbody>
          {ACTIONS.map((a) => (
            <tr key={a.key}>
              <td>{a.label}</td>
              <td><kbd>{bindings[a.key]}</kbd></td>
              <td className="toolbar">
                <button onClick={() => { setProblem(null); setCapturing(a.key); }} disabled={bind.isPending}>
                  {capturing === a.key ? "Press a key… (Esc cancels)" : "Change"}
                </button>
                {bindings[a.key] !== a.binding && (
                  <button onClick={() => reset.mutate(a.key)} disabled={reset.isPending}>Reset to {a.binding}</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
```

`App.tsx`: add `<Route path="settings/shortcuts" element={<ShortcutsPage />} />` inside the `Shell` route. `Shell.tsx`: add `<NavLink to="/settings/shortcuts">Shortcuts</NavLink>` after the Library link.

- [ ] **Step 4: Build and test**

Run: `cd web && npm test && npm run build` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(editor): keyboard navigation, parse, inserts, font size, and a shortcuts screen"
```

---

### Task 6: Find bar

**Files:**
- Create: `web/src/editor/FindBar.tsx`
- Modify: `web/src/editor/Editor.tsx`, `web/src/styles.css`

**Interfaces:**
- Consumes: `findHits`, `wrapStep`, `firstFrom`, `type Hit` (Task 2); `setMarks` (Task 4).
- Produces: `FindBar({needle, onNeedle, position, total, onStep(dir), onClose})` — reused by Task 9.

- [ ] **Step 1: Write `web/src/editor/FindBar.tsx`**

```tsx
import { useEffect, useRef } from "react";

interface Props {
  needle: string;
  onNeedle(needle: string): void;
  position: number; // -1 before the first step
  total: number;
  onStep(dir: 1 | -1): void;
  onClose(): void;
}

/** Find (spec §5): Enter next, Shift+Enter previous, Escape closes; wraps; n/total. */
export default function FindBar({ needle, onNeedle, position, total, onStep, onClose }: Props) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);
  return (
    <div className="findbar" role="search">
      <input ref={input} aria-label="Find" value={needle} className={needle && !total ? "notfound" : undefined}
        onChange={(e) => onNeedle(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onStep(e.shiftKey ? -1 : 1);
          } else if (e.key === "Escape") {
            e.preventDefault();
            onClose();
          }
        }} />
      <span aria-live="polite">{needle ? `${total ? position + 1 : 0}/${total}` : ""}</span>
      <button onClick={() => onStep(-1)} aria-label="Previous match">↑</button>
      <button onClick={() => onStep(1)} aria-label="Next match">↓</button>
      <button onClick={onClose} aria-label="Close find">×</button>
    </div>
  );
}
```

- [ ] **Step 2: Wire it into `Editor.tsx`**

State and derived hits:

```tsx
  const [find, setFind] = useState<{ open: number; needle: string; at: number }>({ open: 0, needle: "", at: -1 });
  const hits = useMemo(
    () => findHits(rows.flatMap((r) => r.kind === "line"
      ? [{ index: r.index, source: r.line.display_text, translation: ed.texts[r.line.line_number] ?? "" }]
      : []), find.needle),
    [rows, ed.texts, find.needle],
  );
  const hit = find.open && find.at >= 0 ? (hits[find.at] ?? null) : null;
  const step = (dir: 1 | -1) => {
    const at = find.at < 0 && dir === 1 ? firstFrom(hits, ed.active) : wrapStep(find.at, hits.length, dir);
    setFind((f) => ({ ...f, at }));
    if (hits[at]) ed.activate(hits[at].index);
  };
```

`find.open` is a counter: `0` is closed, and each Ctrl+F increments it, which remounts the bar and refocuses it. Add to `run`:

```tsx
      case "find":
        setFind((f) => ({ ...f, open: f.open + 1 }));
        break;
```

Render the bar under the status bar:

```tsx
      {find.open > 0 && (
        <FindBar key={find.open} needle={find.needle} position={find.at} total={hits.length}
          onNeedle={(needle) => setFind((f) => ({ ...f, needle, at: -1 }))} onStep={step}
          onClose={() => { setFind((f) => ({ ...f, open: 0, at: -1 })); view.current?.focus(); }} />
      )}
```

Pass `highlight={hit}` to `CardList`. Highlight a translation hit inside the active CodeMirror view:

```tsx
  useEffect(() => {
    const marks = hit && hit.index === ed.active && hit.field === "translation"
      ? [{ from: hit.from, to: hit.to, cls: "find-current" }] : [];
    view.current?.dispatch({ effects: setMarks.of(marks) });
  }, [hit, ed.active]);
```

(Task 7 merges spell marks into this same effect.)

Append to `styles.css`:

```css
.findbar { position: sticky; top: 2.4rem; z-index: 2; display: flex; gap: 0.4rem; align-items: center;
  max-width: 60rem; margin: 0 auto; padding: 0.3rem 1rem; background: Canvas; }
.findbar input.notfound { background: color-mix(in srgb, #dc2626 20%, Canvas); }
```

- [ ] **Step 3: Build and test**

Run: `cd web && npm test && npm run build` — Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat(editor): find bar across source and translation, wrapping, with a counter"
```

---

### Task 7: Spellcheck, suggestions, add to dictionary, profile switcher

**Files:**
- Create: `web/src/editor/spell.ts`, `spell.test.ts`, `useSpell.ts`, `SpellMenu.tsx`
- Modify: `web/src/editor/Editor.tsx`, `web/src/styles.css`

**Interfaces:**
- Consumes: `POST /spell/check` (≤200 texts, ≤100,000 chars each, ≤200,000 total; spans in UTF-16), `PUT /profiles/{profile_id}/words/{word}`, `GET /profiles`; `setMarks`, `CodeEditor.onContextMenu` (Task 4); `onProfile` (Task 4).
- Produces: `spellBatches(texts, maxTexts = 200, maxChars = 200_000) -> string[][]` (drops texts over 100,000 chars); `useSpell(profileId, texts) -> {available, misspelled(text), forget()}`.

- [ ] **Step 1: Write the failing test `web/src/editor/spell.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import { spellBatches } from "./spell";

describe("spellBatches", () => {
  it("caps texts per batch", () => {
    expect(spellBatches(["a", "b", "c"], 2)).toEqual([["a", "b"], ["c"]]);
  });
  it("caps characters per batch", () => {
    expect(spellBatches(["aaaa", "bbbb", "cc"], 200, 6)).toEqual([["aaaa"], ["bbbb", "cc"]]);
  });
  it("drops texts the API would refuse and empty ones", () => {
    expect(spellBatches(["x".repeat(100_001), "", "ok"])).toEqual([["ok"]]);
  });
});
```

Run: `cd web && npm test` — Expected: FAIL (cannot resolve `./spell`).

- [ ] **Step 2: Write `web/src/editor/spell.ts`**

```ts
const MAX_TEXT_CHARS = 100_000;

/** Request batches within the /spell/check caps (200 texts, 200,000 chars in total). */
export function spellBatches(texts: string[], maxTexts = 200, maxChars = 200_000): string[][] {
  const batches: string[][] = [];
  let batch: string[] = [];
  let chars = 0;
  for (const t of texts) {
    if (!t || t.length > MAX_TEXT_CHARS) continue;
    if (batch.length && (batch.length === maxTexts || chars + t.length > maxChars)) {
      batches.push(batch);
      batch = [];
      chars = 0;
    }
    batch.push(t);
    chars += t.length;
  }
  if (batch.length) batches.push(batch);
  return batches;
}
```

Run: `npm test` — Expected: PASS.

- [ ] **Step 3: Write `web/src/editor/useSpell.ts`**

```ts
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api, call } from "../api/client";
import { NONE, type Misspelling } from "./LineCard";
import { spellBatches } from "./spell";

/** Misspellings per translation text, fetched in batches 500 ms after typing stops.
 *  Keyed by text, so a card's array stays identical until its text changes. */
export function useSpell(profileId: number | null, texts: string[]) {
  const cache = useRef(new Map<string, Misspelling[]>());
  const [version, bump] = useReducer((n: number) => n + 1, 0);
  const [available, setAvailable] = useState(true);
  const forget = useCallback(() => {
    cache.current = new Map();
    bump();
  }, []);
  useEffect(forget, [profileId, forget]);
  const key = texts.join("\u0000");
  useEffect(() => {
    const missing = [...new Set(texts)].filter((t) => t && !cache.current.has(t));
    if (!missing.length) return;
    let live = true;
    const timer = setTimeout(async () => {
      for (const batch of spellBatches(missing)) {
        // ponytail: spellcheck is best-effort; a failed batch is retried on the next edit
        const result = await call(api.POST("/spell/check", { body: { texts: batch, profile_id: profileId } })).catch(() => null);
        if (!live || !result) return;
        setAvailable(result.available);
        batch.forEach((t, i) => cache.current.set(t, result.results[i]));
      }
      if (live) bump();
    }, 500);
    return () => {
      live = false;
      clearTimeout(timer);
    };
    // `key` stands for `texts`; `version` re-runs after forget()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, profileId, version]);
  const misspelled = useCallback((t: string) => cache.current.get(t) ?? NONE,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [version]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const known = useCallback((t: string) => cache.current.has(t), [version]);
  return { available, misspelled, forget, known };
}
```

The `version`-dependent `misspelled` changes identity after each fetch, so `CardList` re-renders and cards whose text was checked pick up their (new, stable) array.

- [ ] **Step 4: Write `web/src/editor/SpellMenu.tsx`**

```tsx
import { useEffect, useRef } from "react";
import type { Misspelling } from "./LineCard";

interface Props {
  x: number;
  y: number;
  word: Misspelling;
  onPick(suggestion: string): void;
  onAdd(): void;
  onClose(): void;
}

/** The right-click menu on a misspelled word: suggestions, then "Add to dictionary". */
export default function SpellMenu({ x, y, word, onPick, onAdd, onClose }: Props) {
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    menu.current?.querySelector("button")?.focus();
    const away = (e: MouseEvent) => { if (!menu.current?.contains(e.target as Node)) onClose(); };
    window.addEventListener("mousedown", away);
    return () => window.removeEventListener("mousedown", away);
  }, [onClose]);
  return (
    <div ref={menu} className="spell-menu" role="menu" style={{ left: x, top: y }}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      {word.suggestions.length ? (
        word.suggestions.map((s) => (
          <button key={s} role="menuitem" onClick={() => onPick(s)}><strong>{s}</strong></button>
        ))
      ) : (
        <span className="muted">No suggestions</span>
      )}
      <hr />
      <button role="menuitem" onClick={onAdd}>Add “{word.word}” to the dictionary</button>
    </div>
  );
}
```

- [ ] **Step 5: Wire spelling into `Editor.tsx`**

```tsx
  const profileId = data.profile?.id ?? null;
  const spell = useSpell(profileId, lines.map((l) => ed.texts[l.line_number] ?? ""));
  const [menu, setMenu] = useState<{ x: number; y: number; word: Misspelling } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const addWord = async (word: string) => {
    if (!profileId) return setNotice("No profile to add words to");
    if (!word || /\s/.test(word)) return setNotice("Select a single word first");
    try {
      await call(api.PUT("/profiles/{profile_id}/words/{word}", { params: { path: { profile_id: profileId, word } } }));
      spell.forget();
      setNotice(`Added “${word}” to the dictionary`);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Could not add the word");
    }
  };
  const onContextMenu = (v: EditorView, e: MouseEvent) => {
    const pos = v.posAtCoords({ x: e.clientX, y: e.clientY });
    const text = v.state.doc.toString();
    const word = pos == null ? undefined
      : spell.misspelled(text).find((m) => m.start <= pos && pos <= m.end && text.slice(m.start, m.end) === m.word);
    if (!word) return false;
    e.preventDefault();
    setMenu({ x: e.clientX, y: e.clientY, word });
    return true;
  };
```

- Add `case "add_word": { const v = view.current; if (v) { const { from, to } = v.state.selection.main; void addWord(v.state.sliceDoc(from, to).trim()); } break; }` to `run`.
- Pass `onContextMenu={onContextMenu}` to the active `CodeEditor`, and `misspelled={spell.misspelled}` to `CardList`.
- Render the menu: `{menu && <SpellMenu {...menu} onClose={() => setMenu(null)} onAdd={() => { void addWord(menu.word.word); setMenu(null); }} onPick={(s) => { view.current?.dispatch({ changes: { from: menu.word.start, to: menu.word.end, insert: s } }); setMenu(null); view.current?.focus(); }} />}`.
- Replace the Task 6 marks effect so both layers reach the active view, and stale spell marks are kept (mapped through edits) until the current text has been checked:

```tsx
  const activeText = current ? (ed.texts[current.line_number] ?? "") : "";
  useEffect(() => {
    const v = view.current;
    if (!v || (!spell.known(activeText) && !(hit && hit.index === ed.active))) return;
    const marks = spell.misspelled(activeText).map((m) => ({ from: m.start, to: m.end, cls: "misspelled" }));
    if (hit && hit.index === ed.active && hit.field === "translation") marks.push({ from: hit.from, to: hit.to, cls: "find-current" });
    v.dispatch({ effects: setMarks.of(marks) });
  }, [spell.misspelled, spell.known, activeText, hit, ed.active]);
```

- Profile switcher and spell state through `StatusBar`'s `extra`, plus `notice={notice}`:

```tsx
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => call(api.GET("/profiles")) });
  // …
  extra={<>
    <select aria-label="Profile" value={profileId ?? ""} onChange={(e) => onProfile(e.target.value ? Number(e.target.value) : null)}>
      {!profileId && <option value="">No profile</option>}
      {(profiles.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
    {!spell.available && <span className="muted">Spellcheck unavailable</span>}
  </>}
```

`onProfile` comes from `EditorPage` (Task 4); destructure it in `Editor`'s parameters. Changing it refetches the lines with the new glossary while the editor keeps its texts.

Append to `styles.css`:

```css
.spell-menu { position: fixed; z-index: 10; display: grid; min-width: 12rem; padding: 0.25rem;
  background: Canvas; border: 1px solid color-mix(in srgb, currentColor 30%, transparent);
  border-radius: 6px; box-shadow: 0 4px 16px rgb(0 0 0 / 0.2); }
.spell-menu button { text-align: left; background: none; border: 0; padding: 0.3rem 0.5rem; font: inherit; }
.spell-menu button:focus, .spell-menu button:hover { background: color-mix(in srgb, currentColor 12%, transparent); }
```

- [ ] **Step 6: Build and test**

Run: `cd web && npm test && npm run build` — Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src
git commit -m "feat(editor): spellcheck underlines, suggestions, add to dictionary, and a profile switcher"
```

---

### Task 8: Inline images

**Files:**
- Create: `web/src/editor/ImageCard.tsx`
- Modify: `web/src/editor/Editor.tsx`, `web/src/styles.css`

**Interfaces:**
- Consumes: `GET /documents/{id}/images`, `GET /images/{id}`, `PATCH /images/{id}`; `buildRows`, `CardList.renderImage` (Task 4).
- Produces: `ImageCard({image, collapsed})`; setting `images_collapsed` (boolean).

- [ ] **Step 1: Write `web/src/editor/ImageCard.tsx`**

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, call } from "../api/client";
import type { Image } from "./rows";

/** An illustration between lines (desktop card_list.ImageCard): collapse toggle, cover
 *  marker, include-in-export checkbox. Not a line: no navigation, spellcheck or progress. */
export default function ImageCard({ image, collapsed }: { image: Image; collapsed: boolean }) {
  const [open, setOpen] = useState(!collapsed);
  useEffect(() => setOpen(!collapsed), [collapsed]);
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: (exclude: boolean) =>
      call(api.PATCH("/images/{image_id}", { params: { path: { image_id: image.id } }, body: { exclude_export: exclude } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["document", image.document_id, "images"] }),
  });
  return (
    <figure className="image-card">
      <figcaption className="toolbar">
        <button aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} Image</button>
        {image.is_cover && <span className="badge">Cover</span>}
        <label>
          <input type="checkbox" checked={!image.exclude_export} disabled={toggle.isPending}
            onChange={(e) => toggle.mutate(!e.target.checked)} /> Include in export
        </label>
        {toggle.isError && <span className="error">{toggle.error.message}</span>}
      </figcaption>
      {open && <img src={`/api/images/${image.id}`} alt={image.src_path} loading="lazy" />}
    </figure>
  );
}
```

- [ ] **Step 2: Wire into `Editor.tsx`**

```tsx
  const images = useQuery({
    queryKey: ["document", id, "images"],
    queryFn: () => call(api.GET("/documents/{document_id}/images", { params: { path: { document_id: id } } })),
  });
  const rows = useMemo(() => buildRows(lines, images.data ?? []), [lines, images.data]);
  const imagesCollapsed = Boolean(settings.data?.images_collapsed);
```

(Replace the Task 4 `rows` line.) Pass `renderImage={(image) => <ImageCard key={`img-${image.id}`} image={image} collapsed={imagesCollapsed} />}` to `CardList`. Add a toggle to `StatusBar`'s `extra` when `images.data?.length` is non-zero:

```tsx
    {images.data?.length ? (
      <button onClick={() => {
        queryClient.setQueryData(["settings"], { ...settings.data, images_collapsed: !imagesCollapsed });
        void call(api.PUT("/settings", { body: { images_collapsed: !imagesCollapsed } })).catch(() => {});
      }}>{imagesCollapsed ? "Show images" : "Collapse images"}</button>
    ) : null}
```

Append to `styles.css`:

```css
.image-card { margin: 0.6em 0; }
.image-card img { display: block; max-width: min(100%, 400px); margin: 0.4em auto; }
.badge { padding: 0 0.4em; border-radius: 4px; font-size: 0.75em;
  background: color-mix(in srgb, #16a34a 25%, transparent); }
```

- [ ] **Step 3: Build and test**

Run: `cd web && npm test && npm run build` — Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat(editor): inline illustrations with collapse, cover marker, and export toggle"
```

---

### Task 9: Edit Source and Split view

**Files:**
- Create: `web/src/editor/SourcePage.tsx`
- Modify: `web/src/App.tsx`, `web/src/editor/Editor.tsx` (links)

**Interfaces:**
- Consumes: `PUT /documents/{id}/source` (Task 1; 409 needs `force`), `POST /documents/{id}/split` (`{cuts: [{start, title}]}` → `DocumentOut[]`), `GET /documents/{id}/lines`; `sourceText` (Task 2), `cutsFromText`, `insertMarker`, `SPLIT_MARKER` (Task 2), `findIn`, `wrapStep` (Task 2), `CodeEditor`, `setMarks` (Task 4), `FindBar` (Task 6), `useBindings`, `bindingOf` (Task 3, 5); `invalidateLibrary` (`web/src/library/queries.ts`).
- Produces: routes `/documents/:id/source` and `/documents/:id/split` → `SourcePage({mode: "edit" | "split"})`.

- [ ] **Step 1: Write `web/src/editor/SourcePage.tsx`**

```tsx
import { EditorView } from "@codemirror/view";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, ApiError, call } from "../api/client";
import { invalidateLibrary } from "../library/queries";
import CodeEditor, { setMarks } from "./CodeEditor";
import { cutsFromText, insertMarker, SPLIT_MARKER } from "./cuts";
import FindBar from "./FindBar";
import { findIn, wrapStep } from "./find";
import { bindingOf } from "./keymap";
import { sourceText } from "./rows";
import { useBindings } from "./useEditorKeys";

/** Edit Source and Split (desktop _EditSourceDialog / _SplitChapterDialog): one line per
 *  line, $ marks a continuation. Split: place markers where new chapters start. */
export default function SourcePage({ mode }: { mode: "edit" | "split" }) {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const doc = useQuery({
    queryKey: ["document", id, "lines", null],
    queryFn: () => call(api.GET("/documents/{document_id}/lines", { params: { path: { document_id: id } } })),
  });
  const view = useRef<EditorView | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [find, setFind] = useState({ open: 0, needle: "", at: -1 });
  const bindings = useBindings();
  const current = text ?? (doc.data ? sourceText(doc.data.lines) : "");
  const hits = useMemo(() => findIn(current, find.needle), [current, find.needle]);

  const done = async (to: number) => {
    await queryClient.invalidateQueries({ queryKey: ["document", id] });
    await invalidateLibrary(queryClient);
    navigate(`/documents/${to}`);
  };
  const save = useMutation({
    mutationFn: (force: boolean) =>
      call(api.PUT("/documents/{document_id}/source", { params: { path: { document_id: id } }, body: { text: current, force } })),
    onSuccess: () => done(id),
    onError: (e, force) => {
      if (e instanceof ApiError && e.status === 409 && !force
          && window.confirm(`${e.message}. Translations will then sit next to different source lines. Save anyway?`)) {
        save.mutate(true);
      }
    },
  });
  const split = useMutation({
    mutationFn: (cuts: { start: number; title: string }[]) =>
      call(api.POST("/documents/{document_id}/split", { params: { path: { document_id: id } }, body: { cuts } })),
    onSuccess: (docs) => done(docs[0]?.id ?? id),
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (bindingOf(e) !== bindings.find) return;
      e.preventDefault();
      setFind((f) => ({ ...f, open: f.open + 1 }));
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [bindings.find]);

  const step = (dir: 1 | -1) => {
    const at = wrapStep(find.at, hits.length, dir);
    setFind((f) => ({ ...f, at }));
    const range = hits[at];
    view.current?.dispatch({
      effects: range
        ? [setMarks.of([{ from: range[0], to: range[1], cls: "find-current" }]), EditorView.scrollIntoView(range[0], { y: "center" })]
        : [setMarks.of([])],
    });
  };

  if (doc.isPending) return <main><p className="muted">Loading…</p></main>;
  if (doc.isError) return <main><p className="error" role="alert">{doc.error.message}</p></main>;
  const error = problem ?? (save.isError && !(save.error instanceof ApiError && save.error.status === 409) ? save.error.message : null)
    ?? split.error?.message;
  return (
    <main>
      <p><Link to={`/documents/${id}`}>← Back to the editor</Link></p>
      <h1>{mode === "edit" ? "Edit source" : "Split chapter"} — {doc.data.document.title}</h1>
      <p className="muted">
        {mode === "edit"
          ? "One line per paragraph; a line starting with $ continues the previous one. Translations stay with their line position."
          : `Put the cursor on the first line of each new chapter and press "Insert split here"; type its title after ${SPLIT_MARKER}.`}
      </p>
      {find.open > 0 && (
        <FindBar key={find.open} needle={find.needle} position={find.at} total={hits.length}
          onNeedle={(needle) => setFind((f) => ({ ...f, needle, at: -1 }))} onStep={step}
          onClose={() => { setFind((f) => ({ ...f, open: 0, at: -1 })); view.current?.dispatch({ effects: setMarks.of([]) }); view.current?.focus(); }} />
      )}
      <div className="source-editor">
        <CodeEditor initial={current} label="Source text" onChange={setText}
          onReady={(v) => { view.current = v; }} />
      </div>
      <div className="toolbar">
        {mode === "edit" ? (
          <button onClick={() => save.mutate(false)} disabled={save.isPending}>Save</button>
        ) : (
          <>
            <button onClick={() => {
              const v = view.current;
              if (!v) return;
              const next = insertMarker(v.state.doc.toString(), v.state.selection.main.head);
              v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: next.text }, selection: { anchor: next.caret } });
              v.focus();
            }}>Insert split here</button>
            <button disabled={!current.includes(SPLIT_MARKER) || split.isPending} onClick={() => {
              const cuts = cutsFromText(current);
              setProblem(cuts.length ? null : "Place at least one split marker between two lines.");
              if (cuts.length) split.mutate(cuts);
            }}>Split</button>
          </>
        )}
        <Link to={`/documents/${id}`}>Cancel</Link>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </main>
  );
}
```

Append to `styles.css`: `.source-editor { border: 1px solid color-mix(in srgb, currentColor 25%, transparent); border-radius: 6px; padding: 0.5rem; font-family: ui-monospace, monospace; max-height: 70vh; overflow: auto; }`

- [ ] **Step 2: Routes and links**

`App.tsx`: `<Route path="documents/:id/source" element={<SourcePage mode="edit" />} />` and `<Route path="documents/:id/split" element={<SourcePage mode="split" />} />`. In `Editor.tsx`, add to `StatusBar`'s `extra`: `<Link to={`/documents/${id}/source`}>Edit source</Link> <Link to={`/documents/${id}/split`}>Split</Link>`, and in the no-content branch replace "Back to the library" with `<Link to={`/documents/${id}/source`}>Edit source</Link>`.

The editor's unmount flush (Task 4) runs when Edit Source opens, so pending translations are saved before the source changes.

- [ ] **Step 3: Build and test**

Run: `cd web && npm test && npm run build` — Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat(editor): edit source with a line-count guard, and split a chapter at markers"
```

---

### Task 10: Carry-over from 3a

**Files:**
- Modify: `web/src/library/Volumes.tsx`, `web/src/library/SeriesPage.tsx`, `web/src/library/Picker.tsx`, `web/src/library/DocumentRow.tsx`

**Interfaces:**
- Consumes: `PATCH /documents/{id}` with `{volume_id: null}`.

- [ ] **Step 1: Remove a chapter from a volume**

In `Volumes.tsx` `VolumeEditor`, under the summary, list the volume's chapters with a remove button:

```tsx
  const unassign = useMutation({
    mutationFn: (documentId: number) =>
      call(api.PATCH("/documents/{document_id}", { params: { path: { document_id: documentId } }, body: { volume_id: null } })),
    onSuccess: onChanged,
  });
  // …inside <details>, before the form:
  <ul>
    {docs.filter((d) => d.volume_id === volume.id).map((d) => (
      <li key={d.id}>{d.title}{" "}
        <button onClick={() => unassign.mutate(d.id)} disabled={unassign.isPending} aria-label={`Remove ${d.title} from ${volume.title}`}>Remove</button>
      </li>
    ))}
  </ul>
```

Include `unassign.error` in the component's `error` expression.

- [ ] **Step 2: Label the ZIP exports**

In `SeriesPage.tsx`, change the link texts to `Markdown ZIP (complete chapters only)` and `Ruby Markdown ZIP (complete chapters only)`. (The server skips incomplete chapters and reports the count only in a header a plain download cannot show.)

- [ ] **Step 3: Picker table header and labels**

In `Picker.tsx`, give each group's `<table>` a `<thead>`: `<tr><th><span className="visually-hidden">Select</span></th><th>Title</th><th>Progress</th><th>Edited</th><th>Series</th><th>Export</th></tr>`. In `DocumentRow.tsx`, change the rename input's `aria-label` to `` `New title for ${doc.title}` ``. Append to `styles.css`: `.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }`

- [ ] **Step 4: Build and test**

Run: `cd web && npm test && npm run build` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): remove a chapter from a volume, label partial ZIP exports, label picker columns"
```

---

### Task 11: Playwright smoke flows

**Files:**
- Create: `tools/e2e_seed.py`, `web/playwright.config.ts`, `web/e2e/global-setup.ts`, `web/e2e/editor.spec.ts`
- Modify: `web/vite.config.ts`, `web/package.json` (+ lock), `.gitignore`, `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the whole app. Seeds user `e2e@example.com` / `e2e-password-123` and chapter "E2E chapter" with lines `一行目です。`, `二行目です。`, `三行目です。`.

- [ ] **Step 1: Write `tools/e2e_seed.py`**

```python
"""Reset the Playwright database and seed one user and one chapter.

    TA_DATABASE_URL=postgresql+psycopg://ta:ta@localhost:5432/ta_e2e python -m tools.e2e_seed
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tools.seed_admin import create_admin

EMAIL, PASSWORD = "e2e@example.com", "e2e-password-123"
LINES = ["一行目です。", "二行目です。", "三行目です。"]


def main() -> None:
    url = make_url(os.environ["TA_DATABASE_URL"])
    if not (url.database or "").endswith("_e2e"):
        raise SystemExit(f"refusing to reset {url.database!r}: the name must end in _e2e")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    root = Path(__file__).resolve().parent.parent
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, cwd=root)

    from api.db import SessionLocal
    from api.library import write_lines
    from api.models import Document

    with SessionLocal() as db:
        user = create_admin(db, EMAIL, PASSWORD)
        doc = Document(user_id=user.id, title="E2E chapter")
        db.add(doc)
        db.flush()
        write_lines(db, doc.id, [
            {"line_number": i, "prefix": "%", "raw_text": raw, "translated_text": ""}
            for i, raw in enumerate(LINES)
        ])
        db.commit()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make the dev proxy target configurable**

In `web/vite.config.ts`, change `target: "http://127.0.0.1:8000"` to `target: process.env.TA_API_URL ?? "http://127.0.0.1:8000"`.

- [ ] **Step 3: Install Playwright and write the config**

```bash
cd web && npm install -D @playwright/test && npx playwright install chromium
```

Add `"e2e": "playwright test"` to `scripts`. Add to `.gitignore`: `web/test-results/` and `web/playwright-report/`. Exclude `e2e` from vitest: in `vite.config.ts` set `test: { environment: "node", include: ["src/**/*.test.ts"] }`.

```ts
// web/playwright.config.ts
import { defineConfig } from "@playwright/test";

export const E2E_DB = process.env.TA_E2E_DATABASE_URL ?? "postgresql+psycopg://ta:ta@localhost:5432/ta_e2e";
const SECRET = process.env.TA_SECRET_KEY ?? "e2e-secret-key-at-least-32-characters-long";
const API = "http://127.0.0.1:8001";

export default defineConfig({
  testDir: "e2e",
  workers: 1,
  timeout: 30_000,
  globalSetup: "./e2e/global-setup.ts",
  use: { baseURL: "http://localhost:5174" },
  webServer: [
    {
      command: "cd .. && python -m uvicorn api.main:app --port 8001",
      url: `${API}/healthz`,
      env: { ...process.env, TA_DATABASE_URL: E2E_DB, TA_SECRET_KEY: SECRET, TA_COOKIE_SECURE: "false" } as Record<string, string>,
    },
    {
      command: "npm run dev -- --port 5174 --strictPort",
      url: "http://localhost:5174",
      env: { ...process.env, TA_API_URL: API } as Record<string, string>,
    },
  ],
});
```

```ts
// web/e2e/global-setup.ts
import { execFileSync } from "node:child_process";
import { E2E_DB } from "../playwright.config";

export default function globalSetup() {
  execFileSync("python", ["-m", "tools.e2e_seed"], {
    cwd: "..",
    stdio: "inherit",
    env: { ...process.env, TA_DATABASE_URL: E2E_DB, TA_SECRET_KEY: process.env.TA_SECRET_KEY ?? "e2e-secret-key-at-least-32-characters-long" },
  });
}
```

- [ ] **Step 4: Write `web/e2e/editor.spec.ts`**

```ts
import { expect, test, type Page } from "@playwright/test";

async function openChapter(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/");
  await page.getByRole("link", { name: "Open E2E chapter" }).click();
}

test("sign in and open a document", async ({ page }) => {
  await openChapter(page);
  await expect(page.getByText("一行目です。")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Translation" })).toBeFocused();
});

test("translate two lines and the save indicator settles", async ({ page }) => {
  await openChapter(page);
  await page.getByRole("textbox", { name: "Translation" }).click();
  await page.keyboard.type("This is the first line.");
  await page.keyboard.press("Enter");
  await page.keyboard.type("This is the second line.");
  await expect(page.getByRole("status")).toHaveText("Saved", { timeout: 5_000 });
  await page.reload();
  await expect(page.getByText("This is the first line.")).toBeVisible();
  await expect(page.getByText("This is the second line.")).toBeVisible();
});
```

- [ ] **Step 5: Run it locally**

With the venv active and Postgres up: `cd web && npm run e2e`. Expected: 2 passed.

- [ ] **Step 6: Add the CI job**

Append to `.github/workflows/ci.yml`:

```yaml
  e2e:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: ta
          POSTGRES_PASSWORD: ta
          POSTGRES_DB: ta
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U ta" --health-interval 5s
          --health-timeout 5s --health-retries 10
    env:
      TA_SECRET_KEY: ci-secret-key-at-least-32-characters-long
      TA_E2E_DATABASE_URL: postgresql+psycopg://ta:ta@localhost:5432/ta_e2e
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: pyproject.toml
      - run: sudo apt-get update && sudo apt-get install -y libenchant-2-2 hunspell-en-us
      - run: pip install -e ".[dev]"
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
        working-directory: web
      - run: npx playwright install --with-deps chromium
        working-directory: web
      - run: npm run e2e
        working-directory: web
```

- [ ] **Step 7: Commit**

```bash
git add tools/e2e_seed.py web .gitignore .github/workflows/ci.yml
git commit -m "test(e2e): Playwright flows for opening a chapter and saving two translations"
```

---

### Task 12: Docs

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: Update the docs**

`README.md`: status "phases 1–2, 3a and 3b"; add the Phase 3b plan link; under "Web app (development)" add `npm run e2e   # Playwright; needs the venv active and Postgres up (database ta_e2e is reset)`. Add to "Design decisions":

```markdown
- **The editor saves as you type.** Edits are kept per line and sent 800 ms after typing
  stops (or on leaving a line); the status bar says Saved only for text the server accepted.
  On page hide the rest goes out with `fetch` keepalive and is stashed in sessionStorage, so
  a closed tab or expired session cannot lose it — it is re-sent when the chapter reopens.
- **Every editor key is rebindable** (Shortcuts screen). A key another action uses, or one the
  browser reserves (Ctrl+N/T/W), is refused.
- **Edit Source keeps one line per line** and does not re-split sentences; a `$` line continues
  the previous paragraph. A save that changes the number of lines asks for confirmation,
  because translations stay attached by line position.
- **Japanese highlighting is by character class** (kanji/kana/punctuation); part-of-speech
  colouring arrives with MeCab in phase 5.
```

`CLAUDE.md` "What this is": phase 3b paragraph ("editor screen: cards, CodeMirror input, saving, keymap, find, spell, images, Edit Source/Split; Playwright smoke flows. Phases 4–6 are next.") and add `npm run e2e` to Commands.

- [ ] **Step 2: Final gate**

Run: `source .venv/bin/activate && ruff check . && pytest -q && (cd web && npm test && npm run build && npm run e2e)`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: phase 3b status, editor design decisions, and e2e command"
```

---

## Self-Review Notes

- **Spec coverage (§5, §12, §15 phase 3):**
  - Line-card list: Tasks 4 and 8.
  - Dirty-lines saving: the debounced flush, blur, document close and page hide; the save indicator; the unload guard. Tasks 3 and 4.
  - Keymap and rebinding: Tasks 3 and 5.
  - Parse navigation with `parse_chars` (server sentences): Tasks 2, 4 and 5.
  - Go to line, font size, punctuation inserts: Task 5.
  - Find bar in the editor and in source editing: Tasks 6 and 9.
  - Glossary substitution on display, plus the raw toggle (parse −2): Tasks 4 and 5.
  - Spellcheck with custom words, suggestions and add-to-dictionary: Task 7.
  - Japanese highlighting: Tasks 2 and 4.
  - Progress, word count and line counter: Tasks 2 and 4.
  - Inline images with collapse, cover marker and export checkbox: Task 8.
  - Restore the last opened document: Task 4.
  - Split markers UI (phase 2 deferral): Task 9.
  - vitest for keymap, dirty store and progress: Tasks 2 and 3.
  - Playwright: two of the three flows, in Task 11 (Deviation 8).
- **Carry-over from 3a (memory `phase3b-carryover`):**
  - Remove a chapter from a volume, ZIP labels, picker `<thead>` and aria-labels: Task 10.
  - Browser smoke: Task 11's Playwright plus a manual check of drag reorder in Firefox at handoff.
  - Download links bypassing the 401 flow: not built. A failed download after expiry is the accepted limitation of `<a download>`.
- **Known limitations:**
  - The spell cache grows with each distinct text typed in a session (`useSpell`).
  - A save of 5000 or more dirty lines is cut at 5000 per batch; the rest go in the next flush.
  - `last_position` bumps `updated_at` (Deviation 9).
- **Names used across tasks:**
  - `rows.ts`: `Line`, `Image`, `Row`, `hasContent`, `buildRows`, `nextContent`, `prevContent`, `firstContent`, `firstUntranslated`, `lineAtOrAfter`, `progress`, `sourceText`
  - `parse.ts`: `advanceParse`, `retreatParse`, `sentenceRanges`
  - `find.ts`: `Hit`, `findIn`, `findHits`, `wrapStep`, `firstFrom`
  - `paint.ts`: `Span`, `jpSpans`, `segments`
  - `cuts.ts`: `SPLIT_MARKER`, `cutsFromText`, `insertMarker`
  - `keymap.ts`: `ACTIONS`, `PUNCTUATIONS`, `RESERVED`, `bindingOf`, `effective`, `actionOf`, `bindingProblem`
  - `saveStore.ts`: `createSaveStore`, `SaveStore`, `SaveState`, `Edit`
  - `useEditor` (`useEditor.ts`)
  - `CodeEditor.tsx`: `CodeEditor`, `setMarks`, `insertAtCursor`
  - `LineCard.tsx`: `LineCard`, `Painted`, `NONE`, `Misspelling`
  - `CardList`, `StatusBar`, `FindBar`, `SpellMenu`, `ImageCard`, `SourcePage`
  - `useEditorKeys.ts`: `useBindings`, `useEditorKeys`
  - `useSpell` (`useSpell.ts`), `spellBatches` (`spell.ts`)
  - `ShortcutsPage`
