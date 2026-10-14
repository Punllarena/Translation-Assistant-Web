# ta-web redesign: visual system, dark theme, editor layout

**Status:** design approved on the canvas, spec awaiting review
**Date:** 2026-10-14
**Canvas (reference mockups):** https://claude.ai/artifact/HVHMBMZS6utjpArPXVp3ZU
**Builds on:** `2026-10-10-web-app-port-design.md` (the port spec). Nothing here changes
the data model, the API contracts listed there, or the editor's saving and key handling (§5).

## 1. Purpose

Phases 1–6 ported every feature of the desktop app, but the SPA is unstyled
(`web/src/styles.css`, 72 lines, system font, browser-default controls). This work gives
the SPA one visual system, a dark theme, and an editor layout that holds up when the
find bar opens and on a phone. It is a presentation change: every screen keeps its
current data, routes and behaviour, except for the additions listed in §9.

Success means:

- Every screen on the canvas is built, in light and dark, from shared tokens.
- The editor's toolbar, find bar and side column never overlap or leave a gap, at any
  scroll position, with find open or closed.
- On a narrow screen (below `60rem`) the editor is usable one-handed: the translation
  aids open in a bottom sheet from the toolbar.
- The existing Playwright suite passes, with selector updates only where §11 lists them.

## 2. The canvas

The canvas is the visual reference; this spec is the behavioural one. Where they differ,
this spec wins. Boards:

| Row | Boards |
|---|---|
| Core screens | Editor · Library · Statistics · Editor, scrolled with find open |
| Dark theme | Editor, dark · Library, dark |
| Settings | Profiles · Machine translation · WordPress · Shortcuts |
| Import, publishing, sign-in | Import · Publish one chapter · Batch publish · Sign in and invite |
| Phone | Editor, phone · Editor, phone, aids open |

Bracketed text on the boards (`[Series title]`, `[Error message from the server]`) marks
real data the app fills in; it is not copy.

## 3. Visual system

### 3.1 Tokens

All colour comes from custom properties on `:root`. Components never use a literal colour.
Values are OKLCH; the dark set applies under `:root[data-theme="dark"]` (§4).

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `oklch(0.975 0.004 255)` | `oklch(0.185 0.012 265)` | page |
| `--surface` | `oklch(0.995 0.002 255)` | `oklch(0.225 0.014 265)` | cards, panels, header |
| `--raised` | `oklch(0.985 0.004 255)` | `oklch(0.205 0.013 265)` | hover rows |
| `--field` | `oklch(0.995 0.002 255)` | `oklch(0.195 0.012 265)` | inputs |
| `--ink` | `oklch(0.22 0.02 265)` | `oklch(0.93 0.008 265)` | text |
| `--muted` | `oklch(0.46 0.02 265)` | `oklch(0.73 0.015 265)` | secondary text |
| `--line` | `oklch(0.9 0.008 265)` | `oklch(0.33 0.015 265)` | borders |
| `--src` | `oklch(0.38 0.02 265)` | `oklch(0.82 0.012 265)` | inactive source text |
| `--kata` | `oklch(0.45 0.14 265)` | `oklch(0.8 0.1 265)` | katakana highlight |
| `--sent` | `oklch(0.9 0.05 265)` | `oklch(0.38 0.08 265)` | current-sentence highlight |
| `--hit` / `--hit-cur` | `oklch(0.92 0.08 85)` / `oklch(0.82 0.15 70)` | `oklch(0.38 0.06 85)` / `oklch(0.55 0.12 70)` | find matches |
| `--accent` | `#3d3fa6` | `#3d3fa6` | primary buttons (white text) |
| `--accent-text` | `var(--accent)` | `color-mix(in oklch, var(--accent) 45%, white)` | links, focus, active marks |
| `--accent-soft` / `--accent-ink` | `oklch(0.94 0.03 265)` / `oklch(0.38 0.12 265)` | `oklch(0.31 0.05 265)` / `oklch(0.88 0.06 265)` | pills, "Use" buttons, job strip |
| `--seal` | `oklch(0.52 0.16 30)` | `oklch(0.6 0.15 30)` | logo mark, unsaved dot |
| `--ok`, `--ok-soft`, `--ok-ink` | `0.45 0.1 160`, `0.93 0.04 160`, `0.35 0.08 160` | `0.78 0.11 160`, `0.31 0.05 160`, `0.87 0.08 160` | published, saved |
| `--warn-soft`, `--warn-ink` | `0.94 0.04 80`, `0.4 0.09 70` | `0.32 0.05 75`, `0.88 0.09 80` | scheduled, warnings |
| `--danger`, `--danger-soft` | `0.5 0.17 27`, `0.95 0.03 27` | `0.74 0.14 27`, `0.3 0.06 27` | errors |
| `--quiet-soft` | `oklch(0.94 0.005 265)` | `oklch(0.28 0.012 265)` | "Not published" badge |
| `--h0`…`--h4` | `0.93 0.008`, `0.86 0.05`, `0.74 0.1`, `0.58 0.14`, `0.4 0.14` (hue 265) | `0.27 0.012`, `0.37 0.06`, `0.5 0.1`, `0.64 0.12`, `0.8 0.1` | heatmap levels |
| `--shadow`, `--scrim` | `oklch(0.3 0.08 265 / .35)`, `oklch(0.22 0.02 265 / .45)` | `oklch(0 0 0 / .55)`, `oklch(0.05 0.01 265 / .62)` | elevation, dialog backdrop |

The accent is fixed. The canvas's accent switch was for exploring options, not a user setting.

Contrast: body and muted text meet 4.5:1 on `--bg` and `--surface` in both themes. Status
colours always come with a text label (badges say "Published", never only a colour).

### 3.2 Type

| Role | Face | Size |
|---|---|---|
| UI | Hanken Grotesk 400/500/600 | 15px base; 13px secondary; 12px uppercase labels (`.08em` tracking) |
| English translation and headings | Newsreader 400/500 | editor 20px; page titles 36px; section titles 22px |
| Japanese source | Noto Serif JP 400/500 | editor 17px, line-height 1.85 |
| Numbers, keys, URLs | IBM Plex Mono 400/500 | 12–14px |

The editor's existing font-size control (`--editor-font`) scales the source and translation
sizes together, as it does now.

Fonts are self-hosted through `@fontsource` packages (`@fontsource/hanken-grotesk`,
`@fontsource/newsreader`, `@fontsource/ibm-plex-mono`, `@fontsource/noto-serif-jp`), imported
in `main.tsx`. Self-hosting keeps the app working without access to Google and stops every
page load from contacting a third party. Noto Serif JP ships split by character range, so
the browser fetches only the pieces a chapter uses.

### 3.3 Shape and spacing

8px panel radius, 6px controls, 12px dialogs, 16px sheet top corners. Controls are 36px
tall on desktop (40px inputs) and 44px on narrow screens. Content max-width is 1360px with
32px gutters (16px below `60rem`).

### 3.4 Files

`styles.css` is replaced by `web/src/styles/`:

- `tokens.css`: §3.1, both themes
- `base.css`: element defaults, focus ring, `.visually-hidden`
- `controls.css`: button, input, select, checkbox, badge, pill, kbd, menu
- `shell.css`: header, nav, page header
- `editor.css`: cards, toolbar, find strip, side column, sheet
- `library.css`: rails, volume tables, job strip
- `dialogs.css`: dialog shell, result boxes

`main.tsx` imports them in this order. Each stays under ~300 lines. Class names follow what
already exists (`.card`, `.statusbar` becomes `.ebar`) and add only what the boards need.

## 4. Theme

- **Setting:** `ui_theme` in user settings, `"system" | "light" | "dark"`, default
  `"system"`. Settings are free-form keys (`PUT /settings`), so the API needs no change.
- **Applying:** a small `theme.ts` resolves the setting to `light` or `dark`. For `system`
  it follows `matchMedia('(prefers-color-scheme: dark)')` and listens for changes. It then
  sets `document.documentElement.dataset.theme` and `color-scheme`.
- **No flash:** the resolved value is mirrored in `localStorage` (`ta.theme`). A classic
  inline script in `index.html` sets `data-theme` from that before the bundle loads.
  Once `/settings` arrives, the stored value is corrected if it changed on another device.
  Signed-out pages (sign in, invite) use the stored value or the system setting.
- **Control:** a theme button in the header (half-circle icon plus the current choice)
  opens a menu with System, Light and Dark as radio items. Choosing one writes the setting
  and applies it at once.

## 5. App shell

The header keeps today's six nav links and order, with the current page marked by an
underline. Then the theme button, the signed-in email, and Sign out. The 訳 mark plus
"Translation Assistant" links to the library. Below `60rem` the nav scrolls sideways in
one row; it doesn't wrap into several.

Page headers: an optional breadcrumb, a 36px Newsreader title, an optional muted
subtitle, and the actions on the right, which wrap under the title on narrow screens.

## 6. Editor, desktop (`60rem` and wider)

### 6.1 Toolbar

`StatusBar` is replaced by an editor toolbar `.ebar`, sticky at `top: 0`, sitting directly
under the app header. The app header scrolls away; the toolbar stays.

- **Top line:** breadcrumb (Library / series / volume), the chapter title, then on the
  right: save state, **Find** (with its key shown), **View ▾**, **More ▾**, **Publish**.
- **Save state** shows Saved, Saving…, or Unsaved changes with the `--seal` dot. On error
  it becomes a `--danger-soft` box reading "Not saved: {error}" with a Retry button
  (today's `onRetry`).
- **Second line:** "Line n of N", a progress bar and percentage, word count, "Phrase i of
  k" while parsing, then, pushed right: "Spellcheck unavailable" (only when it is) and the
  Profile select (today's control).
- **View ▾** is a menu of checkboxes: Translation memory (`tm_visible`), Machine
  translation (`mt_visible`), Glossary in this line (`glossary_visible`, new, default
  true), then Collapse images (`images_collapsed`, only when the chapter has images),
  then Text size − / + (the same actions as the font shortcuts).
- **More ▾** holds Edit source, Split, and Series tools (only when the chapter belongs to
  a series). These are links, as today.
- **Publish** opens the existing `PublishDialog` for this document. This is new: today the
  dialog opens only from the library.

### 6.2 Find

`FindBar` renders as a strip attached to the bottom of the toolbar, inside the same sticky
element. Opening it makes the toolbar taller and never covers content. It keeps its current
behaviour (Enter, Shift+Enter, Escape, the `n/total` counter, wrap). It gains a short
hint ("Enter next · Shift+Enter previous · Esc closes") and icon buttons with the same
`aria-label`s. Matches use `--hit`, the current match `--hit-cur`.

### 6.3 Side column

- The layout is a two-column row: cards (`flex: 999 1 560px`) and the side column
  (`flex: 1 1 340px`, max 440px).
- The column is `position: sticky`, with `top` and `max-height` driven by
  `--sticky-h`. A `ResizeObserver` on `.ebar` writes that variable on `<html>`, so the
  offset follows the toolbar's real height, find open or closed and wrapped or not.
  Today's hard-coded `3rem` goes. The column scrolls on its own
  (`overflow-y: auto; overscroll-behavior: contain`).
- **Order:** Translation memory, Machine translation, Glossary in this line. Each is a
  panel whose header is a `<button aria-expanded>` with an uppercase label, a summary on
  the right (TM "1 match", MT "Line n", the glossary count), and a chevron. Clicking it
  folds the panel to its header. Folded panels are remembered in `localStorage`
  (`ta.panels.collapsed`) per browser; they're a layout preference, not account data.
  Hiding a panel completely is the View menu's job (§6.1).
- **MT panel:** today's `MtPanels` content, restyled. One section per service with its name and
  status ("done", "streaming…", "not set up"), the text, and a **Use** button. Ollama's
  Thinking stays a `<details>`. MeCab and JParser keep their word lists, with unmatched
  rows muted. The not-set-up state keeps its "Set up" link.
- **TM panel:** today's `TmPanel`, with the matched source above the stored translation,
  the match percentage, and Use.
- **Glossary in this line (new):** the current profile's glossary, fetched once with the
  existing `["glossary", profileId]` query. The panel lists the entries whose phrase occurs
  in the current line's raw source, in glossary order. Matching is a pure function in
  `editor/glossaryHits.ts`. Below the list, an "Edit glossary" link goes to
  `/settings/profiles?profile={id}`; `ProfilesPage` learns to select the profile named in
  that query parameter. With no profile, the panel says so and links to the profile
  picker in the toolbar.
- The active card's footer reads "{k} glossary terms in this line" when k > 0, plus the
  character count.

## 7. Editor, narrow screens (below `60rem`)

The side column is not rendered. In its place:

- **Toolbar** in one compact row: back arrow (to the series, else the library), the
  chapter title (one line, truncated), save state as text plus dot, Find (icon), ⋯ (More).
  On narrow screens the ⋯ menu holds the View items, Edit source, Split, Series tools and
  Publish.
- **Second row:** "Line n/N", progress, percentage, and an **Aids** pill. Its badge counts
  TM matches + MT services with a result + glossary hits for the current line, and updates
  as MT results stream in. The pill has `aria-label="Open translation aids, {n} results
  for line {line}"`.
- **Sheet:** Aids opens a bottom sheet: a `<dialog>` opened with `showModal()`, about 60% of
  the viewport (`min(60dvh, 520px)`), with a light backdrop, so the active card stays
  readable above it. Inside: a drag handle (drag down or tap the backdrop to close), a
  "Line n" heading, a Close button, and tabs Memory, MT and Glossary with counts
  (`role="tablist"`). The content is the same three panels' content.
- **Behaviour:**
  1. Opening the sheet blurs the CodeMirror input, so the on-screen keyboard closes.
  2. **Use** writes the text into the line (today's `useText`), closes the sheet and
     focuses the input again.
  3. The last tab is remembered in `localStorage` (`ta.aids.tab`). Moving to another line
     while the sheet is open (by the keyboard shortcuts) refreshes its content and keeps it
     open.
  4. Escape closes it (native dialog behaviour). Focus returns to the Aids pill unless
     Use closed it.
- The switch between column and sheet is a `matchMedia('(max-width: 60rem)')` hook, so
  only one of them is ever mounted and only one set of MT streams runs.

## 8. Other screens (restyle, same data)

- **Library:**
  - **Series list on the left:** a glyph tile (the title's first character on a
    cover colour picked from the series id), the title, "{v} volumes · {c} chapters", and a
    progress bar. All of it is computed client-side from `/documents` and `/series`. Then
    "No series" for loose documents, then the "Import…" link (today it sits in the picker's
    toolbar).
  - **Series header:** title, "{t} of {c} chapters translated · {p} published to
    WordPress", and actions: Fetch from Syosetu, Find & replace, Publish selected.
  - **Active job strip** in `--accent-soft`.
  - **Volumes:** sections with a table each: checkbox, number, title link, progress bar,
    WordPress badge (Published / Scheduled · date / Not published), and date edited.
    Selected rows get an accent tint. Collapsed volumes show a one-line summary.
- **Statistics:** three headline numbers, the heatmap on `--h0…4`, and the by-period
  table. The metric switch is a segmented control with `aria-pressed`.
- **Profiles:**
  - **Profile list on the left** with a "Default" pill. No term counts: the profile API
    doesn't return them, and they aren't worth an API change.
  - **Profile page:** title with Rename and Delete; parse characters in their own card;
    then the glossary card.
  - **Glossary card:** borderless inputs that show a border on hover and focus. Icon
    buttons for move up/down/remove keep their `aria-label`s. Changed rows get a left
    `--seal` marker. The header shows "{n} unsaved changes". The footer has Add row,
    Import CSV, **Discard** (new: resets the rows to the loaded glossary after a confirm)
    and Save glossary.
- **Machine translation:**
  - **Left card:** target language, then the panel list (checkbox, name, status badge,
    up/down).
  - **Right column:** a card each for DeepL, LibreTranslate and Ollama. Each shows its
    key or token state as a dot plus "Key saved …hint" or "No key saved". Ollama also has
    Model and System prompt, with Reset prompt.
- **WordPress:**
  - **Connection card:** endpoint URL, API key (with its hint), Save connection, Test
    connection, and the test result as a box.
  - **Publishing defaults card:** grouped under Chapter passwords and Schedule. The
    controls and labels stay as they are today.
- **Shortcuts:** grouped into Moving between lines, Phrases and tools, Insert characters,
  and Text size. Each row has the action, the key in `<kbd>`, and Change. While a key is
  being captured the row turns `--accent-soft` with a dashed key reading "Press a key…",
  and its button becomes Cancel. A changed binding shows a dot and a Reset button whose
  title names the default. A conflict appears as an alert above the groups.
- **Import:**
  - **TXT/CSV card:** a drop zone (new: accepts dragged files as well as the picker) that
    states the limits (500 files, 12 MB), the chosen-files list, the series choice,
    "Import {n} files", and the result box.
  - **EPUB card:** step 2 is laid out as series and volume title in a row, the four
    metadata fields in a grid, and the chapter checklist with character and image counts.
    Short pages start unchecked, as today. Then "Import {n} chapters · {m} unchecked".
- **Sign in / invite:** a centred card with the mark. Sign in adds the line "Accounts are by
  invitation. Ask the person who runs this server for a link." The invite form shows "At
  least 12 characters." under the password.

## 9. Behaviour added by this work

The canvas review kept these five extras; with the editor items they are the only
behavioural changes:

1. Import sits under the library's series list, not among a series' actions (§8).
2. Glossary **Discard** (§8).
3. **Batch publish:**
   - The subtitle names the chapter range.
   - The form shows "Last one goes out {date}", from `POST /wp/batch/preview` (§10).
   - The running view has **Cancel job** (`POST /jobs/{id}/cancel`, already used by
     `JobProgress`).
   - It says the job keeps running after the dialog closes and reopens from the library.
4. **Single publish:** when the previous chapter is still scheduled, the confirm button
   reads "Schedule anyway" if scheduling is on, else "Publish anyway". The result view
   adds a Copy button for the password (`navigator.clipboard.writeText`, with the field
   still selectable as a fallback).
5. **Sign in:** the invitation note (§8).

Editor additions: the glossary panel and the `glossary_visible` setting (§6.3), Publish
from the editor (§6.1), the phone sheet (§7), and the theme setting (§4).

## 10. API change

One endpoint, in `api/routers/wp.py`:

`POST /wp/batch/preview`, body `{start: datetime, count: int (1–500), chapters_per_day: int
(1–99), tz: str}`, returns `{slots: datetime[]}`.

It calls the existing `publish.batch_slots` with the user's `wp_default_schedule_time`, the
same way `POST /wp/batch` does, so the preview and the real run can't drift apart. It is
read-only and writes nothing. The client debounces it (300 ms) on start and per-day changes,
and shows the last slot in the browser's zone. Tests: the slots match what `/wp/batch`
assigns for the same input; an invalid `tz` is 422; count outside 1–500 is 422. Regenerate
`schema.d.ts` with `npm run gen:api`.

## 11. Testing

- **Vitest (pure modules):**
  - `theme.ts`: resolving system, light and dark, and following the media query.
  - `glossaryHits.ts`: overlapping phrases, a phrase that occurs twice, an empty glossary.
  - The Aids count.
  - The panel-collapse store.
- **pytest:** the preview endpoint (§10).
- **Playwright, existing specs.** Update these selectors and nothing else:
  - `source.spec.ts` uses the "Edit source" link: open **More ▾** first.
  - `tm.spec.ts` clicks Show/Hide TM: use the **View ▾** "Translation memory" checkbox.
  - `import.spec.ts` uses the "Import…" link. The link in the series list keeps that
    name, so the test stands.
  - `stats.spec.ts` matches `/Current streak: [1-9]\d* days/`. The headline number keeps
    an accessible name of that form (`aria-label` on the number), so the test stands.
  - `publish.spec.ts` matches "WP status: Not published". The dialog keeps that exact
    text as the badge's accessible name.
- **Playwright, new specs** (each owns its seed rows in `tools/e2e_seed.py`):
  - `theme.spec.ts`: choosing Dark persists across a reload and a fresh sign-in, with no
    light flash. Check `data-theme` on `<html>` at `domcontentloaded`.
  - `editor-narrow.spec.ts` at 390×844: open Aids, press Use on a stubbed MT result. The
    line holds the text, the sheet is closed, and the input has focus.
  - `editor-sticky.spec.ts`: scroll to the middle of a long chapter and open Find. The
    side column's top equals the toolbar's bottom (±1px).

## 12. Delivery

One spec, three plans, each leaving the app shippable:

- **7a, foundation:** tokens, fonts, the style files, theme setting and menu, app shell,
  and a restyle of Statistics, the settings pages, Import, Sign in and the dialogs, with
  the §9 extras that touch them.
- **7b, editor:** toolbar, View and More menus, find strip, sticky side column with
  folding, glossary panel, Publish from the editor, and the narrow-screen sheet.
- **7c, library and publishing:** Library restyle with the series list, batch-publish
  preview endpoint and UI, Cancel job, Copy password.

## 13. Out of scope

- Library and settings layouts designed for phones. They get the generic narrow-screen
  rules (stacked columns, nav that scrolls sideways, tables that scroll inside their box),
  but no dedicated design.
- The Edit source and Split pages beyond picking up the tokens.
- A user-chosen accent colour, cover images in the series list, and glossary term counts
  on profiles.
- Any change to keys, saving, MT streaming or job semantics.
