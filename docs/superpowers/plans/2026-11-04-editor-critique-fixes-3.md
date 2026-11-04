# Editor critique fixes, round 3 (score 30/40 → 35+/40)

Scope: `web/src/editor/*`, `web/src/styles/editor.css`, and any `web/e2e` spec that names text you change.
Rules: tokens only; real characters in JSX (never `\u` escapes); keep every keybinding and behaviour; do not touch
`useLeave` / save logic; add or update vitest for any pure module you change. Gate: `cd web && npx tsc --noEmit` and
`npm test` pass. Do not commit. Final message: files changed, one line per section, pasted gate tails.

## 1. A still aid column (P1)
- Remove the CSS `order` ranking on `.side-col > *` entirely: cards keep DOM order (TM, then backends in slot order), so
  visual order = tab order = Alt+N order. Keep the `state-*` classes: `ready` keeps the accent left edge and a small
  "Ready" word-mark in the header (not colour alone); `empty` still folds to one line; `busy` and `error` keep their cues.
- Make "No match" / "No suggestion" the single wording "No match" everywhere.
- Put the key chip (`.use-key`) in the same place on every card: the header's right side, for TM rows (first two matches),
  MT, Ollama. Widen `.side-col` from 18rem to 20rem.

## 2. One component for Use (P3)
- `TmPanel.tsx`: each match row becomes text + a real `CardAction tone="use"` (with `slot`, `label`, `data-use`) instead of a
  whole-row button with a decorative `.tm-use` chip. Row text click also uses (keep behaviour) via the row's `onClick`
  but only the CardAction is a button in the tab order. Remove `.tm-use`.

## 3. Calmer status bar centre; notices never clobber Undo (P2)
- `StatusBar.tsx`: remove the standing "Readings need MeCab. Set up" and "Spellcheck unavailable" lines from `sb-centre`.
  Put the readings reason in the reading group's `title` and a visually-hidden description (`aria-describedby`), and the
  spellcheck reason in a `title` on a small muted "Aa" indicator only shown when spellcheck is unavailable (still no
  permanent text).
- Notices: `Editor.tsx` keeps two slots: `notice` (transient, including the Undo node) and `waiting`
  ("Leaving once saved. Esc to stay."). Render both when both exist (waiting after the Undo span), never replace one with
  the other.
- Ollama card: one sentence per state. Header chip says the state ("Running", "Waiting", "Queued") and the body shows ONE
  explanatory line; delete the duplicate lines. Merge "Waiting for the night run's current chunk…" and its explanation
  into: "The night run is translating this passage; yours starts when it finishes."

## 4. Visible help and labelled aids (P2)
- Add a visible `Keys` button (icon `?` plus text "Keys" at ≥ 75rem, same pattern as `.reading-label`) in the tools
  cluster that opens KeyHelp; title includes its binding. Keep the ⋯ menu item.
- Label the Memory and Translate toggles with short text at ≥ 75rem ("Memory", "MT") using the same pattern; keep icons and
  aria-labels. The pressed state stays fill + check dot.
- `LineCard.tsx`: the inactive-card placeholder "Type your translation…" renders italic, muted, with no input-like
  box so it reads as a hint (class `.translation-empty`).

## 5. Accurate errors, plain wording (P2)
- `cardCopy.ts` `friendlyError`: replace the loose regex. Network only for: `failed to fetch`, `network ?error`,
  `econn(refused|reset)`, `enotfound`, `timed? out`, `timeout`, `unreachable`, `connection (refused|reset|closed)`,
  each as whole words; credentials for 401/403/unauthorized/forbidden/invalid api key/authentication. Everything else
  returns the message unchanged ("too long", "abort", "dns" alone must NOT match). Update `cardCopy.test.ts` with these cases.
- Wording: "Reroll lines a–b" → "Re-translate lines a–b" (title: "Replaces the suggestions for these lines"); "Translate
  chunk" → "Translate this passage". Update any Playwright spec text that names them.

## 6. Accessibility small fixes
- Saved check in `StatusBar.tsx`: one accessible name only. Use `role="img" aria-label="Saved"` on the icon and delete the
  duplicate visually-hidden span.
- Add an `h2.visually-hidden` "Suggestions" at the top of `.side-col` so the card `h3`s have a parent heading; the "Aids"
  toggle stays a button.
- The hidden `role="status"` "Line n of N" announcement: wrap its text change in a 400 ms trailing debounce (a small
  `useDebounced` helper in `useNotice.ts` or its own file with a test) so held-key stepping does not announce every line.
