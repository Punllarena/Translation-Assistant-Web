# Editor: add-phrase menu item, copy original, glossary ruby

Date: 2026-10-31. Replaces the TODO entry "Editor: copy source" (the undo-across-cards item was dropped by the user).

Three pieces, built in this order so a problem in the last does not block the first two. They share the editor files.

## Why

1. Adding a glossary item from the editor already works (Ctrl+L, "Add a glossary phrase", `PhraseDialog`), but the user
   did not know it existed. It needs a visible entry point.
2. The user pastes lines into other translation tools and has no way to copy the original text of a card.
3. The card's source text is the glossary-**replaced** text, so the original Japanese is hidden wherever a glossary phrase
   matches. The user wants the original text kept, with the glossary translation shown as ruby text on top of it, the way
   author ruby and reading ruby already are, and a button to turn that on and off. Ollama and JParser keep receiving the
   replaced text.

## Goals and non-goals

Goals: the three pieces above. Non-goals: no change to what glossary replacement does for machine translation, Ollama,
JParser, export or publishing; no undo work; no glossary editing in the card; no ruby on translation text.

## Piece 1: "Add glossary phrase…" in the Chapter actions menu

- Add an item to `chapterMenu` in `web/src/editor/Editor.tsx`, next to "Series glossary", that runs the existing
  `add_phrase` action (`run("add_phrase")`). It opens `PhraseDialog` prefilled from the current text selection.
- The item shows the user's current key binding for `add_phrase` (default Ctrl+L, from `useBindings()` / `keymap.ts`;
  find how the Shortcuts page formats a binding and reuse it). It must not hard-code "Ctrl+L".
- Check that the selection survives opening the menu: the shortcut reads `window.getSelection()`, and a menu click may
  move focus. If the selection is lost, capture it when the menu button is pressed. Prove it in the e2e spec (select the
  phrase in the source text, open the menu, choose the item, the dialog's phrase field holds the selection).
- Works on a chapter with no lines too only if `chapterMenu(false)` is used there; keep the item to `withLines` menus
  (it needs a source text), builder's call, say which.

## Piece 2: copy original text

- A small icon button next to the line number (`card-number`) in `LineCard.tsx` that copies the line's **original** text:
  `line.raw_text` as stored, with no glossary replacement and no `$`/`%` prefix. (Confirmed by the user: "the original text".)
- Visible on the active card and on hover or keyboard focus of any card (designer's call). It has an accessible name
  ("Copy original text"). Clicking it does not activate the card (stop the click from reaching the card's `onClick`).
- Feedback: the icon or label changes to a checkmark/"Copied" for about 1.5 s. If `navigator.clipboard` is unavailable or
  rejects, show a short failed state; no fallback hack. Use the existing icon set and tokens; no literal colours.
- The button is not part of the card text, so find, spell check and selection are unaffected.

## Piece 3: glossary ruby, with a toggle

### Behaviour

- A new status-bar toggle button immediately before the "Translation memory" button, `aria-pressed`, label "Glossary
  ruby", saved as the account setting `glossary_ruby` (boolean) exactly like `tm_visible` (`saveSetting` in
  `Editor.tsx`; settings keys are free-form for such flags, but the builder must confirm that `PUT /settings` accepts the new key and
  validate in `api/settings_rules.py` only if that file enforces a whitelist). **Default off** (designer's call: today's
  behaviour is unchanged until the user turns it on).
- When on, on **every card** (designer's guess, since the data is cheap and a hint on cards you are about to translate is
  the point): the source shows the original text (`raw_text`), and each glossary match carries its translation as ruby text
  above it, using the same `<ruby>` placement as author and reading ruby (`Painted` / `layout` in `LineCard.tsx` and
  `paint.ts`). The glossary ruby has its own `rt` class so it can look different from reading ruby (for example the accent
  colour from the tokens, upright rather than small italic; builder's call, tokens only).
- When off: exactly today's behaviour (replaced text shown, no change).
- The Ctrl+Left "revert to original" state (`parse === -2`) keeps working; in ruby mode the source already is the original.
- Interactions (decided with the user or the designer):
  - **Reading ruby (hiragana/katakana/romaji, active card):** where a glossary mark sits, the **glossary wins**; the
    reading is skipped over that range and still shows on the rest of the line. (Confirmed by the user.)
  - **Author ruby (`漢字(かんじ)` in the source):** author ruby keeps priority; a glossary mark that overlaps an author
    ruby range or its hidden bracket range is dropped (designer's call).
  - **Sentence highlight (`sentence-current` while stepping phrases) and the line counter text:** the sentences stay the
    replaced-text ones, used for machine translation. In ruby mode the highlight range is mapped from replaced-text
    coordinates to original-text coordinates through the marks (a position inside a replacement maps to that mark's edges).
    In the rare case where a later glossary phrase matched inside an earlier replacement's output, the mapping is
    best-effort; it must not throw.
  - **Find (`useFind.ts`, `Editor.tsx` `shown`):** in ruby mode the source field searched, highlighted and used to fetch
    readings is the original text, so offsets agree with what is shown. When off, unchanged.

### Server: the marks

The client must not re-implement the glossary rules (they are sequential and order-dependent), so the API sends the
marks. In `api/core/text.py` add a pure function (name at the builder's choice, e.g. `glossary_marks`) beside
`replace_and_parse` that, for the same inputs (the line text with `$`/`%` stripped, the glossary list), returns the list of
matches in the **original** text:

- Process the glossary entries in the same order as `replace_and_parse` and replace all occurrences exactly as it does, but
  track where every piece of text came from. An occurrence found entirely in original, still-untouched text becomes a
  mark. An occurrence that overlaps text a previous entry already replaced, or that lies inside a previous entry's output,
  produces no mark (there is nothing original to put it on). `replace_and_parse`'s own output must not change by a
  single character; add a test that asserts the replaced text equals what the new function reconstructs, for several
  glossaries (longer phrase listed after a shorter one that contains it, two phrases with the same translation, an empty
  translation).
- Each mark: `from`, `to` (offsets into the original text) and `translation`, plus the mark's `shown_from`/`shown_to` in
  the replaced text, so the client can map highlight ranges. **Offsets are UTF-16 code units** (JavaScript string indexes,
  as `ruby.ts` expects), not Python code points; a test with a character outside the BMP (for example `𠮷`) before a match
  proves the conversion.
- An empty translation (a glossary entry that deletes a phrase) produces no ruby text and no mark.
- Marks are sorted by `from` and never overlap.
- `LineOut` (`api/schemas/lines.py`) gets `glossary_marks: list[GlossaryMark]`, filled in `get_lines`
  (`api/routers/lines.py`). The text the offsets refer to is the line's text with `$`/`%` removed (what
  `replace_and_parse` starts from); the builder must check whether `raw_text` can still contain `$` or `%` (the importer
  puts the prefix in `prefix`, but replace strips them anywhere). If it can, add a `plain_text` field and have the client
  use it as the ruby-mode source; if it cannot, `raw_text` is the plain text and no new field is needed. Say which.
- The OpenAPI schema is regenerated (`npm run gen:api`).

### Client

- A pure module (extend `ruby.ts` or add `glossaryRuby.ts`) turns marks into `Ruby[]` (adds an optional `cls` to `Ruby`,
  carried through `layout` to the `rt` class list like `rt-latin` is), drops marks overlapping author ruby, and merges
  with generated readings with the glossary-wins rule; plus the replaced→original offset mapper. All pure and
  vitest-tested.
- `LineCard.tsx`: the `source` / `ruby` / `sourceSpans` computation switches on the toggle; `Editor.tsx` passes the flag
  and the source text used by `useFind` and the readings request.

## Tests

- pytest: marks (order, overlap, chained replacement, empty translation, UTF-16, `replace_and_parse` unchanged), `GET
  /documents/{id}/lines` returns marks, tenancy unchanged.
- vitest: marks to ruby, glossary-wins merge, author-ruby priority, offset mapper (before, inside and after a mark;
  empty marks).
- Playwright (`web/e2e/`, a new seed in `tools/e2e_seed.py` per the conventions in `CLAUDE.md`: own seeded rows, glossary
  phrases that occur only in this spec's series, no "E2E chapter" in names): the menu item opens the dialog with the
  selection; the copy button puts the original text on the clipboard (grant clipboard permissions in the test); the
  toggle shows the original text with ruby `rt` holding the translation, turning it off restores the replaced text;
  the setting persists after reload.
- Gate: `pytest`, `ruff check .`, `npm test`, `npm run e2e` (the editor specs), `tsc` clean, `npm run gen:api`
  diff committed.

## Left to the builder

Class names, icons, CSS, the exact function names, and where the pure helpers live. Update the `CLAUDE.md` editor
paragraph (glossary ruby and the marks field) and delete the TODO entry.

## Delegation

One plan with three ordered tasks. Tasks 1 and 2 (menu item, copy button) suit DeepSeek V4.1 Flash; task 3 (server
marks, mapping and the ruby merge) suits DeepSeek V4 Pro. Same branch, so run them in order; Claude reviews after each.
