# Editor critique fixes — handover

**Branch:** `opencode/editor-critique-fixes`, created from `main` at `a66e2b9`
(`Added plans for the Impeccable Critique Fixes`). Not pushed, no PR.

**Commits** (`git log --oneline a66e2b9..HEAD`):

```
b5c0194 fix(editor): make Use safe, with fixed slots and undo across lines
69a1750 fix(editor): make save status true and stop retrying permanent errors
b6c1af9 fix(editor): one leave flow that waits, asks and recovers
909422c fix(editor): landmarks, line announcements, named Use, keyboard spell menu
2ead261 fix(editor): say why a key did nothing, and finish Find and go to line
8a659d9 docs: record the editor's Use, save and leave rules
```

plus this handover as its own `docs(handoff): editor critique fixes plan` commit. The plan
(`docs/superpowers/plans/2026-10-31-editor-critique-fixes.md`) has every checkbox ticked except Task 6
Step 5 (below), each tick committed with its task. SPA only: no Python file changed, so `ruff` was not run
and the API schema (and `npm run gen:api`) is untouched.

## Environment

- Postgres came from the main checkout's running container at `127.0.0.1:5432`; no second server was started.
  Every run set `$env:TA_DATABASE_URL="postgresql+psycopg://ta:ta@127.0.0.1:5432/ta_test"` and
  `$env:TA_E2E_DATABASE_URL="postgresql+psycopg://ta:ta@127.0.0.1:5432/ta_e2e"`.
- The worktree had no `web/node_modules`; `npm ci` in `web/` (102 packages, from the lockfile) was the only
  install. No `.venv` in the worktree: `C:\dev\ta-web\.venv\Scripts\python.exe` was put on `PATH` so that
  Playwright's `webServer` command (`python -m tools.e2e_seed` then `uvicorn`) ran the app from this worktree.
  Playwright's Chromium was already installed under `%LOCALAPPDATA%\ms-playwright`.
- One Playwright run and one vitest run at a time, as asked. `ta_e2e` is dropped and recreated by
  `tools.e2e_seed` at every Playwright start, so each run began from the seed.
- The plan's commands use `docker compose --profile tools run --rm tools`; the local equivalents were used
  instead (`npx tsc -b --noEmit`, `npx vitest run`, `npx playwright test`), same tools, same versions from
  `web/package.json`.

## Task 1 — safe Use (`b5c0194`): done

- `web/src/editor/useSlots.ts`: `assignSlots(enabled)`; memory always holds 1 and 2, MeCab and JParser take
  none, every other backend gets the next number in the enabled order. `useSlots.test.ts` covers it.
- `TmPanel` takes `slots`/`bindings`; while `tm.isPlaceholderData` the previous line's matches render
  `disabled` with no `data-use`. `MtPanels.Card` shows Use only at `status === "done"`. `OllamaCard` gained
  `data-use` (its `text` is a whole line).
- Numbers: the CSS counter is gone (`editor.css`), each button carries `<span class="use-key">` with the real
  binding. `Editor.run` clicks `.side-col [data-use="N"]`.
- `CodeEditor` keeps a module-level `Map<string, { state, latest }>` keyed `${documentId}:${lineNumber}`,
  writes `view.state` on unmount, reuses it on mount and refreshes the entry's `latest` each render; the
  existing `value` effect still reconciles an externally changed document. `SourcePage` passes
  `historyKey={`source:${mode}:${id}`}`.
- `Editor.useText` says `Replaced line N. Ctrl+Z brings it back` when the line already held different text.

## Task 2 — true save status (`69a1750`): done

- `saveErrors.ts`: `saveFailure(e)` → `{ message, permanent }` (404, 422 and other 4xx except 401/408/429 are
  permanent; a `TypeError` is "The server can't be reached."; a `TimeoutError` is "The server took too long to
  answer."). `useEditor` rethrows `new Error(message)` and records `permanent` in a ref read during render;
  the retry effect sets no timer or `online` listener for a permanent failure, while a new edit still tries
  through the normal debounce.
- `saveStore.set(state, error = state === "saved" ? null : snapshot.error)`, and the success branch that
  leaves dirty lines passes `null`, so an error survives a retry and a keystroke and only a server answer
  clears it.
- `StatusBar`: the failure moved out of `.sb-centre` into `.sb-alert` under `.sb-row`, rendered while
  `save.error` is set (not only while `state === "error"`), holding `role="alert"`, Retry and Copy unsaved
  text; `Retrying…` only when not permanent.
- `Editor`: `ed.missing` now drives the bar (`Line 1 no longer exists; reload the chapter`), the text stays in
  `ed.texts` and Copy offers it; `gone` is gone. `clipboard.ts` holds `copyText` (async clipboard, then the
  legacy textarea) and `unsavedText`; `LineCard` uses it.
- `useNotice.ts` (new, 8 s expiry, cleared when the line changes). `CardList`/`LineCard` take `unsaved` and
  render `<span class="unsaved-dot" title="Not saved" aria-label="Not saved" role="img">` beside the number,
  true only while `save.error` is set.

## Task 3 — one leave flow (`b6c1af9`): done

- `useLeave(store, saveState, onStay)` → `{ leave, waiting, asking, goAnyway, stay }`; `useLeaveGuard` and the
  "Not moved" notice are deleted. `leave(to)` queues `navigate(to)` and flushes; a router-blocked exit queues
  `blocker.proceed` (cancel `blocker.reset`). One effect decides: go at `saved` with nothing pending, ask once
  at `error` with the lines and error frozen then. `bypass` lets a confirmed go pass the blocker; the blocker's
  condition is still `pending()`, a different pathname and not `/login`. `Esc` while waiting (capture listener)
  calls `stay`, which resets/clears and calls `onStay` (`focusAfterDialog`). A second `leave` replaces the
  queued one.
- Timeout: `signal: AbortSignal.timeout(20_000)` in the non-keepalive `saveLines` (landed in Task 2, whose
  message test needed it; ticked under Task 3 step 4).
- Benefit of a detail not in the plan: the store now notifies listeners after the in-flight flag drops, and
  `useLeave` subscribes to the store with a version counter. Without it, `set("saved")` and `inFlight = null`
  happen in different microtasks, so the effect saw `pending() === true` once and never ran again — the "a
  recovered save carries on" test caught exactly that.

## Task 4 — screen reader and keyboard (`909422c`): done

- `main.editor-layout`, `h1.visually-hidden` with the chapter title, `<div role="status" class="visually-hidden">
  Line N of M</div>`; the active card's `.source` has `id="active-source"` and CodeMirror's content carries
  `aria-describedby`.
- Use buttons are named `Use DeepL, Alt+3` / `Use "…", Alt+1` (no key when the match has no slot); `tm.spec.ts`
  locators were updated to the new name.
- `moveMenuFocus(e, root)` exported from `ui/Menu.tsx`, used by `Menu` and `SpellMenu`; `retry_save` (Alt+S)
  and `spell_open` (Ctrl+.) appended to `ACTIONS`, `keymap.test.ts` still passes (unique defaults).

## Task 5 — silent no-ops (`2ead261`): done

- `rows.ts#parseLineNumber`; `useEditorKeys(bindings, run, focusEditor, closeFind)` returns early on
  `e.isComposing`, runs `closeFind()` first on Esc (inside the editor too), and focuses the editor for typing on
  a control except Space.
- `next_untranslated` says `This line has no translation yet` / `No untranslated lines left`; `save_next` on
  the last line focuses `.chapter-end .primary` (through a `wantEnd` state and an effect, because the chapter
  list may still be loading when the key is pressed — a plain `querySelector` there was flaky); `go_to_line` is
  a `PromptDialog` with `Enter a line number from 1 to N` and `lineAtOrAfter`.
- `useFind` returns `hits` (a shared `NO_HITS` while closed); `CardList`/`LineCard` mark every hit with
  `.find-hit` in both the source and the translation, and `.find-hit` sits before `.find-current` in
  `editor.css`.

## Task 6 — polish and verify (`8a659d9`): done except Step 5

- Looked at the real states through Playwright screenshots (not committed; `test-results/shots/`, gitignored)
  at 1440x900 and 390x844, light and dark: the `.sb-alert` row with Retry/Copy, the leave dialog (both widths),
  the `Leaving once saved. Esc to stay.` notice, the unsaved dot, `.find-hit`/`.find-current` and the `Alt+1`
  label on memory. Nothing looked wrong; no CSS was changed after that pass.
- Diff read for churn: the CSS counter, `gone`, `useLeaveGuard`, the `window.prompt` path and `legacyCopy`'s
  home in `LineCard` are all gone. `Editor.tsx` grew (466 lines); the one piece easy to lift out,
  `unsavedText`, moved to `clipboard.ts` with `clipboard.test.ts`, and the shadowed `at` in `spell_open` was
  renamed `spot`. Those two edits and the new test landed in the documentation commit rather than their task's.
- `CLAUDE.md` "Focus and keys" rewritten (fixed slots, session history, `saveFailure`, one `useLeave` flow,
  the new keys); `CHANGELOG.md` gained the entry, linking the plan.

## Commands and real output

| Command | Output |
| --- | --- |
| `npx vitest run src/editor/useSlots.test.ts` (before the module) | exit 1 — `Cannot find module './useSlots'` |
| `npx vitest run src/editor/useSlots.test.ts` (after) | **3 passed** |
| `npx playwright test editor-nav -g "Use can't take a stale…"` (before Task 1 code) | exit 1 — `expected not "Old match"`, received `"Old match"` |
| the other three Task 1 e2e tests (before the code) | exit 1 — `data-use` missing, `Ctrl+Z` left `"From memory"`, no `Replaced line` notice |
| `npx vitest run src/editor/saveErrors.test.ts src/editor/saveStore.test.ts` (before) | exit 1 — `saveErrors` not found; `expected {state:'unsaved',error:null} to equal {…, error:'offline'}` |
| the same two after the code | **18 passed** |
| `npx playwright test editor-nav` (after Task 1) | **16 passed (1.1m)** |
| `npx playwright test tm mt ollama` (after Task 1) | **8 passed** |
| the five Task 2 e2e tests (before the UI) | exit 1 — no `.sb-alert`, no `Copy unsaved text`, no dot, notice never expired, pill said `Saved` |
| the same five after the UI | **5 passed** |
| `npx playwright test editor-nav` (after Task 2) | **21 passed (1.6m)** |
| the nine Task 3 e2e tests (before `useLeave`) | exit 1 — no dialog on arrows/crumbs, old `Not moved` text, no waiting notice |
| the same nine after | **9 passed (52.3s)** |
| `npx playwright test editor-nav editor` (after Task 3) | **35 passed (2.5m)** |
| the three Task 4 e2e tests | **3 passed** (all three needed code that did not exist: `h1`, Alt+S, Ctrl+.) |
| `npx playwright test editor-nav editor tm mt ollama` (after Task 4) | **46 passed (3.0m)** |
| `npx vitest run src/editor/rows.test.ts` (before `parseLineNumber`) | exit 1 — `parseLineNumber is not a function` |
| the five Task 5 e2e tests | **5 passed (25.6s)** |
| `npx playwright test editor-nav editor` (after Task 5) | **43 passed (2.8m)** |
| `npx tsc -b --noEmit` (final) | no output (clean) |
| `npm run build` (final) | `✓ built in 1.55s`; one pre-existing `chunks are larger than 500 kB` warning |
| `npx vitest run` (final, whole SPA) | **60 files, 421 passed** |
| `npx playwright test` (final, whole suite) | **127 passed (5.7m)** |

The final full Playwright run was made after the last code commit (`2ead261` plus the `unsavedText` tidy in
`8a659d9`), on a freshly reset `ta_e2e`. `ruff` was not run because no Python file changed.

## Decisions and deviations worth reviewing

1. **`pending()` after `saved`.** See Task 3: the leave effect would never fire on a recovered save without the
   extra notification in `saveStore.flush`'s `finally` and the store subscription in `useLeave`. The plan's
   "when `saved` and `!store.pending()`" is implemented literally; this is what makes it work.
2. **Endless `wantEnd` guard.** Focusing `.chapter-end .primary` synchronously on Enter lost focus when the
   documents query had not landed yet (the link did not exist). It is now a state flag consumed by an effect
   that gives up once `docs.data` is loaded and there is still nothing to focus.
3. **Test data, not seed changes.** Two e2e tests had to stop assuming line 1 of `Nav one` is empty, because
   earlier tests in the same file type and save there: `replacing says so` uses card 3, and the undo test reads
   the line's current text first. No `tools/e2e_seed.py` change, as the plan requires.
4. **Streams in mocks end without `done`.** A Playwright `fulfill` cannot hold an SSE body open, so the
   "partial suggestion" test gets a `chunk` and a closed connection (the card shows the text as an error, with
   no Use) and checks the `done` case on the next line. The property under test — no Use until `done` — holds.
5. **Clipboard comparison is CRLF-normalised** in the e2e clipboard assertions: Windows returns `\r\n` for what
   was written as `\n`.
6. **`useNotice` is its own module** (`useNotice.ts`) rather than another `Editor` state, and `unsavedText`
   lives in `clipboard.ts` — both to keep `Editor.tsx` from growing further.
7. **`useEditorKeys`' Esc** also runs when focus is inside `.cm-editor`; CodeMirror does not use plain Esc, and
   the "closes Find from the editor" review focus depends on it.

## What I could not verify

- **Task 6 Step 5 — `/impeccable critique web/src/editor` was not run.** No `.impeccable/` directory or
  critique snapshot exists in this worktree (it is gitignored), and this harness has no `/impeccable` command
  to re-score the editor. Its checkbox is left unticked; the branch is ready for Claude's review and for that
  critique to be run where the tool lives.
- **Real IME and real screen readers.** `isComposing` is exercised by a synthetic `KeyboardEvent` only; NVDA,
  VoiceOver and Firefox/Safari were not run. The `role="status"`/`aria-describedby` markup is asserted through
  Playwright's ARIA, not through assistive technology.
- The "hung save" test stubs `AbortSignal.timeout` to 200 ms in the page; the real 20 s path never ran.
- Nothing was pushed and no CI ran on this branch.
