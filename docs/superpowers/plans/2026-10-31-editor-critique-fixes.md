# Editor Critique Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Use safe, make the save status always true, make leaving predictable, and close the keyboard and screen-reader gaps found by the second editor critique.

**Architecture:** SPA only, under `web/src/editor/`; no API or schema change. Pure rules go in small tested modules (`useSlots.ts`, `saveErrors.ts`, `rows.ts`); behaviour that needs a browser is pinned in `web/e2e/editor-nav.spec.ts` with mocked routes.

**Tech Stack:** React, CodeMirror 6, react-router `useBlocker`, TanStack Query, vitest, Playwright.

**Spec:** This plan. The critique snapshot (`.impeccable/critique/2026-10-31T15-14-18Z__web-src-editor.md`) is gitignored, so its findings are restated under each task. Score at the start: 24/40, one P0, two P1s, two P2s.

## Decisions already made by the owner

- Order: safe Use first. Scope: all five priority issues. The critique's minor notes are out of scope.
- Alt+N on a line with text stays one press, and shows that the text was replaced.
- Line history is session only: in the tab until reload, with no schema change.

## Global Constraints

- Colours through `web/src/styles/tokens.css` only; no literal colours (DESIGN.md, The Token Only Rule).
- Vermilion (`--seal`) only for small marks; unsaved dots are allowed. A status colour always comes with words.
- No transitions on editor cards or controls.
- Serif for the novel's text, sans for tools, mono for keys.
- Every new action goes in `ACTIONS` (`keymap.ts`) at the end of the list, so it is rebindable and an existing override wins a clash. Default bindings stay unique (`keymap.test.ts`).
- `Editor.tsx` is over 370 lines: move logic into hooks or modules rather than growing it.
- E2E flows mock saves (`fakeSaves` in `editor-nav.spec.ts`) so the shared `ta_e2e` seed stays unchanged.

Commands, from the repo root:

```bash
docker compose --profile tools run --rm tools sh -c "cd web && npx tsc -b --noEmit"
docker compose --profile tools run --rm tools sh -c "cd web && npx vitest run src/editor/<file>.test.ts"
docker compose --profile tools run --rm tools sh -c "cd web && npm run e2e -- editor-nav"
```

Work on a branch, `fix/editor-critique-2`, from `main`.

## Review Focus

These are the failures most likely to bite that no finding names directly. Each has a test in the task shown.

1. Undo must never cross chapters: the same line number in another chapter has its own history (Task 1).
2. Typing while a leave is waiting: the move happens only once the newer text is saved (Task 3).
3. Cancel, then the server recovers: the page stays put and doesn't move later (Task 3).
4. A 401 during a waiting leave: it goes to sign-in with no dialog, and the stash survives (Task 3).
5. Esc during IME composition must not close Find or move focus (Task 5).

---

### Task 1: Safe Use (P0)

**Findings:** Enter then Alt+1 before the TM response lands inserts the previous line's match (`keepPreviousData`, `TmPanel.tsx`). Alt+1 mid-stream inserts a fragment (`MtPanels.tsx` shows Use on any text). Numbers shift as results arrive. `key={n}` on `CodeEditor` gives each line fresh history, so after moving away Ctrl+Z can't restore replaced text.

**Files:**
- Create: `web/src/editor/useSlots.ts`, `web/src/editor/useSlots.test.ts`
- Modify: `web/src/editor/TmPanel.tsx`, `MtPanels.tsx`, `OllamaCard.tsx`, `CodeEditor.tsx`, `Editor.tsx`, `web/src/styles/editor.css`
- Test: `web/e2e/editor-nav.spec.ts`

**Interfaces:**
- Produces: `assignSlots(enabled: string[]): { tm: [1, 2]; backends: Record<string, number> }`; `data-use="<slot>"` on Use buttons; `CodeEditor` prop `historyKey: string`.

- [ ] **Step 1: Write the failing unit test** in `useSlots.test.ts`

```ts
expect(assignSlots(["deepl", "mecab", "jparser", "ollama"])).toEqual({ tm: [1, 2], backends: { deepl: 3, ollama: 4 } });
expect(assignSlots(["mecab"]).backends).toEqual({});
```

- [ ] **Step 2: Run it and confirm it fails** with `assignSlots` not defined.

- [ ] **Step 3: Implement `assignSlots`.** MeCab and JParser have no Use button, so they take no slot. TM always holds 1 and 2; TM matches past the second stay clickable with no number.

- [ ] **Step 4: Run it and confirm it passes.**

- [ ] **Step 5: Write the failing e2e tests** in `editor-nav.spec.ts`
  - `Use can't take a stale or partial suggestion`: delay `**/tm/matches*` by 1 s for line 2; press Enter then `Alt+1`; expect the box to stay as it was. Stub a stream that sends a chunk and stays open; expect no Use button on that card until `done`.
  - `suggestion numbers don't move`: a backend's Use has the same `data-use` before and after a TM match arrives.
  - `undo survives moving between lines, per chapter`: on Nav one line 1, `Alt+1`, Enter, PageUp, `Control+z`; expect the original text and a mocked PATCH carrying it. Then in Nav two line 1, `Control+z`; expect no change.
  - `replacing says so`: `Alt+1` on a line with text shows `Replaced line 1. Ctrl+Z brings it back`; on an empty line it shows nothing.

- [ ] **Step 6: Run them and confirm they fail.**

- [ ] **Step 7: Implement.**
  - `TmPanel`: while `tm.isPlaceholderData`, render matches `disabled` with no `data-use`. Take `slots` and `bindings` props.
  - `MtPanels.Card`: show Use only when `state.status === "done"`.
  - `OllamaCard`: leave `text` as is (a `line` event carries a whole line); add `data-use`.
  - Numbers: replace the CSS counter with `<span className="use-key" aria-hidden="true">{bindings[`use_${slot}`]}</span>` in mono muted, so the real key prints, Alt included.
  - `Editor.run`: `use_N` clicks `.side-col [data-use="N"]`, and keeps the "No suggestion N on this line" notice.
  - `CodeEditor`: a module-level `Map<string, { state: EditorState; latest: Ref }>` keyed by `historyKey` (`${documentId}:${lineNumber}`). Save `view.state` on unmount and reuse it on mount. The entry owns the `latest` ref, because the saved state's listeners close over it; refresh `latest.current` on mount. The existing `value` effect already reconciles a document changed elsewhere. Comment with `ponytail:` that the map is unbounded until reload.
  - `Editor.useText`: when the line has different non-empty text, `setNotice(\`Replaced line ${n + 1}. Ctrl+Z brings it back\`)`.

- [ ] **Step 8: Run `tsc`, the unit tests and `npm run e2e -- editor-nav tm mt ollama`** and confirm they pass; `tm.spec.ts` covers Ctrl+Z after Use.

- [ ] **Step 9: Commit** `fix(editor): make Use safe, with fixed slots and undo across lines`

### Task 2: True save status (P1)

**Findings:** `missing` lines show "Saved" and the text is dropped. 404 and 422 retry forever. A 422 leaks `lines.0.translated_text…` and wraps the bar until the chapter title is one glyph. The alert and Retry vanish on every attempt and re-announce. A keystroke hides the error. Notices never expire. Bad grammar: "Lines 8".

**Files:**
- Create: `web/src/editor/saveErrors.ts`, `saveErrors.test.ts`, `web/src/editor/clipboard.ts`
- Modify: `saveStore.ts`, `saveStore.test.ts`, `useEditor.ts`, `StatusBar.tsx`, `Editor.tsx`, `LineCard.tsx`, `CardList.tsx`, `web/src/styles/editor.css`
- Test: `web/e2e/editor-nav.spec.ts`

**Interfaces:**
- Produces: `saveFailure(e: unknown): { message: string; permanent: boolean }`; `copyText(text: string): Promise<boolean>`; `ed.savePermanent: boolean`; `ed.missing` still `number[]`; `useNotice(active: number): { notice: string | null; setNotice(text: string): void }`. Task 4 relies on Retry staying mounted while `save.error` is set.

- [ ] **Step 1: Write the failing unit tests**

```ts
// saveErrors.test.ts
expect(saveFailure(new ApiError(500, "x"))).toEqual({ message: "The server answered 500.", permanent: false });
expect(saveFailure(new ApiError(404, "Not found"))).toEqual({ message: "This chapter no longer exists on the server.", permanent: true });
expect(saveFailure(new ApiError(422, "lines.0.translated_text: …"))).toEqual({ message: "The server refused this text. It may be too long.", permanent: true });
expect(saveFailure(new ApiError(403, "x"))).toEqual({ message: "The server refused the save (403).", permanent: true });
for (const s of [401, 408, 429, 503]) expect(saveFailure(new ApiError(s, "x")).permanent).toBe(false);
expect(saveFailure(new TypeError("Failed to fetch"))).toEqual({ message: "The server can't be reached.", permanent: false });
expect(saveFailure(new DOMException("", "TimeoutError"))).toEqual({ message: "The server took too long to answer.", permanent: false });

// saveStore.test.ts: an error stays through a new attempt and a new edit, and only success clears it
store.edit(1, "a"); await flushed;                      // save rejects "offline"
store.edit(1, "ab");
expect(store.getState()).toEqual({ state: "unsaved", error: "offline" });
// next save succeeds:
expect(store.getState()).toEqual({ state: "saved", error: null });
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement.**
  - `saveFailure` as tested. `useEditor`'s save wrapper rethrows `new Error(message)` and records `permanent` in a ref read during render (it is set before the store's state changes).
  - `saveStore.set(state, error = state === "saved" ? null : snapshot.error)`; the success branch that leaves dirty lines passes `null`.
  - The retry effect in `useEditor` sets no timer or `online` listener when permanent. A new edit still tries again through the normal debounce.

- [ ] **Step 4: Run them and confirm they pass.**

- [ ] **Step 5: Write the failing e2e tests** using `fakeSaves`
  - `a permanent error stops retrying and offers the text`: PATCH 422; alert reads `Line 1 not saved: The server refused this text. It may be too long.` with no "Retrying…"; count PATCHes over 6 s stays at 1; Copy unsaved text writes `Line 1\n<text>` (grant clipboard permissions); `.ch-title` keeps its width.
  - `the alert stays through retries and typing`: PATCH 500; the alert and Retry stay visible across an attempt held open by a delayed response, and after one keystroke.
  - `missing lines are a failure`: PATCH 200 with `{"missing":[0]}`; pill reads `Not saved`, alert reads `Line 1 no longer exists; reload the chapter`, Copy still offers the text.
  - `notices expire`: `No suggestion 9` is gone after 8 s, and gone at once on moving a line.
  - `unsaved cards are marked`: during a failure the failed card has `.unsaved-dot` with `aria-label="Not saved"`.

- [ ] **Step 6: Run them and confirm they fail.**

- [ ] **Step 7: Implement the UI.**
  - `StatusBar`: move the failure out of `.sb-centre` into its own full-width `.sb-alert` row under `.sb-row`, shown while `save.error` is set. It holds `<span role="alert">`, Retry and Copy unsaved text, and doesn't unmount between attempts. Text: `${linesText(lines)} not saved: ${error}` plus ` Retrying…` unless permanent.
  - `Editor`: when `ed.missing.length`, pass the bar `{ state: "error", error: "<Line N no longer exists / Lines N, M no longer exist>; reload the chapter" }`. Keep those lines' text in `ed.texts` and include them in Copy. Remove `gone` from the notice chain.
  - `clipboard.ts`: move `legacyCopy` out of `LineCard.tsx`; `copyText` tries `navigator.clipboard`, then the fallback. `LineCard.copy` uses it.
  - `useNotice`: 8 s expiry, cleared when `active` changes. Replaces `notice` state in `Editor`.
  - `CardList` and `LineCard`: an `unsaved` boolean, true only while `save.error` is set, so normal typing doesn't flicker. Renders `<span className="unsaved-dot" title="Not saved" aria-label="Not saved" role="img" />` beside `.card-number`, in `--seal`.

- [ ] **Step 8: Run `tsc`, unit tests and `npm run e2e -- editor-nav`** and confirm they pass.

- [ ] **Step 9: Commit** `fix(editor): make save status true and stop retrying permanent errors`

### Task 3: One leave flow (P1)

**Findings:** The dialog body goes blank during retries, because `unsavedLines` is only computed in `error`. It stays open after the save succeeds. Cancel leaves focus on `BODY`, so the next Enter moves a line. Alt+PageDown, the breadcrumb and the end card only say "Not moved…", so a permanent error can only be escaped through the app header. A hung save queues a move with no notice and no timeout.

**Files:**
- Modify: `web/src/editor/useLeave.ts`, `useEditor.ts`, `Editor.tsx`, `StatusBar.tsx`
- Test: `web/e2e/editor-nav.spec.ts` (the existing `failed save stops the move` test changes)

**Interfaces:**
- Consumes: `ed.store`, `ed.save.state`, `linesText`.
- Produces: `useLeave(store, saveState, onStay: () => void)` returning `{ leave(to: string): void; waiting: boolean; asking: { lines: number[]; error: string } | null; goAnyway(): void; stay(): void }`. `useLeaveGuard` and the "Not moved" notice are removed.

- [ ] **Step 1: Write the failing e2e tests**
  - `every exit asks the same way`: PATCH 500; Next chapter, a breadcrumb link and the Statistics header link each open `Leave with unsaved lines?`, naming `Line 1` and `The server answered 500.`
  - `the dialog text holds through retries`: the body stays the same across two attempts.
  - `a recovered save carries on`: dialog open, PATCH turns 200; the page moves to the target by itself.
  - `Cancel stays`: Cancel focuses the editor; PATCH turns 200; the bar reads Saved and the URL doesn't change after 3 s.
  - `a slow save says it's waiting`: PATCH held open; Next chapter shows `Leaving once saved. Esc to stay.`; Esc clears it and the URL doesn't change when the save lands.
  - `typing while waiting`: PATCH held open, Next chapter, type a letter, release; the move happens only after a PATCH carrying the letter.
  - `a 401 while waiting goes to sign-in`: PATCH 401; the URL becomes `/login?next=…` with no dialog; `sessionStorage` holds the stash.
  - `a hung save times out`: stub `AbortSignal.timeout` to 200 ms with `page.addInitScript`; PATCH never answers; alert reads `The server took too long to answer.`

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement `useLeave` as one state machine.**
  - State `queued: { go(): void; cancel(): void } | null`. `leave(to)` queues `navigate(to)` and flushes. The blocker queues `blocker.proceed`, with `cancel` = `blocker.reset`.
  - An effect on `[queued, saveState]`: when `saved` and `!store.pending()`, run `go`. When `error`, set `asking` once, snapshotting `store.unsaved()` lines (1-based) and the error, so retries can't change the text.
  - A `bypass` ref read by the blocker lets `goAnyway` and `go` pass. The blocker's condition stays `store.pending()`, a different pathname, and not `/login`.
  - While waiting, a capture-phase Esc listener calls `stay()`. `stay` clears everything and calls `onStay`, which is `focusAfterDialog` in `Editor`.
  - A second `leave` replaces the queued one.

- [ ] **Step 4: Add the timeout.** In `saveLines`, non-keepalive only: `signal: AbortSignal.timeout(20_000)`. `saveFailure` already names it.

- [ ] **Step 5: Wire it in `Editor` and `StatusBar`.** `waiting` shows the notice `Leaving once saved. Esc to stay.` in `role="status"`. The dialog reads `asking`: title `Leave with unsaved lines?`, body `${linesText(lines)} could not be saved: ${error} The text is kept in this tab and sent again when you reopen this chapter here. Closing the tab loses it.`, confirm `Leave anyway`, danger. Delete `unsavedLines`'s use in the dialog. Update `failed save stops the move` to expect the dialog.

- [ ] **Step 6: Run `tsc` and `npm run e2e -- editor-nav`** and confirm they pass.

- [ ] **Step 7: Commit** `fix(editor): one leave flow that waits, asks and recovers`

### Task 4: Screen reader and keyboard path (P2)

**Findings:** The working layout has no `<main>` or `<h1>`. A line change announces nothing, and the textbox has no link to its source. Every button is named "Use". Retry is reachable only by Shift+Tab. The spell menu has no arrow keys and no key to open it.

**Files:**
- Modify: `web/src/editor/Editor.tsx`, `LineCard.tsx`, `CodeEditor.tsx`, `TmPanel.tsx`, `MtPanels.tsx`, `OllamaCard.tsx`, `SpellMenu.tsx`, `keymap.ts`, `web/src/ui/Menu.tsx`
- Test: `web/e2e/editor-nav.spec.ts`, plus e2e specs that find Use by name (`tm`, `mt`, `ollama`)

**Interfaces:**
- Consumes: Retry mounted while `save.error` is set (Task 2); `data-use` slots (Task 1).
- Produces: actions `retry_save` (Alt+S), `spell_open` (Ctrl+.); `moveMenuFocus(e: KeyboardEvent, root: HTMLElement): void` exported from `ui/Menu.tsx`.

- [ ] **Step 1: Write the failing e2e tests**
  - `landmarks and names`: one `main`, one `h1` with the chapter title (`.visually-hidden`); the textbox's accessible description contains the source text; moving a line sets `role=status` text to `Line 2 of 23`; a backend's button is named `Use DeepL, Alt+3`.
  - `Alt+S retries`: PATCH 500 then 200; `Alt+S` sends a PATCH at once.
  - `the spell menu works by keyboard`: on a line with a misspelling, `Control+.` opens the menu at it; ArrowDown moves focus; Enter picks; focus returns to the editor. On a clean line the notice reads `No misspelled words on this line`.

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement.**
  - `Editor`: `div.editor-layout` becomes `<main className="editor-layout">`. Add `<h1 className="visually-hidden">` with the chapter title and `<div role="status" className="visually-hidden">Line {n + 1} of {lines.length}</div>`.
  - `LineCard`: `id="active-source"` on the active card's source. `CodeEditor` adds `aria-describedby: "active-source"` to its content attributes.
  - Use buttons: `aria-label={\`Use ${label}, ${key}\`}`; a TM match: `` `Use "${text}", ${key}` ``, without the key when it has no slot. Update e2e locators that name these buttons.
  - `Menu`: extract arrow handling to `moveMenuFocus`, and call it from `SpellMenu`.
  - `spell_open`: the misspelling at or after the caret, else the first on the line, positioned with `view.coordsAtPos`. Reuses `setMenu`.
  - `retry_save`: `ed.store.flush()`.

- [ ] **Step 4: Run `tsc`, `keymap.test.ts` and `npm run e2e -- editor-nav editor tm mt ollama`** and confirm they pass.

- [ ] **Step 5: Commit** `fix(editor): landmarks, line announcements, named Use, keyboard spell menu`

### Task 5: Silent no-ops (P2)

**Findings:** Ctrl+End on an untranslated line does nothing, and Enter on the last line gives no cue. Ctrl+G is a native prompt where "abc" silently does nothing and "999" clamps. Esc from the editor doesn't close Find. Find highlights only the current hit, because `--hit` is unused. Typing after Esc on a menu is lost.

**Files:**
- Modify: `web/src/editor/Editor.tsx`, `useEditorKeys.ts`, `useFind.ts`, `CardList.tsx`, `LineCard.tsx`, `rows.ts`, `rows.test.ts`, `web/src/styles/editor.css`
- Test: `web/e2e/editor-nav.spec.ts`

**Interfaces:**
- Consumes: `useNotice` (Task 2).
- Produces: `parseLineNumber(answer: string, total: number): number | null` in `rows.ts`; `useEditorKeys(bindings, run, focusEditor, closeFind: () => boolean)`; `useFind` also returns `hits: Hit[]`, empty while closed.

- [ ] **Step 1: Write the failing unit test** in `rows.test.ts`

```ts
expect(parseLineNumber("3", 10)).toBe(3);
for (const bad of ["abc", "", "0", "11", "2.5", "-1"]) expect(parseLineNumber(bad, 10)).toBeNull();
```

- [ ] **Step 2: Write the failing e2e tests**
  - `keys that can't act say why`: on an untranslated line, `Control+End` shows `This line has no translation yet`. With none left, it shows `No untranslated lines left`. The jump itself is unchanged, for desktop parity.
  - `Enter on the last line goes to the end card`: focus lands on `.chapter-end .primary`; Enter there runs it.
  - `go to line is a dialog`: `Control+g` opens a dialog; `abc` shows `Enter a line number from 1 to 23` and stays open; `5` moves there and focuses the editor; Esc returns to the editor.
  - `Find`: all matches have `.find-hit`, the current one `.find-current`. `Escape` from the editor closes Find. An Esc dispatched with `isComposing: true` doesn't.
  - `typing after a menu`: open ⋯, Esc, type `x`; it lands in the box. Space on the trigger still opens the menu.

- [ ] **Step 3: Run them and confirm they fail.**

- [ ] **Step 4: Implement.**
  - `useEditorKeys`: `if (e.isComposing) return` before any Esc or typing handling. Esc runs `closeFind()` first, and falls through to `focusEditor` when it returns false, including from inside the editor.
  - Typing on a control now goes to the editor too, except Space: `typed && e.key !== " "`.
  - `run`: `save_next` with `nextContent(...) === null` flushes, then focuses and scrolls to `.chapter-end .primary`.
  - `go_to_line`: `PromptDialog` state in `Editor`, with `parseLineNumber` then `lineAtOrAfter`. Closes through `focusAfterDialog`.
  - `useFind.hits` flows through `CardList` to `LineCard` as per-card spans with class `find-hit`, using a shared empty constant so `memo` holds. The active translation adds them in the existing marks effect. `.find-hit { background: var(--hit); color: var(--ink); }` goes before `.find-current`.

- [ ] **Step 5: Run `tsc`, unit tests and `npm run e2e -- editor-nav editor`** and confirm they pass.

- [ ] **Step 6: Commit** `fix(editor): say why a key did nothing, and finish Find and go to line`

### Task 6: Polish and verify

**Files:**
- Modify: `CLAUDE.md` (the "Focus and keys" paragraph: slots, session history, `saveFailure`, one `useLeave` flow), `CHANGELOG.md`

- [ ] **Step 1: Walk the failure states by eye.** At 1440x900 and 390x844, light and dark: `.sb-alert` with a long message, the leave dialog, the waiting notice, the dots, `.find-hit` in both themes, the key labels on Use. Fix what the look shows.

- [ ] **Step 2: Run everything.**

```bash
docker compose --profile tools run --rm tools sh -c "cd web && npx tsc -b --noEmit && npx vitest run && npm run e2e"
```

Expected: no type errors, all unit and e2e tests pass.

- [ ] **Step 3: Read the diff** for churn, dead code and leftovers: the CSS counter, `gone`, `useLeaveGuard`.

- [ ] **Step 4: Update `CLAUDE.md` and `CHANGELOG.md`, then commit** `docs: record the editor's Use, save and leave rules`

- [ ] **Step 5: Re-run `/impeccable critique web/src/editor`** to score the result. Close the snapshot only if it shows these issues cleared.

## Known limits, deliberately left

- One over-long line fails its whole save batch. The alert names every line and Copy gets the text out; splitting batches isn't worth it until this happens in practice.
- Session history is lost on reload, and the map is unbounded until then.
- A line in `missing` has no leave guard: reloading is the fix, and Copy is the way to keep the text.
- Alt+1–9 may clash with browser tab switching on Linux; it's rebindable and needs a check in a real browser.
- Real IME and screen-reader use, Firefox and Safari stay untested by these suites.
