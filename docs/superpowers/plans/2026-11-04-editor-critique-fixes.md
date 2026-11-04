# Editor critique fixes (target: Impeccable score 29/40 → 35+/40)

Source: `.impeccable/critique/2026-11-04T04-33-53Z__web-src-editor.md` (critique of `web/src/editor`).
Scope: `web/src/editor/*`, `web/src/styles/editor.css` (and `controls.css` only if a shared button style is needed).
Rules: tokens only (no literal colours); keep every keybinding and behaviour; no Python module changes; keep
`useLeave` / save flow untouched; update or add vitest only for pure modules you change. Gate: `cd web && npx tsc --noEmit`
(or `npm run build`) and `npm test` pass.

## Task 1 — Distill the sticky top (heuristic 8, 1)
- `StatusBar.tsx`: remove the `sb-crumbs` row as a separate row. Put the three crumbs (Library / series / volume) inside the
  chapter-nav menu (`ChapterBar.tsx`) as a header or as the first menu items, still going through `onLeave`. Keep a
  `nav aria-label="Breadcrumb"` for them.
- Remove the `at L{line}` span from the pill (the card number and the hidden `role=status` already carry it).
- Move the word count out of the pill (it stays on `ChapterEnd`).
- Save state: when `saved`, render only a small check (with `aria-label="Saved"`, `title`), no text, and drop
  `.save-state { min-width: 9em }` for that state. Saving / Unsaved / Not saved keep their text.
- Goal: at rest the sticky top is one row (chapter nav · progress pill · tools). Update `editor.css`; the `.sb-alert` row
  and find bar are unchanged.

## Task 2 — Strengthen the active card (heuristic 8, 6)
- `editor.css`: add a hairline (`border-top: 1px solid var(--line)`) or a `.3em` gap between `.source` and the translation
  area. Active card: translation area gets `border-left: 3px solid var(--accent-text)` and a `var(--field)` background
  with `border-radius`; inactive cards unchanged.
- Give the empty CodeMirror editor a visible placeholder ("Type your translation…") via the `placeholder` extension in
  `CodeEditor.tsx`, styled `color: var(--muted)`.
- Raise the active card's lift enough to read in light mode (stronger border mix, keep the shadow).

## Task 3 — One style for the aid column (heuristic 4)
- `TmPanel.tsx` / `editor.css`: wrap TM in the `.mt-card` shell (same border, radius, padding) with the same `h3` header
  style (uppercase 12px label). Matches become list rows with the `.use-key` keycap.
- One `Use` button look across TM, MT and Ollama: a small button with `.use-key` styled as a keycap (mono, `var(--line)`
  border, radius `3px`).
- `OllamaCard.tsx`: Retry, Reasoning and Reroll become small secondary buttons (class `small`) inside `.mt-actions`;
  Retry moves into `.mt-actions`.

## Task 4 — Toggle legibility (heuristic 6, 10)
- `editor.css`: `.sb-tools button.icon[aria-pressed="true"]` gets a clear state: filled `var(--accent-soft)` plus a 2px
  inset bottom bar in `var(--accent-text)`; `aria-pressed="false"` buttons stay quiet.
- `ReadingSwitch.tsx` group gets a visible short label "Readings" at ≥ 75rem (hidden below), keeping its `aria-label`.
- Add a visible key hint to the ⋯ trigger tooltip and a `?` item as the last menu entry showing the Ctrl+/ binding
  (`keyed(...)`), already present; make its text "Keyboard shortcuts (?)" unchanged in behaviour.
- `.copy-original`: replace `visibility: hidden` with `opacity: 0` + `pointer-events: none` until hover / focus-within /
  active, so Tab can focus it and `:focus-visible` shows it.

## Task 5 — Narrow layout (heuristic 4, 6)
- `editor.css` `@media (max-width: 60rem)`: `.side-col` becomes `position: sticky; bottom: 0; top: auto; max-height: 40vh;
  overflow-y: auto; order` after the cards but stuck to the viewport bottom, with `var(--surface)` background and a top
  border, so suggestions stay reachable without scrolling to the end. `.jump-back` bottom offset accounts for it
  (`bottom: calc(var(--aid-h, 0px) + 16px)`; set `--aid-h` only if trivially available, otherwise leave `bottom: 16px`).

## Task 6 — Final pass
- Check `.jp-punct { opacity: .6 }` and `.mt-flag` meet 4.5:1 in dark theme (compute against `--surface`); adjust to tokens
  if not.
- Run the gate commands; list any file touched in the final message; do not commit.
