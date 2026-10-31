---
name: ta-web
description: A calm, self-hosted workplace for translating Japanese web novels line by line.
colors:
  ink-indigo: "#3d3fa6"
  soft-indigo-wash: "oklch(0.94 0.03 265)"
  deep-indigo-ink: "oklch(0.38 0.12 265)"
  seal-vermilion: "oklch(0.52 0.16 30)"
  page-grey: "oklch(0.975 0.004 255)"
  paper-surface: "oklch(0.995 0.002 255)"
  hover-raise: "oklch(0.985 0.004 255)"
  blue-black-ink: "oklch(0.22 0.02 265)"
  muted-slate: "oklch(0.46 0.02 265)"
  hairline: "oklch(0.9 0.008 265)"
  source-slate: "oklch(0.38 0.02 265)"
  katakana-indigo: "oklch(0.45 0.14 265)"
  sentence-wash: "oklch(0.9 0.05 265)"
  find-hit: "oklch(0.92 0.08 85)"
  find-current: "oklch(0.82 0.15 70)"
  ok-green: "oklch(0.45 0.1 160)"
  ok-wash: "oklch(0.93 0.04 160)"
  ok-ink: "oklch(0.35 0.08 160)"
  warn-wash: "oklch(0.94 0.04 80)"
  warn-ink: "oklch(0.4 0.09 70)"
  danger-red: "oklch(0.5 0.17 27)"
  danger-wash: "oklch(0.95 0.03 27)"
  quiet-wash: "oklch(0.94 0.005 265)"
  dark-page: "oklch(0.185 0.012 265)"
  dark-surface: "oklch(0.225 0.014 265)"
  dark-raise: "oklch(0.205 0.013 265)"
  dark-field: "oklch(0.195 0.012 265)"
  dark-ink: "oklch(0.93 0.008 265)"
  dark-muted: "oklch(0.73 0.015 265)"
  dark-line: "oklch(0.33 0.015 265)"
  dark-source: "oklch(0.82 0.012 265)"
  dark-accent-text: "color-mix(in oklch, #3d3fa6 45%, white)"
typography:
  display:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "36px"
    fontWeight: 500
    lineHeight: 1.15
  headline:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "22px"
    fontWeight: 500
    lineHeight: 1.25
  title:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "17px"
    fontWeight: 500
  body:
    fontFamily: "Hanken Grotesk, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Hanken Grotesk, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.5
    letterSpacing: "0.08em"
  translation:
    fontFamily: "Newsreader, Georgia, serif"
    fontSize: "18px"
    fontWeight: 400
  source:
    fontFamily: "Noto Serif JP, serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.85
  mono:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "14px"
    fontWeight: 400
rounded:
  mark: "3px"
  control: "6px"
  panel: "8px"
  dialog: "12px"
  pill: "99px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  gutter: "32px"
components:
  button:
    backgroundColor: "{colors.paper-surface}"
    textColor: "{colors.blue-black-ink}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "36px"
  button-primary:
    backgroundColor: "{colors.ink-indigo}"
    textColor: "#fff"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "36px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted-slate}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "36px"
  input:
    backgroundColor: "{colors.paper-surface}"
    textColor: "{colors.blue-black-ink}"
    rounded: "{rounded.control}"
    padding: "0 12px"
    height: "40px"
  panel:
    backgroundColor: "{colors.paper-surface}"
    rounded: "{rounded.panel}"
    padding: "20px 22px"
  badge:
    backgroundColor: "{colors.quiet-wash}"
    textColor: "{colors.muted-slate}"
    rounded: "{rounded.pill}"
    padding: "1px 9px"
  dialog:
    backgroundColor: "{colors.paper-surface}"
    textColor: "{colors.blue-black-ink}"
    rounded: "{rounded.dialog}"
    padding: "24px"
---

# Design System: ta-web

## Overview

**Creative North Star: "The Quiet Workshop"**

A calm room for long sessions of skilled work. The text being translated sits at the centre in print-like serifs, and the tools around it stay small, grey and soft-spoken until they are needed. Nothing moves or calls for attention without a reason, so the screen can hold hours of focus at a keyboard.

The chrome is dense without feeling tight: thin hairlines, cool neutrals carrying a trace of indigo, gently curved corners. Colour is rationed to one ink-like indigo for action and focus, one small vermilion seal, and quiet washes that name a state. Light and dark are equal citizens, both drawn from the same set of roles.

**Key Characteristics:**
- Serif for the text and page titles, sans for the tools, mono for numbers, keys and URLs.
- Cool, barely tinted neutrals, with depth mostly drawn by hairlines and tone.
- One accent and one seal. Status colours are washes paired with words.
- Soft, gently rounded controls, with almost no motion.

## Colors

A restrained, cool palette: indigo-tinted greys, one saturated indigo and a single warm vermilion note. `web/src/styles/tokens.css` is the full source, with dark values for every role.

### Primary
- **Ink Indigo** (`ink-indigo`): Primary buttons, with white text. The same value in both themes. In light it is also the link, focus and active-mark colour.
- **Soft Indigo Wash** and **Deep Indigo Ink** (`soft-indigo-wash`, `deep-indigo-ink`): Pills, pressed toggles and other gentle accent fills, always as a pair.

### Secondary
- **Seal Vermilion** (`seal-vermilion`): The logo mark, unsaved-change dots and, mixed in at 40%, kanji highlighting. Small marks only.

### Neutral
- **Page Grey** (`page-grey`): The page behind everything.
- **Paper Surface** (`paper-surface`): Header, panels, active cards, dialogs and input fields.
- **Hover Raise** (`hover-raise`): Hovered rows, cards and menu items.
- **Blue-Black Ink** (`blue-black-ink`): Text and active source text.
- **Muted Slate** (`muted-slate`): Secondary text, labels, quiet buttons.
- **Source Slate** (`source-slate`): Japanese source on inactive cards, a step quieter than ink.
- **Hairline** (`hairline`): Every border and divider.

### Tertiary
- **Reading marks** (`katakana-indigo`, `sentence-wash`, `find-hit`, `find-current`): Katakana, the current sentence, find matches and the current match, used only inside the editor's text.
- **Status washes** (`ok-*`, `warn-*`, `danger-*`, `quiet-wash`): Published or saved, scheduled or warning, errors, and not yet published.

### Named Rules
**The Token Only Rule.** Stylesheets name colours through `tokens.css` and never write a literal colour. The white text on primary buttons and the seal mark is the existing exception.

**The Rationed Seal Rule.** Vermilion marks small things: the logo and unsaved changes (dots and a thin edge on changed glossary rows). It is never a button, a background or a heading.

**The Word With The Colour Rule.** A status colour always comes with a text label, so a badge says "Published" and never relies on green alone.

## Typography

**Display Font:** Newsreader (with Georgia, serif)
**Body Font:** Hanken Grotesk (with system-ui, sans-serif)
**Label/Mono Font:** IBM Plex Mono (with ui-monospace, monospace)
**Japanese Font:** Noto Serif JP (with serif)

**Character:** A bookish serif pair for the novel's two languages, set against a plain grotesque that keeps the tools out of the text's way. All four faces are self-hosted, so no request leaves the server for fonts.

### Hierarchy
- **Display** (500, 36px, 1.15; 28px below 60rem): Page titles.
- **Headline** (500, 22px, 1.25): Section and panel titles; dialog titles run at 24px.
- **Title** (500, 17px): The chapter title in the editor's status bar.
- **Body** (400, 15px, 1.5): All interface text; secondary text at 13px and controls at 14px.
- **Label** (600, 12px, 0.08em, uppercase): Table headers and small section labels.
- **Translation** (400, 18px default, user-scaled): English on editor cards, and machine-translation and memory text.
- **Source** (400, 18px default, 1.85, user-scaled): Japanese on editor cards. Line height opens to 2.2 when generated readings show.
- **Mono** (400, 12-14px): Numbers, keys, line positions and raw source editing.

### Named Rules
**The Two Voices Rule.** Serif is the novel's voice and page titles; sans is the tool's voice. A control never speaks in serif, and translated text never speaks in sans.

**The Scales Together Rule.** The editor's font-size setting (`--editor-font`) scales source and translation as one, and card details are sized in `em` to follow.

## Layout

Content stops at 1360px with 32px gutters, falling to 16px below 60rem. Spacing follows a loose 4px rhythm, mostly 8, 12, 16 and 24px. The editor's cards sit in a 60rem column, beside an 18rem sticky aid column; a sticky status bar and find bar stay above them. The card list ends with 45vh of space, so the last line can reach the middle of the screen.

Below 60rem controls grow to 44px, the side column drops under the cards and the status bar stacks. The library bookshelf drops to two columns below 767px. Only the editor has a designed phone layout; other pages simply narrow.

## Elevation & Depth

Mostly flat. Hairlines and tone separate surfaces at rest, and shadows belong to things that sit above the page or hold the current focus. Shadows are soft and pulled in with a negative spread, tinted indigo in light and pure black in dark.

### Shadow Vocabulary
- **Active card** (`box-shadow: 0 10px 28px -14px var(--shadow)`): Lifts the one card being worked on.
- **Menu** (`box-shadow: 0 16px 40px -16px var(--shadow)`): Dropdown and spell-check menus.
- **Dialog** (`box-shadow: 0 24px 60px -20px var(--shadow)`): Modal dialogs, over a dimmed backdrop.
- **Floating control** (`box-shadow: 0 8px 24px -10px var(--shadow)`): Jump-back buttons, which float over the cards.
- **Pressed segment** (`box-shadow: 0 1px 2px var(--shadow)`): The selected option in a segmented toggle.

### Named Rules
**The Flat Until Focused Rule.** Panels, inactive cards and buttons in the page flow carry no shadow at rest; a hairline does that work. The sign-in card is the one floating exception.

## Shapes

Gently curved, never pill-soft on structural things: 6px for controls and covers, 8px for panels, cards and menus, 12px for dialogs. Full pills are kept for badges, tags and progress bars. The seal mark is nearly square at 3px, like a stamped seal. Borders are 1px hairlines throughout.

## Components

Soft and calm: gentle shapes and tints, with nothing sharp to look at during a long session.

### Buttons
- **Shape:** Gently curved (6px), 36px tall, 44px on narrow screens; 30px for the small size.
- **Default:** Paper surface, hairline border, ink text at weight 500.
- **Primary:** Ink Indigo with white text. Quiet buttons have no fill or border and muted text. Icon buttons are 36px square and muted.
- **Hover / Focus:** Hover darkens the border, or lifts a quiet or icon button's text to ink. Focus is a 2px accent outline, 2px away. State changes are instant.
- **Danger:** Red text, or a red fill when it is the dialog's primary action.

### Chips
- **Style:** Badges use a status wash with matching ink text. Pills use the indigo wash, both at 12px and weight 500.
- **State:** Status badges read Published, Scheduled or Not posted, each in words.

### Cards / Containers
- **Corner Style:** 8px; the chapter-end card uses 10px.
- **Background:** Paper Surface on Page Grey.
- **Shadow Strategy:** None at rest, per the Flat Until Focused Rule.
- **Border:** 1px hairline.
- **Internal Padding:** 20px 22px; panel headers 14px 16px.

### Inputs / Fields
- **Style:** 40px tall, 1px hairline, 6px corners, field colour one step apart from the surface in dark.
- **Focus:** Accent border with a 2px half-strength accent outline, 1px away.
- **Error / Disabled:** Find misses wash the field in danger; disabled controls drop to 50% opacity.

### Navigation
- **Style:** A 56px header on Paper Surface: seal mark and name, then 14px muted links, then the account area. The current link goes to ink at weight 500 with a 2px accent underline.
- **Settings:** Sections sit in a sidebar, which becomes a scrolling row below 60rem.
- **Narrow:** Header links wrap to their own scrolling row below 60rem.

### Editor Card
The signature component: one card per source line, Japanese above, English below. Inactive cards have no border or fill and show slate source text. Hover adds the raise tone. The active card gains Paper Surface, a half-strength accent border and the active shadow, and its source goes to full ink. Line numbers and the copy button stay small at the top right, with the copy button hidden until needed.

### Series Cover
A 2:3 cover at 6px corners. With no image, it falls back to the series title on an indigo wash.

## Do's and Don'ts

### Do:
- **Do** define every colour for both themes in `tokens.css` and use it by name.
- **Do** keep the two voices apart: Newsreader and Noto Serif JP for the novel's text, Hanken Grotesk for tools.
- **Do** use IBM Plex Mono for numbers, keys and URLs.
- **Do** build new containers from a hairline and Paper Surface at 8px corners.
- **Do** keep status colours as washes with a text label.
- **Do** honour `prefers-reduced-motion` for anything that animates.

### Don't:
- **Don't** use vermilion for buttons, backgrounds or headings.
- **Don't** add a second accent hue or let a user pick one; the accent is fixed.
- **Don't** add a shadow to a panel, inactive card or in-flow button.
- **Don't** load fonts from a third party; faces are self-hosted through `@fontsource`.
- **Don't** add transitions or decorative motion to the editor's cards or controls.
