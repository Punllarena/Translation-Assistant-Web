# Editor status bar, reading aid and navigation

Date: 2026-10-27. Mockups: the "Editor redesign options" canvas
(https://claude.ai/artifact/V3djeRYZZd8jsrvhSMCjV8); the chosen bar is the artboard "Chosen · combined status bar",
the reading aids "Reading aids · placement and script" (scripts row and Scope B), the jump pill and end card
"Back to untranslated + chapter end".

## Why

The editor's status bar (`web/src/editor/StatusBar.tsx`, filled from `Editor.tsx`) is one flat row of links, numbers and
buttons with no grouping: the chapter title, line counter, percent, words and save state sit next to Edit source, Split,
Series tools and three show/hide buttons. There is no way to move to another chapter without going back to the series
page. The source text gives no reading help, and author furigana from syosetu or EPUB imports shows as inline
`漢字(かんじ)`, which is noisy. On a long chapter it is easy to scroll away from where the work is.

Goal: a bar grouped by what things are (where you are, how far along, tools), chapter navigation from the bar, readings
over the source text, and ways back to the work.

## Goals

1. Regroup the status bar as below.
2. Previous / next chapter and a chapter list in the bar.
3. A reading aid (furigana or romaji) over the **active card's** source text.
4. Imported author ruby always shown as furigana, on every card, whatever the reading aid setting.
5. A floating jump control back to the next untranslated line and back to the active card.
6. An end-of-chapter card.

## Non-goals

- Readings on non-active cards (generated ones; author ruby is the exception, goal 4).
- A "hard kanji only" filter (JLPT / grade cut-off). Explored and not chosen.
- The line-map rail and the chapters drawer (option C), glossary hover cards, focus mode, new keyboard shortcuts for
  chapter navigation. Explored or suggested, not chosen.
- Changing how readings are stored: nothing about readings is written to the database.
- Changing the source text, `raw_text`, `display_text` or exports.

## The status bar

Two rows, sticky as today.

**Row 1: breadcrumb.** `Library / <series title> / <volume label>`, each a link: Library to `/`, the series to
`/series/:id`, the volume to `/series/:id?tab=volumes&volume=<id>` (or `volume=none` for a loose chapter, labelled
"No volume"). Small, muted.

**Row 2: three zones** (grid: left, centre, right; the centre pill stays centred).

- **Left: where you are.** `‹` button, then a button showing `Ch. N` (mono, muted; omitted when the chapter has no
  number, e.g. the Illustrations chapter) and the chapter title (serif) with a `▾`, then `›`. The arrows go to the
  previous / next chapter of the series in `series_order` (across volumes, Illustrations chapters included); each is
  disabled at the ends. The title button opens a dropdown listing the chapters of the current volume (or of "No volume")
  with their number, title and progress percent, the current one highlighted; choosing one opens it. Data: the existing
  `GET /documents` list (`series_order`, `chapter_number`, `progress`), filtered by `series_id` client-side.
  Moving chapter awaits a save-store flush first. If that flush fails, stay on the chapter: the pill shows the error and
  Retry, and a notice says the move was stopped so nothing is lost.
- **Centre: the pill.** Progress ring (translated share), `X of Y lines`, `N words`, `at L<line>`, save state
  (Saved / Saving… / Unsaved changes / Not saved). A save error shows its message and a Retry button in or beside the
  pill. The phrase indicator (`Phrase a/b`) and notices (word added, lines missing, spellcheck unavailable) keep showing,
  next to the pill.
- **Right: tools.** The reading-aid switch (segmented: `Off` / `あ` / `ア` / `a`), a divider, icon toggle buttons for TM,
  MT and Images (pressed state shown; Images only when the chapter has images; each keeps its current setting key
  `tm_visible` / `mt_visible` / `images_collapsed`), a divider, and a `⋯` menu holding: Edit source, Split chapter,
  Go to line…, Series glossary (`/series/:id?tab=glossary`), Series tools (`/series/:id?tab=tools`).
  Icon buttons need `aria-label` and `aria-pressed`.

The chapter title truncates with an ellipsis before any tool button is pushed off screen. At phone width the zones stack and wrap (the editor already switches layout at its media query in `editor.css`).
Styles use tokens only (CLAUDE.md, Phase 7a).

## Reading aid

**Setting.** A user setting `reading_aid`: `off` (default) | `hiragana` | `katakana` | `romaji`, saved through
`PUT /settings` like `tm_visible`, so it follows the account.

**Scope.** Only the active card's source text gets generated readings. Other cards render as today (plus author ruby,
below).

**Scripts.**
- `hiragana` / `katakana`: the reading sits over the kanji only, not over okurigana or kana words
  (`<ruby>大<rt>おお</rt></ruby>きく`).
- `romaji`: a reading over every Japanese word, kana words included (`<ruby>なったら<rt>nattara</rt></ruby>`).
  Hepburn with macrons for long vowels (ōkiku, shiyō), as in the mockup. Latin text and punctuation get nothing.

**Where readings come from.**
1. Author ruby in the line (see below) wins for the word it covers; in katakana / romaji mode its reading is converted
   to that script.
2. Everything else: MeCab with UniDic on the server (the optional `mecab` extra, fugashi + unidic-lite, already used by
   `api/core/nouns.py`). A new endpoint returns, for a line's displayed text, the tokens with their offsets and reading.
   The SPA fetches it for the active line only, caches per line and text, and shows the card without readings until it
   arrives. A reply for a line that is no longer active, or whose text changed, is never shown on another line;
   stepping quickly through lines should not leave a queue of requests behind (cancel or skip the stale ones).
4. Kanji alignment (hiragana / katakana modes): MeCab gives one reading per token (`大きく` → `オオキク`). Match the
   token's kana against the reading (in one script) to find the kanji runs and their share of the reading, kana in the
   middle included (`動き出す` → 動/ウゴ, 出/ダ). `々` belongs to its kanji run (`人々` → ヒトビト). When the kana
   cannot be matched, put the whole reading over the whole token rather than drop it.
3. When MeCab is not installed, the switch is disabled with a tooltip like "Readings need MeCab on the server"
   (as spellcheck shows "Spellcheck unavailable"); author ruby still renders.

The readings follow the text that is displayed (`display_text`, or `raw_text` in the Edit-source view, `parse === -2`),
including when glossary substitution has changed it.

## Author ruby

Imports store ruby as `base(reading)` (`api/core/scrape.py`, `api/core/epub_units.py`). The editor renders it as
`<ruby>base<rt>reading</rt></ruby>` on every card, always, whatever `reading_aid` says, and the `(reading)` text is
not shown.

The stored form loses where the base began (`彼はSTATUS(ステータス)` could have been ruby over `STATUS` or over the
whole run), so the base is the run of **one kind** of character directly before the parenthesis:

- a run of kanji (with 々, 〆, ヶ): `喰(く)い千切(ちぎ)る`, `人々(ひとびと)`;
- a run of Latin letters and digits, half or full width: `STATUS(ステータス)`, `Skill(スキル)`, `１(ひと)つ`.

Y must be only kana (hiragana, katakana, ー) and non-empty. Anything else (`(笑)` with no base before it, `(1)`, English
in brackets, a kana base) stays as written. Full-width `（）` follows the same rule. Mixed bases such as `超AI(ちょうエーアイ)`
get ruby over the last run only (`AI`); accepting that is the designer's call, because the stored text cannot say more.
(Keeping the base boundary at import, e.g. syosetu's own `｜base《reading》` notation, would fix this for new imports and
is a separate change.)

Rendering stays offset-based: `paint.ts` already cuts the text into segments at span edges, so an author-ruby span is one
more span; its `(reading)` characters are drawn as the `<rt>` of the base segment instead of as text. Generated readings
are spans over the same offsets. Each `<rt>` has `<rp>(</rp>` / `<rp>)</rp>` around it so copying and screen readers get
`大(おお)きく`, not `大おおきく`.

Find, sentence highlighting (phrase mode), glossary/katakana colouring and spellcheck offsets must still land on the
right characters: the ruby rendering is a display change over the same text. A Find hit inside the hidden
`(reading)` is highlighted in the `<rt>` (designer's call). In romaji mode, when a MeCab word runs past an author ruby
base (`大(おお)きく`), the author's reading covers the kanji and MeCab's the rest (designer's call).

## Jump back

A floating control near the bottom of the editor column, shown only when its target is off screen:

- **Next untranslated · line N** (arrow pointing up or down toward it): the first line of the chapter with source text
  and no translation (`firstUntranslated` in `rows.ts`). Clicking activates that line (which scrolls it into view).
  Hidden when there is no untranslated line.
- **Back to editing · line N**: the active card, when it is scrolled off screen. Clicking scrolls it back into view and
  focuses the editor.

When both point at the same line, show one. Both together sit side by side, primary style on "Next untranslated".

## End-of-chapter card

After the last card, always shown:

- All lines translated: "All N lines translated · W words", then a primary **Next chapter →** link with the next
  chapter's number and title, a **Publish to WordPress** action (the existing single-chapter publish, with its
  re-publish confirmation, chosen the way `web/src/library/ChapterMenu.tsx` picks `IllustrationsPublish` or
  `PublishDialog`; hidden when WordPress is not set up), and **Back to series**.
- Lines left: "K lines left" with **Jump to line N** (the next untranslated line) in the primary spot, and the same
  next-chapter, publish and back links as secondary.
- Last chapter of the series: no next-chapter link; say it is the last chapter.

## Left to the builder

- The readings endpoint's path and shape, its caching, and how MeCab tokens map to "words" for romaji (grouping
  inflections and auxiliaries with their stem is fine, per token is acceptable).
- Aligning a MeCab reading to the kanji of a mixed token (okurigana stripping).
- Kana conversion and romanisation: a small pure module (TS or Python) with tests; a dependency is acceptable if small.
- Icons (inline stroke SVG like the mockups), exact sizes, and how the bar collapses at narrow widths.
- How the chapter list is fetched and cached (reuse of the picker's query is fine).
- How the jump control knows a card is off screen (an `IntersectionObserver` rather than a scroll handler is the
  expected shape).
- Playwright coverage: at least chapter navigation (including a failed save stopping the move), the reading-aid switch,
  author ruby rendering and the jump control, following the E2E conventions in CLAUDE.md.
