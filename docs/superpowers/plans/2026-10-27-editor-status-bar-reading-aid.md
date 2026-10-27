# Editor status bar, reading aid and navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regroup the editor's status bar, add chapter navigation, a reading aid (furigana / romaji) on the active card,
author ruby rendered as furigana on every card, a jump-back control and an end-of-chapter card.

**Architecture:** One new API endpoint tokenises text with MeCab (fugashi, already the optional `mecab` extra) and returns
surface + kana per token; everything else is SPA. Pure TS modules do kana conversion, author-ruby detection, kanji
alignment and token placement; `paint.ts` gains a ruby-aware layout so source text stays offset-based. The status bar is
rebuilt from small components; navigation goes through one guarded "leave" function that awaits the save store.

**Tech Stack:** FastAPI + fugashi/unidic-lite; React 19, TanStack Query, react-router 8, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-27-editor-status-bar-reading-aid-design.md`

## Global Constraints

- Colours only through tokens in `web/src/styles/tokens.css`; editor styles live in `web/src/styles/editor.css`.
- Routers built with `api_router()`; handlers never `commit()`; no Python module over ~400 lines.
- After any API change run `npm run gen:api` and commit `web/src/api/schema.d.ts`.
- `npm test` covers pure modules only; components are covered by Playwright (`web/e2e/`).
- E2E: each spec owns its seeded rows in `tools/e2e_seed.py`; seed names must not contain "E2E chapter".
- User setting key `reading_aid`: `"off" | "hiragana" | "katakana" | "romaji"`; anything else means `"off"`.
- Generated readings only on the active card; author ruby on every card, whatever `reading_aid` is.
- Author ruby: base = run of one kind directly before `(`/`（`: kanji (with 々 〆 ヶ) or Latin letters/digits (half or
  full width); reading = non-empty kana only (hiragana, katakana, ー). Otherwise text stays as written.
- Romaji: Hepburn with macrons for long vowels (ōkiku, shiyō); kana words get readings too; Latin and punctuation none.
- Hiragana/katakana: readings over kanji runs only; when alignment fails, whole reading over whole token.
- Every `<rt>` is wrapped `<rp>(</rp><rt>…</rt><rp>)</rp>`.
- A chapter move awaits a save flush; if the store ends in `error`, stay and show the notice
  `Not moved: the last changes are not saved yet` beside the pill.

## Review Focus

1. Ordinary brackets — `(笑)`, `（1）`, `ABC (note)`, `かな(かな)` — must stay as written. Test: Task 3 `authorRuby` cases.
2. Characters outside the BMP (`𠮷野家`) — UTF-16 offsets must line up between the API tokens and the painted text. Test:
   Task 3 `placeTokens` with `𠮷野家に行く`; Task 1 returns surfaces only, never offsets.
3. Whitespace MeCab drops (half-width spaces, `　`, `\n`) — placement must skip it, not shift every later reading. Test:
   Task 1 API test with `今日は 晴れ`; Task 3 `placeTokens` with spaces.
4. A glossary / katakana / find span crossing an author-ruby boundary must not break the ruby nesting or drop text. Test:
   Task 4 `layout` with a span from inside a base to after the hidden reading.
5. Chapters without a number or volume (Illustrations chapter, "No volume" chapters, a one-chapter series) — navigation
   must not crash or point past the ends. Test: Task 6 `chapterNeighbours` cases.

---

### Task 1: Readings endpoint

**Files:**
- Create: `api/core/readings.py`, `api/routers/readings.py`, `api/schemas/readings.py`
- Modify: `api/main.py` (include the router), `web/src/api/schema.d.ts` (regenerated)
- Test: `tests/test_readings.py`

**Interfaces:**
- Produces: `POST /readings` body `{"text": str}` (max 5,000 chars, else 422) →
  `{"available": bool, "message": str, "tokens": [{"surface": str, "kana": str, "pos": str}]}`.
  `kana` is the UniDic kana form (tab column 2, katakana; `""` when MeCab gives none or `*`); `pos` the first POS
  field (`名詞`, `助詞`, `助動詞`, ...). Tokens are in text order; no offsets (the SPA places them, Task 3).
  When MeCab is missing: `available=false`, `message=nouns.SETUP`, `tokens=[]`, status 200.
- Python: `readings.tokens(text: str, tagger) -> list[Token]` with `Token = NamedTuple(surface, kana, pos)`.
  Schema classes `ReadingsRequest`, `ReadingToken`, `ReadingsOut`, so the SPA type is `Schemas["ReadingToken"]`.

- [ ] **Step 1: Write the failing tests** in `tests/test_readings.py`:
  - `test_tokens_parse_surface_kana_pos`: a fake tagger (same shape as `_FakeTagger` in `tests/test_nouns.py`) returning
    `"大きく\tオーキク\tオオキク\t大きい\t形容詞-一般\nEOS\n"` → `[Token("大きく", "オオキク", "形容詞")]`.
  - `test_tokens_star_kana_is_empty`: kana column `*` → `kana == ""`.
  - `test_api_returns_tokens` (monkeypatch `api.core.nouns.tagger` to return the fake) → 200, tokens as above.
  - `test_api_unavailable`: monkeypatch `nouns.tagger` to raise `nouns.Unavailable(nouns.SETUP)` → 200,
    `available is False`, `tokens == []`.
  - `test_api_text_too_long` → 422 for 5,001 chars.
  - `test_api_needs_login` → 401 without a session.
  - `test_real_mecab_spaces` (`pytest.importorskip("fugashi")`): `今日は 晴れ` → surfaces joined equal `今日は晴れ`.
- [ ] **Step 2: Run** `pytest tests/test_readings.py -v` — expect FAIL (module missing).
- [ ] **Step 3: Implement** `readings.tokens` (parse lines until `EOS`, split on tab) and the router; call the tagger
  under `nouns._lock` as `nouns.frequent_nouns` does.
- [ ] **Step 4: Run** `pytest tests/test_readings.py tests/test_commit_boundary.py -v` — PASS; `ruff check .` clean.
- [ ] **Step 5:** `cd web && npm run gen:api`.
- [ ] **Step 6: Commit** `feat(readings): MeCab readings endpoint for the editor's reading aid`.

### Task 2: Kana conversion and romaji

**Files:**
- Create: `web/src/editor/kana.ts`, `web/src/editor/kana.test.ts`

**Interfaces:**
- Produces: `toHiragana(s: string): string`, `toKatakana(s: string): string` (code-point shift, other characters
  unchanged); `toRomaji(kana: string, pos?: string): string` — Hepburn: `し`→shi, `ち`→chi, `つ`→tsu, `ふ`→fu,
  `じ`/`ぢ`→ji, `づ`→zu, yōon (`きょ`→kyo), small `っ` doubles the next consonant (`っち`→tchi), `ん`→n (`n'` before a
  vowel or y), long vowels with macrons for `oo`/`ou`→ō, `uu`→ū, `aa`→ā, `ee`→ē, and `ー` lengthens the previous vowel
  with a macron; `ii` stays `ii`. When `pos === "助詞"`: `は`→wa, `へ`→e, `を`→o.

- [ ] **Step 1: Write the failing tests:** `toHiragana("オオキク") === "おおきく"`, `toKatakana("ゆめ") === "ユメ"`,
  `toRomaji("おおきく") === "ōkiku"`, `toRomaji("しよう") === "shiyō"`, `toRomaji("ケッコン") === "kekkon"`,
  `toRomaji("なったら") === "nattara"`, `toRomaji("ステータス") === "sutētasu"`, `toRomaji("ちょっと") === "chotto"`,
  `toRomaji("きんえん") === "kin'en"`, `toRomaji("おいしい") === "oishii"`, `toRomaji("は", "助詞") === "wa"`,
  `toRomaji("は") === "ha"`, `toRomaji("を", "助詞") === "o"`.
- [ ] **Step 2: Run** `cd web && npx vitest run src/editor/kana.test.ts` — FAIL.
- [ ] **Step 3: Implement** with a syllable table (longest match first: yōon before single kana), working on hiragana.
- [ ] **Step 4: Run** the same — PASS.
- [ ] **Step 5: Commit** `feat(editor): kana conversion and Hepburn romaji`.

### Task 3: Author ruby, alignment and placement

**Files:**
- Create: `web/src/editor/ruby.ts`, `web/src/editor/ruby.test.ts`

**Interfaces:**
- Consumes: `toHiragana`, `toKatakana`, `toRomaji` (Task 2); token shape `{surface, kana, pos}` (Task 1,
  `Schemas["ReadingToken"]` after gen:api).
- Produces:
  - `type ReadingMode = "off" | "hiragana" | "katakana" | "romaji"`; `readingMode(v: unknown): ReadingMode`.
  - `interface Ruby { from: number; to: number; rt: string; hide?: [number, number] }` — UTF-16 offsets into the shown
    text; `[from, to)` is the base; `hide` is the `(reading)` range (brackets included) not drawn as text.
  - `authorRuby(text: string): Ruby[]`.
  - `placeTokens(text: string, tokens: Token[]): { from: number; to: number; token: Token }[]` — scans forward with
    `indexOf` from a cursor; a token not found is skipped (cursor unchanged).
  - `alignReading(surface: string, kana: string): { from: number; to: number; rt: string }[]` — offsets within
    `surface`, reading in katakana; kanji runs only; kana in surface matched against kana in the reading as anchors;
    no match → one item over the whole surface.
  - `generatedRuby(text: string, tokens: Token[], mode: ReadingMode, author: Ruby[]): Ruby[]` — `off` → `[]`;
    hiragana/katakana: aligned kanji runs, converted to the mode's script; romaji: one ruby per token with any Japanese
    character, `助動詞` tokens merged into the previous token, romanised with `toRomaji(token.kana, token.pos)` so
    particles read wa / e / o; tokens with empty kana skipped. Any part already inside an
    author ruby base or hidden range is dropped (romaji: the author reading, converted, covers the base and the token's
    remaining kana stays on the rest).
- [ ] **Step 1: Write the failing tests:**
  - `authorRuby("大(おお)きく")` → `[{from:0,to:1,rt:"おお",hide:[1,5]}]`; `"喰(く)い千切(ちぎ)る"` → two rubies;
    `"STATUS(ステータス)"`, `"１(ひと)つ"` (full-width digit), `"人々（ひとびと）"` (full-width brackets) → one each;
    `"彼はSTATUS(ステータス)"` → base is `STATUS` only; `"超AI(ちょうエーアイ)"` → base `AI`.
  - unchanged (`[]`): `"(笑)"`, `"笑(笑)"`, `"（1）"`, `"ABC (note)"`, `"かな(かな)"`, `"漢字()"`, `"漢字(kanji)"`.
  - `placeTokens("𠮷野家に行く", [{surface:"𠮷野家",…},{surface:"に",…},{surface:"行く",…}])` → froms `0, 4, 5`.
  - `placeTokens("今日は 晴れ", …)` → `晴れ` at 4.
  - `alignReading("大きく","オオキク")` → `[{0,1,"オオ"}]`; `("動き出す","ウゴキダス")` → `[{0,1,"ウゴ"},{2,3,"ダ"}]`;
    `("人々","ヒトビト")` → `[{0,2,"ヒトビト"}]`; `("今日","キョウ")` → `[{0,2,"キョウ"}]`;
    `("行っ","イッ")` → `[{0,1,"イ"}]`; a mismatch such as `("大きく","ダイ")` → `[{0,3,"ダイ"}]`.
  - `generatedRuby` hiragana for `大きく` → rt `おお`; romaji for tokens `なっ`(動詞) + `たら`(助動詞) → one ruby `nattara`;
    romaji over `promise` → none; romaji for `は`(助詞) → `wa`; an author ruby on `大` with hiragana mode → generated ruby for `大` dropped.
- [ ] **Step 2: Run** `npx vitest run src/editor/ruby.test.ts` — FAIL.
- [ ] **Step 3: Implement.** Alignment algorithm (the signature does not pin it):
  ```
  segments = split surface into runs: kanji-run | kana-run (kana compared as katakana)
  walk the reading with a cursor; for each kana-run, find it in the reading at/after the cursor
  (for the last run, match at the reading's end); the reading between the previous anchor and this one
  belongs to the kanji-run before it. Any run not found, or a kanji-run left with an empty share → fallback.
  ```
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(editor): author ruby detection, kanji alignment and token placement`.

### Task 4: Ruby-aware painting

**Files:**
- Modify: `web/src/editor/paint.ts`, `web/src/editor/paint.test.ts`, `web/src/editor/LineCard.tsx`,
  `web/src/editor/CardList.tsx`, `web/src/styles/editor.css`

**Interfaces:**
- Consumes: `Ruby`, `authorRuby` (Task 3).
- Produces:
  - `type Piece = { kind: "text"; seg: Segment } | { kind: "ruby"; base: Segment[]; rt: string; rtClasses: string[] }`;
    `layout(text: string, spans: Span[], ruby: Ruby[]): Piece[]` — hidden ranges produce no text; spans are cut at ruby
    edges so a span crossing a base boundary yields one segment inside and one outside; `rtClasses` gets
    `find-current` when a span with that class overlaps the ruby's `hide` range.
  - `Painted` gains an optional `ruby?: Ruby[]` prop and renders `<ruby>{base}<rp>(</rp><rt className>…</rt><rp>)</rp></ruby>`.
  - `LineCard` gains `readings?: Ruby[]` (generated, active card only); it always passes
    `authorRuby(source)` merged with `readings`. `CardList` passes `readings` to the active card only.
- [ ] **Step 1: Write the failing tests** in `paint.test.ts`:
  - `layout("大(おお)きく", [], authorRuby(...))` → `[ruby(base "大", rt "おお"), text "きく"]` and no `(`/`)` text.
  - a span `{from:0,to:6,cls:"jp-kanji"}` over `大(おお)きく` → the base segment has `jp-kanji`, `きく` has it, total
    drawn text is `大きく`.
  - a span `{from:2,to:4,cls:"find-current"}` (inside the reading) → `rtClasses` contains `find-current`.
  - with no ruby, `layout` text equals `segments` (existing behaviour unchanged).
- [ ] **Step 2: Run** `npx vitest run src/editor/paint.test.ts` — FAIL.
- [ ] **Step 3: Implement** `layout` on top of `segments` (add ruby edges and hide edges as cuts), then `Painted`,
  `LineCard`, `CardList`. CSS: `.source rt { font-size: .5em; color: var(--muted); }`, romaji `rt` in `var(--sans)`
  (class `rt-latin` set when the reading is Latin); `.source` line-height unchanged when no ruby, `2.2` on an active card
  with readings.
- [ ] **Step 4: Run** `npm test` — PASS (all editor tests, `parse`/`find` included).
- [ ] **Step 5: Commit** `feat(editor): show author ruby as furigana`.

### Task 5: Reading-aid setting, switch and fetch

**Files:**
- Create: `web/src/editor/useReadings.ts`, `web/src/editor/ReadingSwitch.tsx`
- Modify: `web/src/editor/Editor.tsx`

**Interfaces:**
- Consumes: `POST /readings` (Task 1), `generatedRuby`, `readingMode` (Task 3), `LineCard.readings` (Task 4).
- Produces:
  - `useReadings(text: string, mode: ReadingMode): { ruby: Ruby[]; available: boolean; message: string }` — TanStack
    query keyed `["readings", text]`, `enabled: mode !== "off" && text !== ""`, `staleTime: Infinity`, passes the
    query `signal` to `api.POST` so a query left by a fast line change is cancelled; returns
    `generatedRuby(text, tokens, mode, authorRuby(text))`. A result for an old text is keyed to that text and never
    used for another line.
  - `<ReadingSwitch mode onChange disabled title />` — `role="group" aria-label="Reading aid"`, four buttons
    `Off` / `あ` / `ア` / `a` with `aria-pressed`, `aria-label`s `Readings off`, `Hiragana readings`, `Katakana readings`,
    `Romaji readings`. Disabled with `title` = the endpoint's message when `available` is false.
  - In `Editor`: `mode = readingMode(settings.data?.reading_aid)`; changing it writes `reading_aid` the way the TM toggle
    writes `tm_visible`. The switch is mounted in the status bar's tools zone in Task 7; until then mount it in `extra`.
- [ ] **Step 1:** Implement both files and wire them into `Editor.tsx` (the text is the active card's shown source:
  `raw_text` when `parse === -2`, else `display_text`).
- [ ] **Step 2: Run** `npm test && npx tsc -b` — PASS.
- [ ] **Step 3: Check by hand** with `docker compose --profile dev up` (mecab extra installed): `あ` shows `おお` over 大 on
  the active card only; stepping lines quickly does not flash another line's readings.
- [ ] **Step 4: Commit** `feat(editor): reading aid switch with MeCab readings on the active card`.

### Task 6: Chapter navigation

**Files:**
- Create: `web/src/editor/chapterNav.ts`, `web/src/editor/chapterNav.test.ts`, `web/src/editor/ChapterNav.tsx`,
  `web/src/editor/useLeave.ts`
- Modify: `web/src/editor/Editor.tsx`

**Interfaces:**
- Consumes: `useDocuments()` and `useAllVolumes()` from `web/src/library/queries.ts`; `ed.store` (`flush()` never
  rejects; `getState().state`).
- Produces:
  - `chapterNeighbours(docs: Doc[], id: number): { prev: Doc | null; next: Doc | null; volume: Doc[] }` — docs of the
    same `series_id` sorted by `series_order`; `volume` = those with the same `volume_id` (null groups loose chapters).
    Unknown id → `{prev: null, next: null, volume: []}`.
  - `useLeave(store, setNotice): (to: string) => Promise<void>` — awaits `store.flush()`; if `store.getState().state ===
    "error"`, calls `setNotice("Not moved: the last changes are not saved yet")` and stays; else `navigate(to)`.
  - `<ChapterNav doc chapters onGo />`: `‹` (`aria-label="Previous chapter"`), title button (`Ch. N` when
    `chapter_number` is not null, then the shown title, `▾`) opening a `Menu` of `volume` rows
    (`role="menuitemradio"`, `aria-checked` on the current, text `N · title`, progress `%` on the right), `›`
    (`aria-label="Next chapter"`); arrows disabled at the ends.
- [ ] **Step 1: Write the failing tests** (`chapterNav.test.ts`): middle chapter → both neighbours; first → `prev` null;
  last → `next` null; an Illustrations chapter (`chapter_number` null) sits by `series_order`; a loose chapter's
  `volume` lists only loose chapters; a one-chapter series → both null; other series' docs never appear; unknown id.
- [ ] **Step 2: Run** `npx vitest run src/editor/chapterNav.test.ts` — FAIL.
- [ ] **Step 3: Implement** the three files; mount `ChapterNav` in `extra` for now (Task 7 moves it).
- [ ] **Step 4: Run** `npm test && npx tsc -b` — PASS.
- [ ] **Step 5: Commit** `feat(editor): previous/next chapter and chapter list`.

### Task 7: Status bar layout

**Files:**
- Modify: `web/src/editor/StatusBar.tsx`, `web/src/editor/Editor.tsx`, `web/src/styles/editor.css`,
  `web/e2e/tm.spec.ts`, `web/e2e/chapter-title.spec.ts`, `web/e2e/source.spec.ts`

**Interfaces:**
- Consumes: `ChapterNav` (Task 6), `ReadingSwitch` (Task 5).
- Produces: `StatusBar` props replace `title`/`extra` with `crumbs: { series: {id, title}; volume: {id: number | null;
  label: string} }`, `nav: ReactNode`, `tools: ReactNode`; keeps `line`, `total`, `percent`, `words`, `phrase`,
  `save`, `onRetry`, `notice`; adds `translated: number` and `lineCount: number` for `X of Y lines`.
  Layout (spec "The status bar"): `<nav aria-label="Breadcrumb">` row (`Library` → `/`, series →
  `/series/:id`, volume → `/series/:id?tab=volumes&volume=<id|none>`, label `No volume` when null); then a grid row:
  left `nav`; centre pill (`role="status"`, ring SVG `aria-label="<percent>% translated"`, `X of Y lines`, `N words`,
  `at L<line>`, save text from `SAVE_TEXT`; error message + Retry button beside it; phrase, notice and
  `Spellcheck unavailable` (when `!spell.available`) after it); right
  `tools`.
  Tools (built in `Editor`): `ReadingSwitch`, divider, icon buttons `aria-label` `Translation memory` / `Machine
  translation` / `Images` with `aria-pressed` (Images only when the chapter has images; `aria-pressed` = not collapsed),
  divider, `Menu` with `buttonLabel="Chapter actions"` and items: Edit source (`/documents/:id/source`), Split chapter
  (`/documents/:id/split`), Go to line… (runs the existing `go_to_line` action), Series glossary
  (`/series/:id?tab=glossary`), Series tools (`/series/:id?tab=tools`). Links go through `useLeave`.
  CSS: chapter title `text-overflow: ellipsis` with `min-width: 0`; under the existing narrow media query the grid
  becomes one column and the tools wrap.
- [ ] **Step 1: Update the e2e specs first:** `tm.spec.ts` clicks `getByRole("button", { name: "Translation memory" })`
  and checks `aria-pressed` `false` then `true`; `chapter-title.spec.ts` reads the title from
  `getByRole("button", { name: /Shown chapter title/ })`; `source.spec.ts` opens `Chapter actions` and clicks
  `getByRole("menuitem", { name: "Edit source" })`.
- [ ] **Step 2: Run** `cd web && npx playwright test tm chapter-title source` — FAIL.
- [ ] **Step 3: Implement** the layout and move the switch and `ChapterNav` out of `extra`.
- [ ] **Step 4: Run** the same specs plus `npx playwright test editor narrow` — PASS.
- [ ] **Step 5: Commit** `feat(editor): status bar grouped into breadcrumb, place, progress and tools`.

### Task 8: Jump back and end-of-chapter card

**Files:**
- Create: `web/src/editor/JumpBack.tsx`, `web/src/editor/ChapterEnd.tsx`
- Modify: `web/src/editor/Editor.tsx`, `web/src/editor/LineCard.tsx` (add `data-index={index}` on the article),
  `web/src/styles/editor.css`

**Interfaces:**
- Consumes: `firstUntranslated` (`rows.ts`), `chapterNeighbours`, `useLeave` (Task 6), `PublishDialog` /
  `IllustrationsPublish` chosen by `doc.is_illustrations` as `web/src/library/ChapterMenu.tsx` does, the
  `["wp", "credentials"]` query (`kind === "wordpress" && name === ""` with an `endpoint_url` = set up).
- Produces:
  - `<JumpBack active untranslated onActivate onReturn />` — an `IntersectionObserver` on
    `article[data-index="<n>"]` for both targets; buttons `Next untranslated · line N` (arrow up or down from the
    target's position relative to the viewport) and `Back to editing · line N`; only off-screen targets show; one button
    when both are the same line. `onReturn` scrolls the active card into view and calls `view.current?.focus()` (the CodeMirror view in
    `Editor`), so keyboard focus leaves the pill. CSS: the pill is `position: sticky; bottom` in the editor column with
    `z-index: 1`, below the status bar (`z-index: 2`, as today); the status bar's menus open inside it and so sit above
    the cards.
  - `<ChapterEnd />` after `CardList`: all translated → `All N lines translated · W words`, primary
    `Next chapter →` with `N · title`, `Publish to WordPress` (only when set up), `Back to series`; lines left →
    `K lines left`, primary `Jump to line N`, the rest secondary; no next chapter → `Last chapter of the series`.
- [ ] **Step 1:** Implement both components and mount them in `Editor`.
- [ ] **Step 2: Run** `npm test && npx tsc -b` — PASS.
- [ ] **Step 3: Commit** `feat(editor): jump back to work and end-of-chapter card`.

### Task 9: End-to-end coverage and docs

**Files:**
- Create: `web/e2e/editor-nav.spec.ts`
- Modify: `tools/e2e_seed.py`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Seed: series `Nav series` with volume 1 holding `Nav one` (lines: `大(おお)きな夢(ゆめ)を見た。`,
  `STATUS(ステータス)を開く。`, `今日は晴れ。`, twenty filler lines `行N。` so the list scrolls) and `Nav two`
  (one line, `二話目です。`).
- [ ] **Step 1: Write the specs:**
  - `chapter arrows and list`: open `Nav one`; `Next chapter` → URL is `Nav two`'s and `二話目です。` shows; `Previous
    chapter` back; title button → menu item `2 · Nav two` opens it.
  - `failed save stops the move`: `page.route("**/documents/*/lines", r => r.request().method() === "PATCH" ? r.fulfill({ status: 500 }) : r.continue())`,
    type a translation, click `Next chapter` → URL unchanged and `Not moved: the last changes are not saved yet` shows.
  - `author ruby always shows`: with readings off, `ruby` containing `大` has `rt` `おお` and the text `(おお)` is not
    visible; `STATUS` has `rt` `ステータス`.
  - `reading aid on the active card` (skip when `POST /readings` answers `available: false`): click `Hiragana
    readings` → active card shows `rt` `きょう` over `今日` after activating that line; a non-active card has no
    generated `rt`; `Romaji readings` → `rt` `kyō` over `今日`.
  - `jump back`: activate line 1, scroll to the bottom → `Back to editing · line 1` visible; click → line 1 card in
    view; `Next untranslated` button visible while line 2 is off screen.
  - `end card`: in `Nav two` with its line translated → `All 1 lines translated` and no `Next chapter →`, text
    `Last chapter of the series`.
- [ ] **Step 2: Run** `cd web && npx playwright test editor-nav` — PASS (Postgres up, `ta_e2e` reset, mecab extra).
- [ ] **Step 3:** Add a CLAUDE.md paragraph: `POST /readings` (MeCab tokens, surfaces only, SPA places them), the
  `reading_aid` setting, author-ruby rule (`web/src/editor/ruby.ts`), and the spec path.
- [ ] **Step 4: Run** `pytest`, `ruff check .`, `cd web && npm test && npx playwright test` — all PASS.
- [ ] **Step 5: Commit** `test(editor): navigation, ruby and reading aid flows; docs`.
