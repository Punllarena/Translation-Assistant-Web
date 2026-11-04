# Editor critique fixes, round 2 (score 30/40 → 35+/40)

Source: `.impeccable/critique/2026-11-04T04-48-23Z__web-src-editor.md` and the round-2 findings below.
Scope: `web/src/editor/*`, `web/src/styles/editor.css` (shared button/keycap styles in `controls.css` only if needed).
Rules: tokens only; keep every keybinding and behaviour; do not touch `useLeave` / save flow; add a vitest only for a pure
module you create. Gate: `cd web && npx tsc --noEmit` and `npm test` pass. Do not commit.

## 1. Rank the aid column by usefulness (heuristics 8, 4)
- In `Editor.tsx` / `MtPanels.tsx` / `TmPanel.tsx`: give each aid card a state class: `ready` (has a Use button), `busy`
  (streaming / waiting), `empty` (no match / no suggestion / nothing to show), `error`.
- Order is visual, not DOM-breaking: use CSS `order` on `.side-col > *` so `ready` < `busy` < `error` < `empty`; keep DOM
  order (and therefore `assignSlots` / Alt+N keys) unchanged.
- `empty` cards collapse to a one-line header (title + muted "No match"); `ready` cards that own a key slot show the keycap
  (`.use-key`) in the header and get a stronger left edge (`border-left: 3px solid var(--accent-text)`).
- One shared `Use` look: a primary-tinted small button with the keycap, same in TM, MT and Ollama (TM rows keep the
  whole-row click but render the same `Use` affordance at the right).

## 2. Distill the status bar tools (heuristics 8, 6)
- Group the four aid toggles (Glossary ruby, Translation memory, Machine translation, Images) into ONE cluster: a segmented
  group `role="group" aria-label="Aids"` with each toggle's pressed state shown by fill + a small check dot, not a faint wash.
- Move Glossary ruby and Images out of the always-visible row into the ⋯ chapter menu as toggle items
  (`role="menuitemcheckbox"`, `aria-checked`, with their keys via `keyed`). Keep TM and MT toggles and the reading switch
  visible. Visible controls at rest: prev/next + chapter menu, progress pill, reading switch (4), TM, MT, ⋯ (≤ 9 → ≤ 8,
  with glossary ruby / images inside ⋯).
- Make the save pill width stable: reserve the width of the check in the saved state so the pill never resizes
  (`.save-state` fixed `min-width: 1.5em` for saved; keep text states auto).
- Align `.statusbar` horizontal padding with `.editor` (`max-width: 60rem` content edge) on wide screens, via the same
  max-width + `margin: 0 auto` on an inner wrapper.

## 3. One status/action language for cards (heuristic 9, 4)
- New `web/src/editor/CardParts.tsx` exporting `CardStatus` (`kind: "busy" | "empty" | "error" | "info"`, children;
  `busy` renders a small CSS spinner (`prefers-reduced-motion` → static dots), replacing the bare `…` glyph; `error`
  renders `role="alert"` once per card) and `CardAction` (a `small` button with optional `.use-key`).
- Use them in `MtPanels.tsx`, `OllamaCard.tsx`, `TmPanel.tsx`: Retry is the same `CardAction` everywhere; errors show
  `cause + next step` copy via a small pure helper `friendlyError(message)` in `cardCopy.ts` (+ `cardCopy.test.ts`):
  network/timeout → "Couldn't reach {backend}. Retry, or check Settings → Machine translation."; 401/403 →
  "Credentials rejected. Check them in Settings → Machine translation."; otherwise the original message unchanged.
- `Set up` links keep their target.

## 4. Undo after Use (heuristic 3, 5)
- In `Editor.tsx` `useText`: when it replaces an existing translation, set the notice to a node: "Replaced line N." plus an
  `Undo` small button that calls the CodeMirror undo (`undo(view)` from `@codemirror/commands`) and refocuses the editor.
  `useNotice` must accept a ReactNode (keep the 8 s clear and the clear-on-line-change). The notice text style is
  `var(--ink)` (not muted) while it carries an action.

## 5. Inline help for states (heuristic 10)
- Disabled reading buttons: when `!readings.available`, show an inline muted line in the status bar centre
  ("Readings need MeCab.") with a `Set up` link to the docs/settings target already used for MeCab messaging (use
  `readings.message` text; do not invent URLs). Spellcheck unavailable gets the same pattern ("Spellcheck unavailable. Words
  you add still work." only if true; otherwise keep the current text).
- Ollama states: add one-line explanations under the waiting states ("The night run is translating this chunk. Yours
  starts when it finishes.", "Another Ollama request is running. Yours follows.") and under `source changed`
  ("The Japanese line changed after this draft.").
- Glossary ruby toggle in ⋯ gets a description line in its title: "Shows glossary matches above the source".

## 6. Small fixes
- Narrow layout (< 60rem): `.side-col` collapsible: make its header row a button that toggles `max-height` between
  `40vh` and a 2.5rem peek bar; default collapsed while a card is focused for typing is NOT required — keep it expanded.
- `Editor.tsx` pending branch `if (images.isPending) return <main />;`: render a quiet skeleton row (`.editor-skel`) instead.
- Final: run the gate, list files changed and a one-line summary per section.
