# Editor critique fixes, round 4 (scores 29–30/40 → 35+/40)

Scope: `web/src/editor/*`, `web/src/styles/editor.css`, `web/e2e` specs naming text you change.
Rules: tokens only; real characters in JSX (no `\u` escapes); keep every keybinding and behaviour; DOM order of aid cards
defines Alt+N slots; do not touch `useLeave` / save logic; tests for any pure module you change. Gate: `cd web && npx tsc
--noEmit` and `npm test`. Do not commit. Final message: files changed, one line per section, pasted gate tails.

## 1. Labels stay (heuristic 6, P1)
- `editor.css`: `.reading-label`, `.sb-label` currently hide under 75rem. Show them down to 40rem. Under 40rem keep icons but
  make `ReadingSwitch` render ONE labelled button ("Readings: あ ▾", showing the current mode) that opens a `Menu` of the
  four modes (`menuitemradio`), so nothing is ever an unlabelled glyph row.
- `ReadingSwitch.tsx`: option text becomes "Off", "あ", "ア", "Abc" (Latin form no longer a bare "a").

## 2. Lighter aid column (heuristic 8, P1)
- The `Aids` collapse toggle shows at every width (rename its text to "Suggestions" and make the visually-hidden h2 the
  button's heading text so the two names agree). Collapsed on desktop = a 2.5rem peek bar showing only "Suggestions ▸" and
  a count of ready cards ("2 ready"); remember the choice in `localStorage` (`ta.aidsOpen`, wrapped in try/catch, page
  must work without it).
- Empty and error cards render as a single 2rem row (header + note + Retry inline), `ready` and `busy` cards keep the full
  card. Use the existing `state-*` classes.

## 3. Protect Re-translate; scope the Settings advice (heuristic 5, 9, P2)
- `OllamaCard.tsx`: "Re-translate lines a–b" becomes a two-step: first click changes the button to "Replace saved drafts?
  Confirm / Cancel" (inline, `CardAction`s, auto-cancels after 6 s, Esc cancels); only Confirm asks.
- `cardCopy.ts` `friendlyError(message, backend, settingsHint = true)`: when `settingsHint` is false the messages drop the
  "Check ... Settings → Machine translation" tail ("Credentials rejected." / "Couldn't reach the service. Retry."). `TmPanel`
  passes `false`. Update `cardCopy.test.ts`.

## 4. One state language (heuristic 4, P2)
- Route the Ollama card's state (Running / Waiting / Queued, setup, error) and the Dictionary card's statuses through
  `CardStatus` and the `.card-meta` header slot, like MT/TM. Say each state once (header chip OR body line, not both).

## 5. Reasons visible, not only in `title` (heuristic 10, P3)
- Remove the `Aa` spell badge. In the ⋯ chapter menu add disabled `menuitem`s at the top when relevant:
  "Readings unavailable: needs MeCab · Set up" (link to `/settings/mt` as before) and "Spellcheck unavailable: no dictionary
  on the server". They are plain visible text in the open menu, with `aria-disabled`.
- The disabled reading control also shows its reason as visible text in its menu (section 1's menu on narrow widths) and in
  the group's `title` on wide widths.

## 6. Split Editor.tsx (maintainability)
- Editor.tsx is 526 lines. Move the chapter menu (`chapterMenu`) and the tools cluster into `web/src/editor/EditorTools.tsx`
  as components taking the values they need as props (pure move, no behaviour change). Target Editor.tsx < 400 lines.
