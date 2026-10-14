# Phase 7a: Visual System, Theme and Simple Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the SPA one token-based visual system with light and dark themes, a System / Light / Dark switch saved to the account, and the redesigned Statistics, settings, Import, publish-dialog and sign-in screens.

**Architecture:** Colours, fonts and spacing live in CSS custom properties (`web/src/styles/tokens.css`). Every other stylesheet uses those properties, never literal colours. The theme is a `data-theme` attribute on `<html>`:
- An inline script in `index.html` paints it from `localStorage` before the bundle loads.
- `src/theme/theme.ts` owns the rules.
- The account's `ui_theme` setting wins once `/settings` arrives.

Screens keep their data and behaviour. Only markup, class names, three small additions (glossary Discard, the import drop zone, the "Schedule anyway" label) and one stats test locator change.

**Tech Stack:** React 19, react-router 8, TanStack Query 5, plain CSS (no framework), Vite 8, Vitest 5 (node environment, pure modules only), Playwright 1.64, `@fontsource` font packages.

**Spec:** `docs/superpowers/specs/2026-10-14-web-redesign-design.md`. This plan is delivery stage 7a (§12). Mockups: https://claude.ai/artifact/HVHMBMZS6utjpArPXVp3ZU

### Where this plan departs from the spec, and why

1. `localStorage["ta.theme"]` stores the *preference* (`system`/`light`/`dark`), not the resolved theme. Then a signed-out page with "System" still follows the OS. The spec's §4 says "resolved value".
2. `stats.spec.ts` changes one locator. Its `getByText(/Current streak: …/)` can't see an `aria-label`, so it becomes `getByRole("region", { name: /Current streak: … days/ })` (the spec promised the test would stand as is).
3. The import buttons keep the exact name **Import**, because `import.spec.ts` clicks `{ name: "Import", exact: true }`. The counts the spec puts in the button ("Import 4 files") sit beside it as text instead.
4. Page-specific styles get their own files (`stats.css`, `settings.css`, `import.css`, `auth.css`), all pulled in by `styles/index.css`. The spec lists only the shared files.
5. The Profiles page has no subtitle. The mockup's "Used by series that don't pick a profile of their own" describes a fallback the code was not checked for.

## Global Constraints

- Colours appear only in `web/src/styles/tokens.css`. Everywhere else uses `var(--token)`. The one exception is `#fff` text on `--accent` fills.
- Theme preference values are exactly `"system" | "light" | "dark"`. The user-settings key is `ui_theme`; the `localStorage` key is `ta.theme`. Unknown or missing values mean `"system"`.
- The narrow-screen breakpoint is `60rem` (`@media (max-width: 60rem)`).
- No backend changes in 7a: no Python, no migrations, no `schema.d.ts` regeneration.
- These accessible names are used by existing Playwright specs and must not change:
  - Sign in: "Email", "Password", button "Sign in".
  - Nav links: "Library", "Statistics", "Machine translation", "Shortcuts".
  - Profiles: heading "Glossary", "Add row", "Phrase N", "Translation N", "Move N up", "Save glossary", "Import CSV". The only `role="status"` on the Profiles page is the save/import note.
  - Machine translation: heading "Machine translation", "Show DeepL", "DeepL API key", "Save DeepL", test id `status-deepl` with text "Ready", and the key hint text (for example "…y:fx").
  - WordPress: "WordPress endpoint URL", "WordPress API key", "Save connection", "Test connection", and the text "Key saved".
  - Import: link "Import…", heading "Import", "Files to import", "New series title", "EPUB file", "Author", button "Import" (exact), the chapter text "{order}. {title}", the result text "Imported: N", and link "Open series".
  - Single publish: dialog "Publish to WordPress", the text "WP status: Not published", button "Publish" (exact), "Published!", "Close".
  - Batch publish: dialog "Publish / Schedule Chapters", the checkbox matching `/Schedule \(unchecked/`, buttons "Start" and "Close".
- `<dialog>` elements keep their native open/closed behaviour. `dialog:not([open]) { display: none; }` must win over any `display` set by a class.
- Commit messages end with the attribution trailer configured for the session.

## Review Focus

1. **Browser storage blocked or throwing** (private window, site data disabled): the app still loads and the theme falls back to System. Pinned by the `readPref` test in Task 1.
2. **A `ui_theme` value the client doesn't know** (typo, a later version's value, a number): it's treated as System, never as a crash or a blank theme. Pinned by the `parseThemePref` test in Task 1.
3. **The OS switches light/dark while the preference is System:** the page follows without a reload. Pinned by the `emulateMedia` test in Task 3.
4. **Phone width with long data** (long emails, profile names, wide tables, the 52-week heatmap): no sideways page scroll; wide content scrolls inside its own box. Pinned by `narrow.spec.ts` in Task 12.
5. **Files of the wrong type dropped on the import zone** (images, folders, `.txt.bak`): they're left out and named in a note, never uploaded. Pinned by the `acceptFiles` test in Task 9.

---

## File map

| File | Responsibility |
|---|---|
| `web/index.html` | inline theme script in `<head>` |
| `web/src/theme/theme.ts` | preference parsing, resolution, storage, applying, OS listener |
| `web/src/theme/useThemeSync.ts` | the account's `ui_theme` overrides the device copy |
| `web/src/theme/ThemeMenu.tsx` | header System / Light / Dark menu |
| `web/src/ui/Menu.tsx` | generic popover menu (reused by 7b's View and More menus) |
| `web/src/ui/PageHeader.tsx` | page title, breadcrumb, subtitle, actions |
| `web/src/ui/icons.tsx` | inline stroke icons (arrows, cross) |
| `web/src/fonts.ts` | `@fontsource` imports |
| `web/src/styles/*.css` | tokens, base, controls, shell, editor (carried over), dialogs, stats, settings, import, auth; `index.css` imports them in order |
| `web/src/settings/glossary.ts` | gains `changedRows`, `countChanges` |
| `web/src/settings/shortcutGroups.ts` | the Shortcuts page's sections |
| `web/src/library/drop.ts` | `acceptFiles` for the drop zone |
| `web/src/publish/label.ts` | `confirmLabel`, `statusTone` |
| `web/src/styles.css` | deleted (replaced by `styles/`) |

---

### Task 1: Theme rules and the no-flash script

**Files:**
- Create: `web/src/theme/theme.ts`
- Test: `web/src/theme/theme.test.ts`
- Modify: `web/index.html`, `web/src/main.tsx`

**Interfaces:**
- Produces:
  - `type ThemePref = "system" | "light" | "dark"` and `type Theme = "light" | "dark"`.
  - `THEME_KEY = "ta.theme"` and `THEME_PREFS: readonly ThemePref[]`.
  - `parseThemePref(value: unknown): ThemePref` and `resolveTheme(pref: ThemePref, systemDark: boolean): Theme`.
  - `readPref(storage: Pick<Storage, "getItem"> | null): ThemePref` and `storedPref(): ThemePref`.
  - `applyPref(pref: ThemePref): void` and `startTheme(): void`.

- [ ] **Step 1: Write the failing test**

`web/src/theme/theme.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { parseThemePref, readPref, resolveTheme, THEME_KEY } from "./theme";

describe("theme", () => {
  it("parses known preferences and treats anything else as system", () => {
    expect(parseThemePref("light")).toBe("light");
    expect(parseThemePref("dark")).toBe("dark");
    expect(parseThemePref("system")).toBe("system");
    for (const v of [undefined, null, "", "blue", "Dark", 1, true, {}]) expect(parseThemePref(v)).toBe("system");
  });

  it("resolves system from the OS and keeps explicit choices", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("reads the stored preference and survives missing or throwing storage", () => {
    expect(readPref({ getItem: (k: string) => (k === THEME_KEY ? "dark" : null) })).toBe("dark");
    expect(readPref({ getItem: () => null })).toBe("system");
    expect(readPref(null)).toBe("system");
    expect(readPref({ getItem: () => { throw new Error("SecurityError"); } })).toBe("system");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (in `web/`): `npx vitest run src/theme/theme.test.ts`
Expected: FAIL, `Failed to resolve import "./theme"`.

- [ ] **Step 3: Write the module**

`web/src/theme/theme.ts`:

```ts
export type ThemePref = "system" | "light" | "dark";
export type Theme = "light" | "dark";

/** localStorage key. index.html's inline script reads the same key before the bundle loads. */
export const THEME_KEY = "ta.theme";
export const THEME_PREFS: readonly ThemePref[] = ["system", "light", "dark"];

/** Any stored or server value to a preference; unknown values mean "system". */
export function parseThemePref(value: unknown): ThemePref {
  return value === "light" || value === "dark" ? value : "system";
}

export function resolveTheme(pref: ThemePref, systemDark: boolean): Theme {
  if (pref === "system") return systemDark ? "dark" : "light";
  return pref;
}

/** Storage can be missing or throw (private windows, blocked site data). */
export function readPref(storage: Pick<Storage, "getItem"> | null): ThemePref {
  try {
    return parseThemePref(storage?.getItem(THEME_KEY));
  } catch {
    return "system";
  }
}

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const darkQuery = () => window.matchMedia("(prefers-color-scheme: dark)");

export const storedPref = (): ThemePref => readPref(browserStorage());

/** Remember the preference on this device and paint it. */
export function applyPref(pref: ThemePref): void {
  try {
    browserStorage()?.setItem(THEME_KEY, pref);
  } catch {
    // Blocked storage: the theme still applies for this page load.
  }
  document.documentElement.dataset.theme = resolveTheme(pref, darkQuery().matches);
}

/** Paint the stored preference and follow the OS while it is "system". Call once at startup. */
export function startTheme(): void {
  applyPref(storedPref());
  darkQuery().addEventListener("change", () => applyPref(storedPref()));
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/theme/theme.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Paint before the bundle loads**

In `web/index.html`, add this inside `<head>` after the `<title>` line. It must stay a classic inline script, not a module, so it runs before first paint.

```html
    <script>
      // Paint the saved theme before the bundle loads (src/theme/theme.ts owns the rules).
      (function () {
        var pref = null;
        try { pref = localStorage.getItem("ta.theme"); } catch (e) {}
        var dark = pref === "dark" || (pref !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
        document.documentElement.dataset.theme = dark ? "dark" : "light";
      })();
    </script>
```

In `web/src/main.tsx`, add the import below the others and call it before `createRoot`:

```ts
import { startTheme } from "./theme/theme";
```

```ts
startTheme();

createRoot(document.getElementById("root")!).render(
```

- [ ] **Step 6: Check the build and the unit tests**

Run: `npm test && npm run build`
Expected: all Vitest files pass; `tsc --noEmit` and `vite build` succeed.

- [ ] **Step 7: Commit**

```bash
git add web/index.html web/src/main.tsx web/src/theme/theme.ts web/src/theme/theme.test.ts
git commit -m "feat(web): theme preference rules and pre-paint script"
```

---

### Task 2: Tokens, shared styles, fonts and the header

**Files:**
- Create: `web/src/styles/tokens.css`, `base.css`, `controls.css`, `shell.css`, `editor.css`, `dialogs.css`, `index.css`
- Create: `web/src/fonts.ts`
- Delete: `web/src/styles.css`
- Modify: `web/src/main.tsx`, `web/src/Shell.tsx`, `web/package.json` (via npm)

**Interfaces:**
- Consumes: nothing from Task 1 (the CSS keys off `html[data-theme]`, which Task 1 sets).
- Produces:
  - Every class and token named below. Later tasks use `.panel`, `.sec`, `.panel-head`, `.panel-msg`, `.label`, `.field`, `.hint`, `.check`, `.badge(.ok|.warn)`, `.pill`, `.dot(.ok|.seal)`, `.box(.ok|.warn|.danger)`, `.menu-root`, `.menu`, `.page-head`, `.page-actions`, `.crumbs`, `.with-rail`, `.rail`, `.rail-head`, `.rail-item`, `.rail-main`, `.table-scroll`, `.num`, `.mono`, `.dlg`, `.dlg-head`, `.dlg-body`, `.dlg-foot`.
  - Buttons by modifier class on `<button>`: `.primary`, `.quiet`, `.danger`, `.icon`, `.small`. `.btn` styles a link or label as a button.
  - Font variables: `--sans`, `--serif`, `--jp`, `--mono`.

- [ ] **Step 1: Install the fonts**

Run (in `web/`): `npm install @fontsource/hanken-grotesk@^5 @fontsource/newsreader@^5 @fontsource/ibm-plex-mono@^5 @fontsource/noto-serif-jp@^5`
Expected: four packages added to `dependencies` in `package.json`; `package-lock.json` updated.

`web/src/fonts.ts`:

```ts
// Self-hosted faces (spec §3.2): no request leaves the server for fonts.
import "@fontsource/hanken-grotesk/400.css";
import "@fontsource/hanken-grotesk/500.css";
import "@fontsource/hanken-grotesk/600.css";
import "@fontsource/newsreader/400.css";
import "@fontsource/newsreader/400-italic.css";
import "@fontsource/newsreader/500.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/noto-serif-jp/400.css";
import "@fontsource/noto-serif-jp/500.css";
```

- [ ] **Step 2: Write the tokens**

`web/src/styles/tokens.css`:

```css
/* Every colour in the app. Other stylesheets use these names only (spec §3.1). */
:root {
  --sans: "Hanken Grotesk", system-ui, sans-serif;
  --serif: "Newsreader", Georgia, serif;
  --jp: "Noto Serif JP", serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;

  --bg: oklch(0.975 0.004 255);
  --surface: oklch(0.995 0.002 255);
  --raised: oklch(0.985 0.004 255);
  --field: oklch(0.995 0.002 255);
  --ink: oklch(0.22 0.02 265);
  --muted: oklch(0.46 0.02 265);
  --line: oklch(0.9 0.008 265);
  --src: oklch(0.38 0.02 265);
  --kata: oklch(0.45 0.14 265);
  --sent: oklch(0.9 0.05 265);
  --hit: oklch(0.92 0.08 85);
  --hit-cur: oklch(0.82 0.15 70);
  --accent: #3d3fa6;
  --accent-text: var(--accent);
  --accent-soft: oklch(0.94 0.03 265);
  --accent-ink: oklch(0.38 0.12 265);
  --seal: oklch(0.52 0.16 30);
  --ok: oklch(0.45 0.1 160);
  --ok-soft: oklch(0.93 0.04 160);
  --ok-ink: oklch(0.35 0.08 160);
  --warn-soft: oklch(0.94 0.04 80);
  --warn-ink: oklch(0.4 0.09 70);
  --danger: oklch(0.5 0.17 27);
  --danger-soft: oklch(0.95 0.03 27);
  --quiet-soft: oklch(0.94 0.005 265);
  --h0: oklch(0.93 0.008 265);
  --h1: oklch(0.86 0.05 265);
  --h2: oklch(0.74 0.1 265);
  --h3: oklch(0.58 0.14 265);
  --h4: oklch(0.4 0.14 265);
  --shadow: oklch(0.3 0.08 265 / 0.35);
  --scrim: oklch(0.22 0.02 265 / 0.45);
}

:root[data-theme="dark"] {
  --bg: oklch(0.185 0.012 265);
  --surface: oklch(0.225 0.014 265);
  --raised: oklch(0.205 0.013 265);
  --field: oklch(0.195 0.012 265);
  --ink: oklch(0.93 0.008 265);
  --muted: oklch(0.73 0.015 265);
  --line: oklch(0.33 0.015 265);
  --src: oklch(0.82 0.012 265);
  --kata: oklch(0.8 0.1 265);
  --sent: oklch(0.38 0.08 265);
  --hit: oklch(0.38 0.06 85);
  --hit-cur: oklch(0.55 0.12 70);
  --accent-text: color-mix(in oklch, var(--accent) 45%, white);
  --accent-soft: oklch(0.31 0.05 265);
  --accent-ink: oklch(0.88 0.06 265);
  --seal: oklch(0.6 0.15 30);
  --ok: oklch(0.78 0.11 160);
  --ok-soft: oklch(0.31 0.05 160);
  --ok-ink: oklch(0.87 0.08 160);
  --warn-soft: oklch(0.32 0.05 75);
  --warn-ink: oklch(0.88 0.09 80);
  --danger: oklch(0.74 0.14 27);
  --danger-soft: oklch(0.3 0.06 27);
  --quiet-soft: oklch(0.28 0.012 265);
  --h0: oklch(0.27 0.012 265);
  --h1: oklch(0.37 0.06 265);
  --h2: oklch(0.5 0.1 265);
  --h3: oklch(0.64 0.12 265);
  --h4: oklch(0.8 0.1 265);
  --shadow: oklch(0 0 0 / 0.55);
  --scrim: oklch(0.05 0.01 265 / 0.62);
}
```

- [ ] **Step 3: Write base, controls, shell, dialogs**

`web/src/styles/base.css`:

```css
html { color-scheme: light; -webkit-text-size-adjust: 100%; }
html[data-theme="dark"] { color-scheme: dark; }
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; min-height: 100dvh; background: var(--bg); color: var(--ink);
  font-family: var(--sans); font-size: 15px; line-height: 1.5; }
h1, h2, h3 { margin: 0; font-weight: 600; }
p { margin: 0 0 8px; }
a { color: var(--accent-text); }
:focus-visible { outline: 2px solid var(--accent-text); outline-offset: 2px; }
main { max-width: 1360px; margin: 0 auto; padding: 32px 32px 64px; }
table { border-collapse: collapse; width: 100%; }
th { padding: 8px 12px; text-align: left; font-size: 12px; font-weight: 600; letter-spacing: .08em;
  text-transform: uppercase; color: var(--muted); }
td { padding: 10px 12px; border-top: 1px solid var(--line); vertical-align: middle; }
tr.selected td { background: color-mix(in oklch, var(--accent-soft) 60%, var(--surface)); }
td.num, th.num { text-align: right; font-family: var(--mono); font-size: 14px; }
.table-scroll { overflow-x: auto; max-width: 100%; }
.muted { color: var(--muted); }
.error { color: var(--danger); }
.mono { font-family: var(--mono); }
.stack { display: flex; flex-direction: column; gap: 12px; }
form.stack { max-width: 32rem; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 8px 0; }
.spacer { flex: 1; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
@media (max-width: 60rem) { main { padding: 20px 16px 48px; } }
```

`web/src/styles/controls.css`:

```css
button, .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  min-height: 36px; padding: 0 14px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--surface); color: var(--ink); font: inherit; font-size: 14px; font-weight: 500;
  line-height: 1.2; text-decoration: none; cursor: pointer; }
button:hover:not(:disabled), .btn:hover { border-color: var(--muted); }
button:disabled { opacity: .5; cursor: default; }
button.primary, .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
button.quiet, .btn.quiet { background: none; border-color: transparent; color: var(--muted); }
button.quiet:hover:not(:disabled), .btn.quiet:hover { color: var(--ink); border-color: transparent; }
button.danger { color: var(--danger); }
button.icon { width: 36px; padding: 0; border-color: transparent; background: none; color: var(--muted); }
button.icon:hover:not(:disabled) { background: var(--raised); color: var(--ink); border-color: transparent; }
button.small, .btn.small { min-height: 30px; padding: 0 10px; font-size: 13px; }
@media (max-width: 60rem) { button, .btn { min-height: 44px; } button.icon { width: 44px; } }

input:not([type="checkbox"], [type="radio"], [type="file"], [type="range"]), select, textarea {
  min-height: 40px; max-width: 100%; padding: 0 12px; border: 1px solid var(--line); border-radius: 6px;
  background: var(--field); color: var(--ink); font: inherit; }
textarea { padding: 10px 12px; line-height: 1.55; resize: vertical; }
input:focus-visible, select:focus-visible, textarea:focus-visible {
  outline: 2px solid color-mix(in oklch, var(--accent-text) 55%, transparent); outline-offset: 1px;
  border-color: var(--accent-text); }
input[type="checkbox"], input[type="radio"] { width: 16px; height: 16px; margin: 0; accent-color: var(--accent); }
progress { appearance: none; width: 100%; max-width: 420px; height: 6px; border: 0; border-radius: 99px;
  background: var(--line); overflow: hidden; }
progress::-webkit-progress-bar { background: var(--line); }
progress::-webkit-progress-value { background: var(--accent-text); border-radius: 99px; }
progress::-moz-progress-bar { background: var(--accent-text); border-radius: 99px; }

.field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.field > span:first-child { font-size: 13px; font-weight: 500; }
.hint { margin: 0; font-size: 13px; color: var(--muted); }
.check { display: flex; align-items: flex-start; gap: 10px; min-height: 28px; }
.check input { margin-top: 3px; flex: none; }

.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }
.panel.pad { padding: 20px 22px; }
.sec { display: flex; flex-direction: column; gap: 16px; padding: 20px 22px; }
.panel-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
  gap: 8px 12px; padding: 14px 16px; border-bottom: 1px solid var(--line); }
.sec h2, .panel-head h2 { font-family: var(--serif); font-weight: 500; font-size: 22px; line-height: 1.25; }
.panel-msg { margin: 0; padding: 12px 16px; }
.label, .sec h2.label, .panel-head h2.label { font-family: var(--sans); font-size: 12px; font-weight: 600;
  line-height: 1.5; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }

.badge { display: inline-block; padding: 1px 9px; border-radius: 99px; font-size: 12px; font-weight: 500;
  white-space: nowrap; background: var(--quiet-soft); color: var(--muted); }
.badge.ok { background: var(--ok-soft); color: var(--ok-ink); }
.badge.warn { background: var(--warn-soft); color: var(--warn-ink); }
.pill { display: inline-block; padding: 1px 8px; border-radius: 99px; font-size: 12px; font-weight: 500;
  background: var(--accent-soft); color: var(--accent-ink); }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--line); flex: none; }
.dot.ok { background: var(--ok); }
.dot.seal { background: var(--seal); }
.box { display: flex; align-items: flex-start; gap: 10px; margin: 0; padding: 10px 14px; border-radius: 6px; font-size: 14px; }
.box.ok { background: var(--ok-soft); color: var(--ok-ink); }
.box.warn { background: var(--warn-soft); color: var(--warn-ink); }
.box.danger { background: var(--danger-soft); color: var(--danger); }
kbd { display: inline-block; min-width: 28px; padding: 2px 8px; border: 1px solid var(--line); border-bottom-width: 2px;
  border-radius: 5px; background: var(--raised); font-family: var(--mono); font-size: 13px; text-align: center; white-space: nowrap; }

.menu-root { position: relative; display: inline-block; }
.menu { position: absolute; top: calc(100% + 6px); z-index: 20; min-width: 200px; padding: 6px;
  display: flex; flex-direction: column; background: var(--surface); border: 1px solid var(--line);
  border-radius: 8px; box-shadow: 0 16px 40px -16px var(--shadow); }
.menu-end { right: 0; }
.menu-start { left: 0; }
.menu [role^="menuitem"] { justify-content: flex-start; width: 100%; min-height: 40px; border: 0;
  background: none; color: var(--ink); font-weight: 400; }
.menu [role^="menuitem"]:hover, .menu [role^="menuitem"]:focus-visible { background: var(--raised); outline: none; }
.menu [role="menuitemradio"]::before { content: ""; width: 16px; flex: none; }
.menu [role="menuitemradio"][aria-checked="true"]::before { content: "✓"; color: var(--accent-text); }
```

`web/src/styles/shell.css`:

```css
.app-header { display: flex; flex-wrap: wrap; align-items: center; gap: 0 32px; min-height: 56px; padding: 0 32px;
  background: var(--surface); border-bottom: 1px solid var(--line); }
.brand { display: inline-flex; align-items: center; gap: 10px; color: var(--ink); font-weight: 600;
  letter-spacing: .01em; text-decoration: none; white-space: nowrap; }
.mark { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 3px;
  background: var(--seal); color: #fff; font-family: var(--jp); font-size: 16px; }
.app-header nav { display: flex; gap: 4px; flex: 1; min-width: 0; overflow-x: auto; scrollbar-width: none; }
.app-header nav a { padding: 16px 12px 14px; border-bottom: 2px solid transparent; color: var(--muted);
  font-size: 14px; text-decoration: none; white-space: nowrap; }
.app-header nav a:hover { color: var(--ink); }
.app-header nav a[aria-current="page"] { color: var(--ink); font-weight: 500; border-bottom-color: var(--accent-text); }
.who { display: flex; align-items: center; gap: 12px; min-width: 0; font-size: 14px; color: var(--muted); }
.who .email { max-width: 24ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.page-head { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.page-head > div:first-child { min-width: 0; }
.page-head h1 { font-family: var(--serif); font-weight: 500; font-size: 36px; line-height: 1.15; overflow-wrap: anywhere; }
.page-head p { margin: 4px 0 0; }
.page-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.crumbs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; font-size: 13px; color: var(--muted); }
.crumbs a { color: inherit; }

.with-rail { display: flex; flex-wrap: wrap; gap: 40px; align-items: flex-start; }
.rail { flex: 1 1 260px; max-width: 300px; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.rail-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rail ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.rail-item { width: 100%; justify-content: space-between; min-height: 52px; padding: 10px 14px;
  border-color: transparent; background: none; text-align: left; }
.rail-item:hover:not(:disabled) { background: var(--surface); border-color: transparent; }
.rail-item[aria-current="true"] { background: var(--surface); border-color: var(--line);
  box-shadow: 0 8px 22px -14px var(--shadow); }
.rail-item > span:first-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rail-main { flex: 999 1 560px; min-width: 0; display: flex; flex-direction: column; gap: 24px; }
.rail-main .page-head { margin-bottom: 0; }

@media (max-width: 60rem) {
  .app-header { gap: 0 12px; padding: 0 16px; }
  .app-header nav { order: 3; flex-basis: 100%; }
  .who .email { display: none; }
  .rail { max-width: none; }
  .page-head h1 { font-size: 28px; }
}
```

`web/src/styles/dialogs.css`:

```css
dialog { width: min(560px, calc(100vw - 32px)); max-height: calc(100dvh - 32px); padding: 24px;
  border: 1px solid var(--line); border-radius: 12px; background: var(--surface); color: var(--ink);
  box-shadow: 0 24px 60px -20px var(--shadow); }
dialog:not([open]) { display: none; }
dialog::backdrop { background: var(--scrim); }
.dlg-head { display: flex; flex-direction: column; gap: 4px; }
.dlg-head h2 { font-family: var(--serif); font-weight: 500; font-size: 24px; line-height: 1.25; overflow-wrap: anywhere; }
.dlg-head p { margin: 0; }
.dlg-body { display: flex; flex-direction: column; gap: 14px; padding: 16px 0; }
.dlg-body a { overflow-wrap: anywhere; }
.dlg-foot { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; padding-top: 16px; border-top: 1px solid var(--line); }
```

- [ ] **Step 4: Carry the editor rules onto tokens**

The editor layout is redesigned in 7b; here its existing rules move to `editor.css` with token colours and the new faces, nothing else.

`web/src/styles/editor.css`:

```css
/* The phase 3b editor rules on tokens. The layout redesign is phase 7b. */
.editor-page { font-size: var(--editor-font, 18px); }
.statusbar { position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center;
  padding: 8px 32px; font-size: 13px; color: var(--muted); background: color-mix(in oklch, var(--bg) 94%, transparent);
  border-bottom: 1px solid var(--line); }
.statusbar strong { color: var(--ink); font-family: var(--serif); font-weight: 500; font-size: 17px; }
.save-state { display: inline-block; min-width: 9em; }
.editor { max-width: 60rem; margin: 0 auto; padding: 1rem 1rem 45vh; }
.card { content-visibility: auto; contain-intrinsic-size: auto 6em; padding: .6em .8em; margin: .4em 0;
  border: 1px solid transparent; border-radius: 8px; cursor: pointer; }
.card:hover { background: var(--raised); }
.card.active { background: var(--surface); border-color: color-mix(in oklch, var(--accent-text) 45%, transparent);
  box-shadow: 0 10px 28px -14px var(--shadow); cursor: auto; }
.card-number { float: right; font-family: var(--mono); font-size: .7em; color: var(--muted); }
.source { margin: 0 0 .3em; font-family: var(--jp); line-height: 1.85; color: var(--src); }
.card.active .source { color: var(--ink); }
.translation { margin: 0; white-space: pre-wrap; font-family: var(--serif); }
.code-editor { font-family: var(--serif); }
.code-editor .cm-editor.cm-focused { outline: none; }
.code-editor .cm-content { font: inherit; padding: 0; caret-color: var(--accent-text); }
.code-editor .cm-cursor { border-left-color: var(--accent-text); }
.jp-katakana { color: var(--kata); }
.jp-kanji { color: color-mix(in oklch, var(--seal) 40%, currentColor); }
.jp-punct { opacity: .6; }
.sentence-current { background: var(--sent); border-radius: 2px; }
.find-current { background: var(--hit-cur); color: var(--ink); }
.misspelled { text-decoration: underline wavy var(--danger); text-decoration-skip-ink: none; }
.findbar { position: sticky; top: 2.4rem; z-index: 2; display: flex; gap: .4rem; align-items: center; max-width: 60rem;
  margin: 0 auto; padding: .3rem 1rem; background: var(--surface); border-bottom: 1px solid var(--line); }
.findbar input.notfound { background: var(--danger-soft); }
.spell-menu { position: fixed; z-index: 10; display: grid; min-width: 12rem; padding: .25rem; background: var(--surface);
  border: 1px solid var(--line); border-radius: 8px; box-shadow: 0 16px 40px -16px var(--shadow); }
.spell-menu button { justify-content: flex-start; min-height: 32px; border: 0; background: none; font-weight: 400; }
.spell-menu button:focus, .spell-menu button:hover { background: var(--raised); }
.image-card { margin: .6em 0; }
.image-card img { display: block; max-width: min(100%, 400px); margin: .4em auto; }
.source-editor { border: 1px solid var(--line); border-radius: 6px; padding: .5rem; font-family: var(--mono);
  max-height: 70vh; overflow: auto; background: var(--field); }
.editor-layout { display: flex; gap: 1rem; align-items: flex-start; justify-content: center; }
.editor-layout .editor { flex: 1; min-width: 0; }
.side-col { position: sticky; top: 3rem; width: 18rem; flex: none; font-size: .875rem; max-height: calc(100vh - 3.5rem); overflow-y: auto; }
.tm-panel { font-size: .875rem; padding: .5rem; }
.tm-panel h2 { font-size: .875rem; margin: 0 0 .4rem; }
.tm-panel ul { list-style: none; margin: 0; padding: 0; display: grid; gap: .5rem; }
.tm-panel button { display: block; width: 100%; padding: .4rem .5rem; text-align: left; font: inherit; font-family: var(--serif); }
.mt-panels { display: grid; gap: .5rem; padding: .5rem; }
.mt-card { min-height: 4rem; padding: .5rem .6rem; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }
.mt-card header { display: flex; justify-content: space-between; align-items: baseline; }
.mt-card h3 { font-size: .875rem; margin: 0; }
.mt-glyph { min-width: 3.5em; text-align: right; }
.mt-text { white-space: pre-wrap; margin: .3rem 0; font-family: var(--serif); font-size: 1rem; }
.mt-entries { list-style: none; margin: .3rem 0 0; padding: 0; max-height: 12rem; overflow-y: auto; }
.mt-entries li { padding: .1rem 0; }
.mt-entries li.muted { opacity: .55; }
@media (max-width: 60rem) {
  .editor-layout { flex-direction: column; }
  .side-col { position: static; width: auto; max-height: none; }
  .statusbar { padding: 8px 16px; }
}
```

`web/src/styles/index.css`:

```css
@import "./tokens.css";
@import "./base.css";
@import "./controls.css";
@import "./shell.css";
@import "./editor.css";
@import "./dialogs.css";
```

- [ ] **Step 5: Switch the entry point and the header**

Delete `web/src/styles.css`. In `web/src/main.tsx`, replace `import "./styles.css";` with:

```ts
import "./fonts";
import "./styles/index.css";
```

Replace `web/src/Shell.tsx` with:

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { api, call } from "./api/client";
import { forgetUserData, useMe } from "./auth/session";

/** The Library link stays marked inside a series, a chapter and the import page. */
const LIBRARY = /^\/($|series\/|documents\/|import$)/;

export default function Shell() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { pathname } = useLocation();
  const logout = useMutation({
    mutationFn: () => call(api.POST("/auth/logout")),
    onSuccess: () => {
      forgetUserData(queryClient);
      queryClient.setQueryData(["me"], null);
    },
  });
  return (
    <>
      <header className="app-header">
        <Link className="brand" to="/"><span className="mark" aria-hidden="true">訳</span>Translation Assistant</Link>
        <nav aria-label="Main">
          <Link to="/" aria-current={LIBRARY.test(pathname) ? "page" : undefined}>Library</Link>
          <NavLink to="/stats">Statistics</NavLink>
          <NavLink to="/settings/profiles">Profiles</NavLink>
          <NavLink to="/settings/mt">Machine translation</NavLink>
          <NavLink to="/settings/wp">WordPress</NavLink>
          <NavLink to="/settings/shortcuts">Shortcuts</NavLink>
        </nav>
        <div className="who">
          <span className="email">{me.data?.email}</span>
          <button type="button" className="quiet" onClick={() => logout.mutate()}>Sign out</button>
        </div>
      </header>
      <Outlet />
    </>
  );
}
```

- [ ] **Step 6: Verify nothing regressed**

Run (in `web/`): `npm test && npm run build`
Expected: Vitest passes; the build succeeds and `dist/assets/` contains `.woff2` files.

Run (Postgres up, venv active with the mecab extra, `ta_e2e` reset as in CLAUDE.md): `npm run e2e`
Expected: every existing spec passes; no selectors changed in this task.

Manual check: with `npm run dev` running, open the library, a chapter, and Statistics in light. Then run `localStorage.setItem("ta.theme","dark")` in the console and reload. Expected: dark backgrounds, readable text, no white panels left over.

- [ ] **Step 7: Commit**

```bash
git add web/package.json web/package-lock.json web/src/fonts.ts web/src/styles web/src/main.tsx web/src/Shell.tsx
git rm web/src/styles.css
git commit -m "feat(web): token-based styles, self-hosted fonts and the new header"
```

---

### Task 3: Menu, theme switch, page header

**Files:**
- Create: `web/src/ui/Menu.tsx`, `web/src/ui/PageHeader.tsx`, `web/src/theme/ThemeMenu.tsx`, `web/src/theme/useThemeSync.ts`
- Modify: `web/src/Shell.tsx`
- Test: `web/e2e/theme.spec.ts`

**Interfaces:**
- Consumes: `applyPref`, `parseThemePref`, `storedPref`, `THEME_PREFS`, `ThemePref` from Task 1; the `.menu*` classes from Task 2.
- Produces:
  - `Menu` (default export of `ui/Menu.tsx`), with props `{ label: ReactNode; buttonLabel?: string; align?: "start" | "end"; children: (close: () => void) => ReactNode }`.
  - `PageHeader` (default export of `ui/PageHeader.tsx`), with props `{ title: ReactNode; subtitle?: ReactNode; crumbs?: ReactNode; actions?: ReactNode }`.
  - `ThemeMenu` and `useThemeSync(): void`.

- [ ] **Step 1: Write the failing end-to-end test**

`web/e2e/theme.spec.ts`:

```ts
import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/stats"); // not "/", which may resume the last open chapter
}

const theme = (page: Page) => page.evaluate(() => document.documentElement.dataset.theme);

async function choose(page: Page, name: "System" | "Light" | "Dark") {
  await page.getByRole("button", { name: /^Theme: / }).click();
  const saved = page.waitForResponse((r) => r.url().endsWith("/settings") && r.request().method() === "PUT");
  await page.getByRole("menuitemradio", { name }).click();
  await saved;
}

test("the theme choice follows the account across reloads and sign-ins", async ({ page, browser, baseURL }) => {
  await signIn(page);
  await choose(page, "Dark");
  expect(await theme(page)).toBe("dark");
  await page.reload({ waitUntil: "domcontentloaded" });
  expect(await theme(page)).toBe("dark"); // painted by index.html's inline script, before the bundle

  const other = await browser.newContext({ baseURL, colorScheme: "light" });
  const fresh = await other.newPage();
  await signIn(fresh);
  await expect.poll(() => theme(fresh)).toBe("dark"); // from the account, not this device
  await choose(fresh, "System");
  expect(await theme(fresh)).toBe("light");
  await other.close();
});

test("with System chosen the page follows the OS without a reload", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("button", { name: "Theme: System" })).toBeVisible();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(() => theme(page)).toBe("dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect.poll(() => theme(page)).toBe("light");
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx playwright test e2e/theme.spec.ts`
Expected: FAIL. There's no button matching `/^Theme: /`.

- [ ] **Step 3: Write the menu, page header, theme menu and sync hook**

`web/src/ui/Menu.tsx`:

```tsx
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

const ITEMS = '[role^="menuitem"]';

/** A button that opens a popover menu. The caller renders the items (buttons with a menuitem role).
 *  On open the checked item (else the first) takes focus; arrow keys move; Escape closes and returns
 *  focus to the button; a press outside closes. */
export default function Menu({ label, buttonLabel, align = "end", children }: {
  label: ReactNode; buttonLabel?: string; align?: "start" | "end"; children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const id = useId();
  const items = () => [...(root.current?.querySelectorAll<HTMLElement>(ITEMS) ?? [])];
  useEffect(() => {
    if (!open) return;
    const list = items();
    (list.find((el) => el.getAttribute("aria-checked") === "true") ?? list[0])?.focus();
    const outside = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const close = () => {
    setOpen(false);
    button.current?.focus();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!open) return;
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const list = items();
    const at = list.indexOf(document.activeElement as HTMLElement);
    const step = e.key === "ArrowDown" ? 1 : -1;
    const next = at < 0 ? (step > 0 ? 0 : list.length - 1) : (at + step + list.length) % list.length;
    list[next]?.focus();
  };
  return (
    <div className="menu-root" ref={root} onKeyDown={onKeyDown}>
      <button ref={button} type="button" className="quiet" aria-haspopup="menu" aria-expanded={open}
        aria-controls={open ? id : undefined} aria-label={buttonLabel} onClick={() => setOpen((o) => !o)}>
        {label}
      </button>
      {open && <div className={`menu menu-${align}`} role="menu" id={id}>{children(close)}</div>}
    </div>
  );
}
```

`web/src/ui/PageHeader.tsx`:

```tsx
import type { ReactNode } from "react";

/** A page's title block (spec §5): optional breadcrumb, serif title, muted subtitle, actions on the right. */
export default function PageHeader({ title, subtitle, crumbs, actions }: {
  title: ReactNode; subtitle?: ReactNode; crumbs?: ReactNode; actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        {crumbs && <nav className="crumbs" aria-label="Breadcrumb">{crumbs}</nav>}
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
```

`web/src/theme/useThemeSync.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, call } from "../api/client";
import { applyPref, parseThemePref } from "./theme";

/** Once settings arrive, the account's ui_theme replaces this device's copy (another device may have changed it). */
export function useThemeSync(): void {
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const loaded = settings.isSuccess;
  const value = settings.data?.ui_theme;
  useEffect(() => {
    if (loaded) applyPref(parseThemePref(value));
  }, [loaded, value]);
}
```

`web/src/theme/ThemeMenu.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, call } from "../api/client";
import Menu from "../ui/Menu";
import { applyPref, parseThemePref, storedPref, THEME_PREFS, type ThemePref } from "./theme";

const LABEL: Record<ThemePref, string> = { system: "System", light: "Light", dark: "Dark" };

function Icon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 2.5v11a5.5 5.5 0 0 0 0-11z" fill="currentColor" />
    </svg>
  );
}

/** Header control: System / Light / Dark, saved to the account (ui_theme) and to this device. */
export default function ThemeMenu() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const pref = settings.isSuccess ? parseThemePref(settings.data.ui_theme) : storedPref();
  const save = useMutation({
    mutationFn: (p: ThemePref) => call(api.PUT("/settings", { body: { ui_theme: p } })),
    onSuccess: (data) => queryClient.setQueryData(["settings"], data),
    // A failed save: reload the account's value, which useThemeSync then paints.
    onError: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const choose = (p: ThemePref) => {
    applyPref(p);
    queryClient.setQueryData(["settings"], { ...settings.data, ui_theme: p });
    save.mutate(p);
  };
  return (
    <Menu label={<><Icon />{LABEL[pref]}</>} buttonLabel={`Theme: ${LABEL[pref]}`}>
      {(close) => THEME_PREFS.map((p) => (
        <button key={p} type="button" role="menuitemradio" aria-checked={p === pref}
          onClick={() => { choose(p); close(); }}>
          {LABEL[p]}
        </button>
      ))}
    </Menu>
  );
}
```

- [ ] **Step 4: Put the switch in the header**

In `web/src/Shell.tsx`, add the imports:

```tsx
import ThemeMenu from "./theme/ThemeMenu";
import { useThemeSync } from "./theme/useThemeSync";
```

Call the hook at the top of `Shell()`, right after `const { pathname } = useLocation();`:

```tsx
  useThemeSync();
```

and make `ThemeMenu` the first child of `<div className="who">`:

```tsx
        <div className="who">
          <ThemeMenu />
          <span className="email">{me.data?.email}</span>
```

- [ ] **Step 5: Run the end-to-end test to verify it passes**

Run: `npx playwright test e2e/theme.spec.ts`
Expected: PASS (2 tests).

Manual check: open the theme menu, then use ArrowDown/ArrowUp to move between items and Escape to close (focus returns to the button). Clicking outside closes it too.

- [ ] **Step 6: Run the whole suite**

Run: `npm test && npm run build && npm run e2e`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add web/src/ui web/src/theme web/src/Shell.tsx web/e2e/theme.spec.ts
git commit -m "feat(web): System/Light/Dark theme menu saved to the account"
```

---

### Task 4: Statistics

**Files:**
- Create: `web/src/styles/stats.css`
- Modify: `web/src/styles/index.css`, `web/src/stats/heatmap.ts`, `web/src/stats/Heatmap.tsx`, `web/src/stats/StatsPage.tsx`, `web/e2e/stats.spec.ts`

**Interfaces:**
- Consumes: `PageHeader` (Task 3); `.panel`, `.panel-head`, `.label`, `.table-scroll`, `td.num` (Task 2).
- Produces: `LEVELS` (replaces `COLORS`) from `stats/heatmap.ts`, and `.seg` (segmented control) in `stats.css`.

- [ ] **Step 1: Point the stats test at the new headline**

In `web/e2e/stats.spec.ts`, replace

```ts
  await expect(page.getByText(/Current streak: [1-9]\d* days/)).toBeVisible();
```

with

```ts
  await expect(page.getByRole("region", { name: /Current streak: [1-9]\d* days/ })).toBeVisible();
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx playwright test e2e/stats.spec.ts`
Expected: FAIL. There's no region named "Current streak: … days".

- [ ] **Step 3: Heatmap levels from tokens**

In `web/src/stats/heatmap.ts`, replace the `COLORS` line with:

```ts
/** Intensity levels; each is painted by the .heat-N classes in styles/stats.css (tokens --h0…--h4). */
export const LEVELS = [0, 1, 2, 3, 4] as const;
```

In `web/src/stats/Heatmap.tsx`:
- Change the import to `import { intensity, thresholds, weeks, type Metric } from "./heatmap";`.
- Add `className="heatmap"` to the `<svg>`.
- Remove the `fontSize="9" fill="#767676"` attributes from both `<text>` elements.
- Replace `fill={COLORS[intensity(d?.[metric] ?? 0, th)]}` with `className={`heat-${intensity(d?.[metric] ?? 0, th)}`}`.

- [ ] **Step 4: Rewrite the page**

Replace the body of `web/src/stats/StatsPage.tsx` from the `LABELS` constant down with:

```tsx
const LABELS: Record<Metric, string> = { paragraphs: "Paragraphs", chars: "Source chars", en_words: "EN words" };
const UNITS: Record<Metric, string> = { paragraphs: "paragraphs", chars: "source chars", en_words: "EN words" };
const n = (v: number) => v.toLocaleString();
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(0)}%`);
const trend = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "up" : "down");
const longDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "long" });

export default function StatsPage() {
  const queryClient = useQueryClient();
  const stats = useQuery({ queryKey: ["stats"], queryFn: () => call(api.GET("/stats", { params: { query: { tz: browserZone() } } })) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const saveMetric = useMutation({
    mutationFn: (m: Metric) => call(api.PUT("/settings", { body: { stats_metric: m } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const [days, setDays] = useState(30);
  const [picked, setPicked] = useState("");
  const stored = settings.data?.stats_metric;
  const metric: Metric = METRICS.includes(stored as Metric) ? (stored as Metric) : "paragraphs";
  if (stats.isPending) return <main><p className="muted">Loading…</p></main>;
  if (stats.isError) return <main><p className="error" role="alert">{stats.error.message}</p></main>;
  const s = stats.data;
  const comp = s.comparisons[metric];
  const best = s.daily.reduce<typeof s.daily[number] | null>((b, d) => (!b || d[metric] > b[metric] ? d : b), null);
  const cutoff = new Date(`${s.today}T00:00:00Z`);
  cutoff.setUTCDate(cutoff.getUTCDate() - (days - 1));
  const recent = s.daily.filter((d) => d.date >= cutoff.toISOString().slice(0, 10)).reverse();
  const periods = [[`Today (${longDate(s.today)})`, "today"], ["Last 7 days", "week"], ["Last 30 days", "month"], ["All time", "alltime"]] as const;
  const avg = comp.daily_avg_30;
  const avgText = avg < 10 ? avg.toFixed(1) : n(Math.round(avg));
  const { current_streak: streak, longest_streak: longest } = s.streaks;
  return (
    <main className="stats">
      <PageHeader title="Statistics" actions={
        <div className="seg" role="group" aria-label="Metric">
          {METRICS.map((m) => (
            <button key={m} type="button" aria-pressed={m === metric} onClick={() => saveMetric.mutate(m)}>{LABELS[m]}</button>
          ))}
        </div>
      } />
      {saveMetric.error && <p className="error" role="alert">{saveMetric.error.message}</p>}

      <div className="kpis">
        <section className="panel kpi" aria-label={`Current streak: ${streak} days`}>
          <span className="label">Current streak</span><b>{streak} days</b><span className="muted">Longest: {longest} days</span>
        </section>
        <section className="panel kpi" aria-label={`Daily average over 30 days: ${avgText} ${UNITS[metric]}`}>
          <span className="label">Daily average, 30 days</span><b>{avgText}</b><span className="muted">{UNITS[metric]} per day</span>
        </section>
        {best && best[metric] > 0 && (
          <section className="panel kpi" aria-label={`Best day: ${n(best[metric])} ${UNITS[metric]} on ${longDate(best.date)}`}>
            <span className="label">Best day</span><b>{n(best[metric])}</b>
            <span className="muted">{UNITS[metric]} · {longDate(best.date)}</span>
          </section>
        )}
      </div>

      <section className="panel pad" aria-labelledby="heat-h">
        <div className="heat-head">
          <h2 id="heat-h" className="label">Translated per day, last 52 weeks</h2>
          <span className="legend" aria-hidden="true">Less {LEVELS.map((l) => <i key={l} className={`swatch heat-${l}`} />)} More</span>
        </div>
        <div className="table-scroll"><Heatmap today={s.today} daily={s.daily} metric={metric} onPick={setPicked} /></div>
      </section>

      <section className="panel" aria-labelledby="period-h">
        <div className="panel-head"><h2 id="period-h" className="label">By period</h2></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Period</th><th className="num">Paragraphs</th><th className="num">Source chars</th><th className="num">EN words</th><th className="num">vs previous</th></tr></thead>
            <tbody>
              {periods.map(([label, key]) => {
                const change = key === "alltime" ? null : comp.periods[key]?.pct_change;
                return (
                  <tr key={key}>
                    <td>{label}</td><td className="num">{n(s.summary[key].paragraphs)}</td><td className="num">{n(s.summary[key].chars)}</td>
                    <td className="num">{n(s.summary[key].en_words)}</td><td className={`num ${trend(change)}`}>{pct(change)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="days-h">
        <div className="panel-head">
          <h2 id="days-h" className="label">Last {days} days</h2>
          <button type="button" className="small" onClick={() => setDays(days === 30 ? 7 : 30)}>{days === 30 ? "Show last 7 days" : "Show last 30 days"}</button>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Date</th><th className="num">Paragraphs</th><th className="num">Source chars</th><th className="num">EN words</th></tr></thead>
            <tbody>
              {recent.map((d) => (
                <tr key={d.date} aria-current={d.date === picked ? "date" : undefined} className={d.date === picked ? "selected" : ""}>
                  <td>{longDate(d.date)}</td><td className="num">{n(d.paragraphs)}</td><td className="num">{n(d.chars)}</td><td className="num">{n(d.en_words)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="series-h">
        <div className="panel-head"><h2 id="series-h" className="label">By series</h2></div>
        {s.series.length ? (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Series</th><th className="num">Paragraphs</th><th className="num">Source chars</th><th className="num">EN words</th><th className="num">Chapters</th></tr></thead>
              <tbody>
                {s.series.map((r) => (
                  <tr key={r.series_id}><td>{r.series}</td><td className="num">{n(r.paragraphs)}</td><td className="num">{n(r.chars)}</td><td className="num">{n(r.en_words)}</td><td className="num">{r.chapters}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted panel-msg">No series data yet.</p>}
      </section>
    </main>
  );
}
```

Update the imports at the top of the file:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import { browserZone } from "../time";
import PageHeader from "../ui/PageHeader";
import Heatmap from "./Heatmap";
import { LEVELS, METRICS, type Metric } from "./heatmap";
```

- [ ] **Step 5: Add the page styles**

`web/src/styles/stats.css`:

```css
.stats { display: flex; flex-direction: column; gap: 24px; }
.stats .page-head { margin-bottom: 0; }
.seg { display: inline-flex; gap: 2px; padding: 3px; border-radius: 8px; background: color-mix(in oklch, var(--line) 60%, var(--bg)); }
.seg button { min-height: 32px; border: 0; background: none; color: var(--muted); font-weight: 400; }
.seg button[aria-pressed="true"] { background: var(--surface); color: var(--ink); font-weight: 500; box-shadow: 0 1px 2px var(--shadow); }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); gap: 16px; }
.kpi { display: flex; flex-direction: column; gap: 2px; padding: 18px 20px; }
.kpi b { font-family: var(--serif); font-weight: 500; font-size: 40px; line-height: 1.15; }
.heat-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 12px; }
.legend { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--muted); }
.swatch { display: inline-block; width: 13px; height: 13px; border-radius: 3px; }
.heatmap text { fill: var(--muted); font-size: 9px; }
.heatmap rect { rx: 2px; }
.heat-0 { fill: var(--h0); background: var(--h0); }
.heat-1 { fill: var(--h1); background: var(--h1); }
.heat-2 { fill: var(--h2); background: var(--h2); }
.heat-3 { fill: var(--h3); background: var(--h3); }
.heat-4 { fill: var(--h4); background: var(--h4); }
.up { color: var(--ok); }
.down { color: var(--danger); }
```

Append to `web/src/styles/index.css`:

```css
@import "./stats.css";
```

- [ ] **Step 6: Verify**

Run: `npm test && npm run build && npx playwright test e2e/stats.spec.ts`
Expected: Vitest passes (including `heatmap.test.ts`, which doesn't use `COLORS`); build succeeds; the stats spec passes.

Manual check: the metric switch saves and the heatmap recolours; in dark the heatmap's empty cells are dark, not white.

- [ ] **Step 7: Commit**

```bash
git add web/src/stats web/src/styles/stats.css web/src/styles/index.css web/e2e/stats.spec.ts
git commit -m "feat(web): restyle Statistics with headline numbers and token heatmap"
```

---

### Task 5: Profiles and glossary Discard

**Files:**
- Create: `web/src/ui/icons.tsx`, `web/src/styles/settings.css`
- Modify: `web/src/settings/glossary.ts`, `web/src/settings/glossary.test.ts`, `web/src/settings/GlossaryTable.tsx`, `web/src/settings/ProfilesPage.tsx`, `web/src/styles/index.css`, `web/e2e/profiles.spec.ts`

**Interfaces:**
- Consumes: `PageHeader` (Task 3); `.with-rail`, `.rail*`, `.panel*`, `.field`, `.hint`, `.dot`, `.pill` (Task 2).
- Produces:
  - `changedRows(rows: Row[], loaded: Row[]): Set<number>` and `countChanges(rows: Row[], loaded: Row[]): number`.
  - `ArrowUp`, `ArrowDown` and `Cross` from `ui/icons.tsx`, each `() => JSX.Element`, 16px and `aria-hidden`.
  - Classes in `settings.css`: `.settings`, `.cols`, `.sec-head`, `.inline-form`, `.row-fields`, `.panel-foot`, `.file-btn`.

- [ ] **Step 1: Write the failing unit tests**

Append inside the `describe("glossary rows", …)` block of `web/src/settings/glossary.test.ts`, and change the import to `import { changedRows, countChanges, moveRow, toEntries } from "./glossary";`:

```ts
  it("marks rows that differ from the loaded glossary at the same position", () => {
    const loaded = [r("a", "x"), r("b", "y")];
    expect([...changedRows(loaded, loaded)]).toEqual([]);
    expect([...changedRows([r("a", "x"), r("b", "z")], loaded)]).toEqual([1]);
    expect([...changedRows([r("b", "y"), r("a", "x")], loaded)]).toEqual([0, 1]);
    expect([...changedRows([...loaded, r("")], loaded)]).toEqual([2]);
  });
  it("counts changed and added rows plus rows removed", () => {
    const loaded = [r("a"), r("b"), r("c")];
    expect(countChanges(loaded, loaded)).toBe(0);
    expect(countChanges([r("a")], loaded)).toBe(2);
    expect(countChanges([r("b"), r("c")], loaded)).toBe(3);
    expect(countChanges([...loaded, r("d")], loaded)).toBe(1);
  });
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx vitest run src/settings/glossary.test.ts`
Expected: FAIL, `changedRows is not a function` (or a missing export).

- [ ] **Step 3: Implement**

Append to `web/src/settings/glossary.ts`:

```ts
/** Positions in `rows` whose phrase or translation differs from the loaded glossary at the same position. */
export function changedRows(rows: Row[], loaded: Row[]): Set<number> {
  const out = new Set<number>();
  rows.forEach((row, i) => {
    const was = loaded[i];
    if (!was || was.phrase !== row.phrase || was.translation !== row.translation) out.add(i);
  });
  return out;
}

/** The "{n} unsaved changes" count: changed or added rows, plus rows removed from the end. */
export const countChanges = (rows: Row[], loaded: Row[]) =>
  changedRows(rows, loaded).size + Math.max(0, loaded.length - rows.length);
```

Run: `npx vitest run src/settings/glossary.test.ts`
Expected: PASS.

- [ ] **Step 4: Write the failing end-to-end test for Discard**

Append to `web/e2e/profiles.spec.ts`:

```ts
test("Discard puts the glossary back after a confirm", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.goto("/settings/profiles");
  await expect(page.getByRole("button", { name: "Add row" })).toBeVisible(); // the glossary has loaded
  const phrases = page.getByRole("textbox", { name: /^Phrase \d+$/ });
  const before = await phrases.count();
  await page.getByRole("button", { name: "Add row" }).click();
  const added = page.getByLabel(`Phrase ${before + 1}`, { exact: true });
  await added.fill("to be discarded");
  await expect(page.getByText("1 unsaved change", { exact: true })).toBeVisible();

  page.once("dialog", (d) => void d.dismiss());
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(added).toHaveValue("to be discarded");

  page.once("dialog", (d) => void d.accept());
  await page.getByRole("button", { name: "Discard" }).click();
  await expect(phrases).toHaveCount(before);
  await expect(page.getByText(/unsaved change/)).toHaveCount(0);
});
```

Run: `npx playwright test e2e/profiles.spec.ts`
Expected: the new test FAILS (no "Discard" button); the first test still passes.

- [ ] **Step 5: Icons**

`web/src/ui/icons.tsx`:

```tsx
const box = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor",
  strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;

export const ArrowUp = () => <svg {...box}><path d="M8 13V3M4 7l4-4 4 4" /></svg>;
export const ArrowDown = () => <svg {...box}><path d="M8 3v10M4 9l4 4 4-4" /></svg>;
export const Cross = () => <svg {...box}><path d="M4 4l8 8M12 4l-8 8" /></svg>;
```

- [ ] **Step 6: Rewrite the glossary table**

Replace `web/src/settings/GlossaryTable.tsx` with:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, ApiError, call, errorMessage } from "../api/client";
import { ArrowDown, ArrowUp, Cross } from "../ui/icons";
import { changedRows, countChanges, moveRow, toEntries, type Row } from "./glossary";

/** Editable glossary for one profile (desktop dlg_glossary). Keyed by the parent on profile + data version. */
type Props = { pid: number; loaded: Row[]; onLoaded: (rows: Row[]) => void; onDirty: (d: boolean) => void; note: string | null; setNote: (n: string | null) => void };

const Heading = () => <h2 id="glossary-h">Glossary</h2>;

function Editor({ pid, loaded, onLoaded, onDirty, note, setNote }: Props) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<Row[]>(loaded);
  const dirty = JSON.stringify(rows) !== JSON.stringify(loaded);
  const changed = changedRows(rows, loaded);
  const changes = countChanges(rows, loaded);
  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);
  const written = () => queryClient.invalidateQueries({ queryKey: ["document"] });
  const save = useMutation({
    mutationFn: () =>
      call(api.PUT("/profiles/{profile_id}/glossary", { params: { path: { profile_id: pid } }, body: { entries: toEntries(rows) } })),
    onSuccess: (data) => {
      onLoaded(data.map(({ phrase, translation }) => ({ phrase, translation })));
      setNote("Saved");
      written();
    },
    onError: () => setNote(null),
  });
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`/api/profiles/${pid}/glossary/import`, { method: "POST", body });
      if (!res.ok) throw new ApiError(res.status, errorMessage(await res.json().catch(() => null)));
      return (await res.json()) as { added: number; updated: number; skipped: number };
    },
    onSuccess: (r) => {
      setNote(`Imported: ${r.added} added, ${r.updated} updated, ${r.skipped} skipped`);
      queryClient.invalidateQueries({ queryKey: ["glossary", pid] });
      written();
    },
    onError: () => setNote(null),
  });
  const edit = (i: number, patch: Partial<Row>) => setRows(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const discard = () => {
    if (!window.confirm("Discard unsaved glossary edits?")) return;
    setRows(loaded);
    setNote(null);
  };
  const error = save.error?.message ?? upload.error?.message;
  return (
    <section className="panel glossary" aria-labelledby="glossary-h">
      <div className="panel-head">
        <div className="title-row"><Heading /><span className="muted">{loaded.length} terms</span></div>
        {changes > 0 && (
          <span className="unsaved" aria-live="polite">
            <span className="dot seal" aria-hidden="true" />{changes} unsaved {changes === 1 ? "change" : "changes"}
          </span>
        )}
      </div>
      {error && <p className="error panel-msg" role="alert">{error}</p>}
      {note && <p className="panel-msg" role="status">{note}</p>}
      <div className="table-scroll">
        <table className="glossary-table">
          <thead><tr><th>Phrase</th><th>Translation</th><th><span className="visually-hidden">Row actions</span></th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={changed.has(i) ? "changed" : undefined}>
                <td><input className="jp" lang="ja" aria-label={`Phrase ${i + 1}`} value={r.phrase} onChange={(e) => edit(i, { phrase: e.target.value })} /></td>
                <td><input className="en" aria-label={`Translation ${i + 1}`} value={r.translation} onChange={(e) => edit(i, { translation: e.target.value })} /></td>
                <td className="row-actions">
                  <button type="button" className="icon" aria-label={`Move ${i + 1} up`} disabled={i === 0} onClick={() => setRows(moveRow(rows, i, -1))}><ArrowUp /></button>
                  <button type="button" className="icon" aria-label={`Move ${i + 1} down`} disabled={i === rows.length - 1} onClick={() => setRows(moveRow(rows, i, 1))}><ArrowDown /></button>
                  <button type="button" className="icon" aria-label={`Remove ${i + 1}`} onClick={() => setRows(rows.filter((_, k) => k !== i))}><Cross /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel-foot">
        <button type="button" onClick={() => setRows([...rows, { phrase: "", translation: "" }])}>Add row</button>
        <label className="btn file-btn">
          Import CSV
          <input type="file" accept=".csv,text/csv" aria-label="Import CSV" className="visually-hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file && (!dirty || window.confirm("Discard unsaved glossary edits?"))) upload.mutate(file);
            }} />
        </label>
        <span className="spacer" />
        <button type="button" className="quiet" disabled={!dirty} onClick={discard}>Discard</button>
        <button type="button" className="primary" onClick={() => save.mutate()} disabled={save.isPending || !dirty}>Save glossary</button>
      </div>
    </section>
  );
}

export default function GlossaryTable({ pid, onDirty }: { pid: number; onDirty: (d: boolean) => void }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState<string | null>(null); // outlives Editor remounts on data change
  const glossary = useQuery({
    queryKey: ["glossary", pid],
    queryFn: () => call(api.GET("/profiles/{profile_id}/glossary", { params: { path: { profile_id: pid } } })),
  });
  if (!glossary.data) {
    return (
      <section className="panel glossary" aria-labelledby="glossary-h">
        <div className="panel-head"><Heading /></div>
        {glossary.error
          ? <p className="error panel-msg" role="alert">{glossary.error.message}</p>
          : <p className="muted panel-msg">Loading…</p>}
      </section>
    );
  }
  const loaded = glossary.data.map(({ phrase, translation }) => ({ phrase, translation }));
  return (
    <Editor
      key={`${pid}:${glossary.dataUpdatedAt}`}
      pid={pid}
      loaded={loaded}
      onDirty={onDirty}
      note={note}
      setNote={setNote}
      onLoaded={(rows) => queryClient.setQueryData(["glossary", pid], rows.map((r, i) => ({ ...r, id: i, sort_order: i })))}
    />
  );
}
```

- [ ] **Step 7: Rewrite the Profiles page**

In `web/src/settings/ProfilesPage.tsx`, add `import PageHeader from "../ui/PageHeader";` to the imports. Keep everything up to and including `const error = …`, then replace the `return (…)` with:

```tsx
  const newProfile = () => {
    if (!discardOk()) return;
    const name = window.prompt("Profile name");
    if (name?.trim()) create.mutate(name.trim());
  };
  return (
    <main className="with-rail">
      <aside className="rail" aria-label="Profiles">
        <div className="rail-head">
          <h2 className="label">Profiles</h2>
          <button type="button" onClick={newProfile}>New profile</button>
        </div>
        <ul>
          {list.map((p) => (
            <li key={p.id}>
              <button type="button" className="rail-item" aria-current={current?.id === p.id ? "true" : undefined}
                onClick={() => { if (p.id !== current?.id && discardOk()) setChosen(p.id); }}>
                <span>{p.name}</span>{p.is_default && <span className="pill">Default</span>}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <div className="rail-main">
        {error && <p className="error" role="alert">{error}</p>}
        {current && (
          <>
            <PageHeader title={current.name} actions={<>
              <button type="button" onClick={() => { const name = window.prompt("New name", current.name); if (name?.trim()) patch.mutate({ name: name.trim() }); }}>Rename</button>
              <button type="button" className="danger" onClick={() => { if (window.confirm(`Delete profile "${current.name}"?`) && discardOk()) remove.mutate(); }}>Delete</button>
            </>} />
            <form
              key={`${current.id}:${current.parse_chars}`}
              className="panel sec parse-form"
              onSubmit={(e) => {
                e.preventDefault();
                patch.mutate({ parse_chars: new FormData(e.currentTarget).get("parse_chars") as string });
              }}
            >
              <label className="field">
                <span>Parse characters</span>
                <input name="parse_chars" className="mono" defaultValue={current.parse_chars} aria-describedby="parse-hint" />
              </label>
              <button type="submit" disabled={patch.isPending}>Save</button>
              <p id="parse-hint" className="hint">Characters that end a phrase for Next phrase and Previous phrase.</p>
            </form>
            <GlossaryTable pid={current.id} onDirty={setDirty} />
          </>
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 8: Settings styles**

`web/src/styles/settings.css`:

```css
/* Profiles, Machine translation, WordPress, Shortcuts. */
.settings { display: flex; flex-direction: column; gap: 24px; }
.settings .page-head { margin-bottom: 0; }
.cols { display: flex; flex-wrap: wrap; gap: 24px; align-items: flex-start; }
.cols > * { flex: 1 1 440px; min-width: 0; }
.sec-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 8px; }
.inline-form { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; }
.inline-form .grow { flex: 1 1 280px; }
.row-fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: 12px; }
.panel-foot { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 14px 16px; border-top: 1px solid var(--line); }
.file-btn { position: relative; }
.file-btn:focus-within { outline: 2px solid var(--accent-text); outline-offset: 2px; }

.parse-form { flex-direction: row; flex-wrap: wrap; align-items: flex-end; gap: 8px 16px; }
.parse-form .field { flex: 1 1 280px; }
.parse-form .hint { flex-basis: 100%; }
.glossary .title-row { display: flex; align-items: baseline; gap: 12px; }
.unsaved { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
.glossary-table { min-width: 640px; }
.glossary-table th, .glossary-table td { padding: 6px 8px; }
.glossary-table th:first-child, .glossary-table td:first-child { padding-left: 16px; }
.glossary-table input { width: 100%; border-color: transparent; background: none; }
.glossary-table input:hover { border-color: var(--line); }
.glossary-table input.jp { font-family: var(--jp); }
.glossary-table input.en { font-family: var(--serif); font-size: 17px; }
.glossary-table tr.changed td:first-child { box-shadow: inset 3px 0 0 var(--seal); }
.row-actions { width: 1%; white-space: nowrap; }
```

Append to `web/src/styles/index.css`:

```css
@import "./settings.css";
```

- [ ] **Step 9: Verify**

Run: `npm test && npm run build && npx playwright test e2e/profiles.spec.ts`
Expected: all pass, including the new Discard test.

- [ ] **Step 10: Commit**

```bash
git add web/src/ui/icons.tsx web/src/settings web/src/styles/settings.css web/src/styles/index.css web/e2e/profiles.spec.ts
git commit -m "feat(web): Profiles with a profile list, changed-row marks and glossary Discard"
```

---

### Task 6: Machine translation settings

**Files:**
- Modify: `web/src/settings/MtSettingsPage.tsx`, `web/src/styles/settings.css`

**Interfaces:**
- Consumes: `PageHeader` (Task 3); `ArrowUp`, `ArrowDown` (Task 5); `.cols`, `.sec-head`, `.inline-form`, `.row-fields` (Task 5).
- Produces: `KeyState({ text, ok }: { text: string; ok: boolean })`, exported from `MtSettingsPage.tsx` and reused by Task 7. Classes `.key-state`, `.order-list`, `.stack-col`, `.saved-note`.

- [ ] **Step 1: Confirm the existing spec passes before changing anything**

Run: `npx playwright test e2e/mt-settings.spec.ts`
Expected: PASS. It is the regression guard for this task.

- [ ] **Step 2: Rewrite the page's markup**

In `web/src/settings/MtSettingsPage.tsx`, add the imports:

```tsx
import { ArrowDown, ArrowUp } from "../ui/icons";
import PageHeader from "../ui/PageHeader";
```

Add this component above `export default function MtSettingsPage()`:

```tsx
/** "Key saved …hint" with a green dot, or the reason there is none. */
export function KeyState({ text, ok }: { text: string; ok: boolean }) {
  return <span className="key-state"><span className={ok ? "dot ok" : "dot"} aria-hidden="true" />{text}</span>;
}
```

Inside the component, below `keyState`, add:

```tsx
  const hasKey = (kind: Kind) => Boolean(cred(kind)?.has_secret && !cred(kind)?.secret_unreadable);
```

Replace the whole `return (…)` with:

```tsx
  return (
    <main className="settings">
      <PageHeader title="Machine translation"
        subtitle="Which panels appear beside the editor, in what order, and how each service is reached."
        actions={note ? <span role="status" className="saved-note">{note}</span> : undefined} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="cols">
        {backends.data && (
          <section className="panel sec mt-order" aria-labelledby="mt-panels-h">
            <h2 id="mt-panels-h">Panels</h2>
            <label className="field"><span>Target language</span>
              <select aria-label="Target language" value={backends.data.target}
                onChange={(e) => putSetting.mutate({ mt_target: e.target.value })}>
                {Object.entries(backends.data.languages).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
              </select>
            </label>
            <p className="hint">Checked panels show in the editor in this order. Changes save as you make them.</p>
            <ul className="order-list">
              {shown.map((n, i) => {
                const b = rows.find((r) => r.name === n)!;
                return (
                  <li key={n}>
                    <label className="check"><input type="checkbox" aria-label={`Show ${LABELS[n]}`} checked={on.includes(n)} onChange={() => toggle(n)} />{LABELS[n]}</label>
                    <span className={b.available ? "badge ok" : "badge warn"} data-testid={`status-${n}`}>{b.available ? "Ready" : b.message}</span>
                    <button type="button" className="icon" aria-label={`Move ${LABELS[n]} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp /></button>
                    <button type="button" className="icon" aria-label={`Move ${LABELS[n]} down`} disabled={i === shown.length - 1} onClick={() => move(i, 1)}><ArrowDown /></button>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        <div className="stack-col">
          <form className="panel sec" aria-labelledby="deepl-h" onSubmit={(e) => { const f = e.currentTarget; const secret = typed(form(e).get("k")); if (secret) saveCred.mutate({ kind: "deepl", secret }, { onSuccess: () => f.reset() }); }}>
            <div className="sec-head"><h2 id="deepl-h">DeepL</h2><KeyState text={keyState("deepl")} ok={hasKey("deepl")} /></div>
            <div className="inline-form">
              <label className="field grow"><span>API key</span>
                <input type="password" name="k" aria-label="DeepL API key" autoComplete="off"
                  placeholder={hasKey("deepl") ? "Enter a new key to replace the saved one" : undefined} /></label>
              <button type="submit">Save DeepL</button>
            </div>
          </form>

          <form key={cred("libretranslate")?.endpoint_url} className="panel sec" aria-labelledby="lt-h" onSubmit={(e) => {
            const el = e.currentTarget; const f = form(e); const secret = typed(f.get("k"));
            saveCred.mutate({ kind: "libretranslate", endpoint_url: typed(f.get("u")), ...(secret ? { secret } : {}) },
              { onSuccess: () => { (el.elements.namedItem("k") as HTMLInputElement).value = ""; } });
          }}>
            <div className="sec-head"><h2 id="lt-h">LibreTranslate</h2><KeyState text={keyState("libretranslate")} ok={hasKey("libretranslate")} /></div>
            <div className="row-fields">
              <label className="field"><span>Server URL</span><input name="u" className="mono" aria-label="LibreTranslate URL" defaultValue={cred("libretranslate")?.endpoint_url ?? ""} /></label>
              <label className="field"><span>API key (optional)</span><input type="password" name="k" aria-label="LibreTranslate API key" autoComplete="off" /></label>
            </div>
            <div><button type="submit">Save LibreTranslate</button></div>
          </form>

          <section className="panel sec" aria-labelledby="ollama-h">
            <div className="sec-head">
              <h2 id="ollama-h">Ollama</h2>
              <KeyState text={keyState("ollama").replace("key", "token").replace("Key", "Token")} ok={hasKey("ollama")} />
            </div>
            <form key={cred("ollama")?.endpoint_url} className="stack" onSubmit={(e) => {
              const el = e.currentTarget; const f = form(e); const secret = typed(f.get("k"));
              saveCred.mutate({ kind: "ollama", endpoint_url: typed(f.get("u")), ...(secret ? { secret } : {}) },
                { onSuccess: () => { (el.elements.namedItem("k") as HTMLInputElement).value = ""; } });
            }}>
              <div className="row-fields">
                <label className="field"><span>Server URL</span><input name="u" className="mono" aria-label="Ollama URL" placeholder="server default" defaultValue={cred("ollama")?.endpoint_url ?? ""} /></label>
                <label className="field"><span>Token (optional)</span><input type="password" name="k" aria-label="Ollama token" autoComplete="off" /></label>
              </div>
              <div><button type="submit">Save Ollama URL</button></div>
            </form>
            <form key={`${s.ollama_model}|${s.ollama_system_prompt}`} className="stack" onSubmit={(e) => {
              const f = form(e);
              putSetting.mutate({ ollama_model: typed(f.get("m")), ollama_system_prompt: String(f.get("p") ?? "") });
            }}>
              <label className="field"><span>Model</span><input name="m" className="mono" aria-label="Ollama model" defaultValue={String(s.ollama_model ?? "")} /></label>
              <label className="field"><span>System prompt</span>
                <textarea name="p" aria-label="Ollama system prompt" rows={8} placeholder={backends.data?.ollama_default_prompt}
                  defaultValue={String(s.ollama_system_prompt ?? "")} aria-describedby="prompt-hint" /></label>
              <p id="prompt-hint" className="hint">Leave empty to use the built-in prompt. Reset clears your own.</p>
              <div className="toolbar">
                <button type="submit">Save Ollama options</button>
                <button type="button" className="quiet" onClick={() => resetPrompt.mutate()}>Reset</button>
              </div>
            </form>
          </section>
        </div>
      </div>
    </main>
  );
```

- [ ] **Step 3: Styles**

Append to `web/src/styles/settings.css`:

```css
.cols > .mt-order { flex: 1 1 360px; max-width: 460px; }
.cols > .stack-col { flex: 2 1 560px; }
.stack-col { display: flex; flex-direction: column; gap: 24px; }
.key-state { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
.order-list { list-style: none; margin: 0; padding: 0; }
.order-list li { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-top: 1px solid var(--line); }
.order-list li:first-child { border-top: 0; }
.order-list .check { flex: 1; align-items: center; min-height: 36px; font-weight: 500; }
.order-list .check input { margin-top: 0; }
.saved-note { font-size: 14px; color: var(--ok); }
```

- [ ] **Step 4: Verify**

Run: `npm run build && npx playwright test e2e/mt-settings.spec.ts e2e/mt.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/settings/MtSettingsPage.tsx web/src/styles/settings.css
git commit -m "feat(web): restyle Machine translation settings"
```

---

### Task 7: WordPress settings

**Files:**
- Modify: `web/src/settings/WpSettingsPage.tsx`, `web/src/styles/settings.css`

**Interfaces:**
- Consumes: `PageHeader` (Task 3); `KeyState` (Task 6); `.cols`, `.sec-head` (Task 5); `.box` (Task 2).
- Produces: classes `.grp`, `.inline-field`, `.num-input`.

- [ ] **Step 1: Regression guard**

Run: `npx playwright test e2e/publish.spec.ts`
Expected: PASS before the change (it fills the WordPress form).

- [ ] **Step 2: Rewrite the markup**

In `web/src/settings/WpSettingsPage.tsx`, add the imports:

```tsx
import PageHeader from "../ui/PageHeader";
import { KeyState } from "./MtSettingsPage";
```

Replace the whole `return (…)` with:

```tsx
  return (
    <main className="settings">
      <PageHeader title="WordPress" subtitle="Publishing goes through the TA Publisher plugin on your site."
        actions={note ? <span role="status" className="saved-note">{note}</span> : undefined} />
      {error && <p className="error" role="alert">{error.message}</p>}
      <div className="cols">
        <form className="panel sec" key={cred?.endpoint_url ?? ""} onSubmit={submitCred} aria-labelledby="wp-conn-h">
          <div className="sec-head">
            <h2 id="wp-conn-h">Connection</h2>
            <KeyState text={keyState} ok={Boolean(cred?.has_secret && !cred.secret_unreadable)} />
          </div>
          <label className="field"><span>Endpoint URL</span>
            <input name="url" className="mono" aria-label="WordPress endpoint URL" required
              placeholder="https://yoursite.com/wp-json/ta-publisher/v1/publish" defaultValue={cred?.endpoint_url ?? ""} /></label>
          <label className="field"><span>API key</span>
            <input name="key" type="password" aria-label="WordPress API key" autoComplete="off"
              required={!cred} aria-describedby="wp-key-hint" /></label>
          <p id="wp-key-hint" className="hint">WP Admin → Settings → TA Publisher</p>
          <div className="toolbar">
            <button type="submit" className="primary" disabled={saveCred.isPending}>Save connection</button>
            <button type="button" disabled={!cred || test.isPending} onClick={() => test.mutate()}>Test connection</button>
          </div>
          {test.data && <p role="status" className={test.data.ok ? "box ok" : "box danger"}>{test.data.message}</p>}
        </form>

        {p && (
          <form className="panel sec" key={JSON.stringify(p)} onSubmit={submitPrefs} aria-labelledby="wp-def-h">
            <h2 id="wp-def-h">Publishing defaults</h2>
            <fieldset className="grp">
              <legend className="label">Chapter passwords</legend>
              <label className="check"><input type="checkbox" name="pw" defaultChecked={p.wp_password_enabled} /><span>Enable password protection by default</span></label>
              <label className="inline-field"><span>Keep N chapters locked</span>
                <input type="number" name="unlock" className="num-input mono" min={1} max={99} defaultValue={p.wp_unlock_after} /></label>
              <label className="check"><input type="checkbox" name="attr" defaultChecked={p.wp_attribution_enabled} /><span>Add attribution footer to published chapters</span></label>
            </fieldset>
            <fieldset className="grp">
              <legend className="label">Schedule</legend>
              <label className="check"><input type="checkbox" name="timed" defaultChecked={!!p.wp_default_schedule_time} /><span>Set default schedule time</span></label>
              <label className="inline-field"><span>Time</span>
                <input type="time" name="time" className="mono" defaultValue={p.wp_default_schedule_time || "20:00"} /></label>
              <label className="inline-field"><span>Chapters per day</span>
                <input type="number" name="perday" className="num-input mono" min={1} max={99} defaultValue={p.wp_chapters_per_day} /></label>
              <label className="check"><input type="checkbox" name="global" defaultChecked={p.wp_schedule_scope_global} /><span>Count chapters/day across all series</span></label>
            </fieldset>
            <div><button type="submit" disabled={savePrefs.isPending}>Save defaults</button></div>
          </form>
        )}
      </div>
    </main>
  );
```

- [ ] **Step 3: Styles**

Append to `web/src/styles/settings.css`:

```css
.grp { display: flex; flex-direction: column; gap: 12px; min-width: 0; margin: 0; padding: 16px 0 0; border: 0; border-top: 1px solid var(--line); }
.grp legend { float: left; width: 100%; padding: 0 0 4px; }
.grp legend + * { clear: both; }
.inline-field { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.num-input { width: 88px; }
```

- [ ] **Step 4: Verify**

Run: `npm run build && npx playwright test e2e/publish.spec.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/settings/WpSettingsPage.tsx web/src/styles/settings.css
git commit -m "feat(web): restyle WordPress settings"
```

---

### Task 8: Shortcuts

**Files:**
- Create: `web/src/settings/shortcutGroups.ts`, `web/src/settings/shortcutGroups.test.ts`
- Modify: `web/src/settings/ShortcutsPage.tsx`, `web/src/styles/settings.css`

**Interfaces:**
- Consumes: `Action` and `ACTIONS` from `editor/keymap.ts`; `PageHeader` (Task 3).
- Produces: `interface ActionGroup { title: string; actions: Action[] }` and `groupActions(actions: Action[]): ActionGroup[]`.

- [ ] **Step 1: Write the failing test**

`web/src/settings/shortcutGroups.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { ACTIONS } from "../editor/keymap";
import { groupActions } from "./shortcutGroups";

describe("shortcut sections", () => {
  it("puts every action in exactly one section, keeping order", () => {
    const groups = groupActions(ACTIONS);
    expect(groups.map((g) => g.title)).toEqual(["Moving between lines", "Phrases and tools", "Insert characters", "Text size"]);
    expect(groups.flatMap((g) => g.actions).map((a) => a.key).sort()).toEqual(ACTIONS.map((a) => a.key).sort());
    expect(groups[0].actions.map((a) => a.key)).toEqual(
      ["save_next", "next", "next_alt", "prev", "prev_alt", "next_untranslated", "first", "go_to_line"]);
    expect(groups[2].actions).toHaveLength(9);
    expect(groups[3].actions.map((a) => a.key)).toEqual(["font_larger", "font_smaller"]);
  });
  it("files an unknown action under Phrases and tools and drops empty sections", () => {
    const extra = { key: "new_thing", label: "New thing", binding: "Ctrl+K" };
    expect(groupActions([extra])).toEqual([{ title: "Phrases and tools", actions: [extra] }]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/settings/shortcutGroups.test.ts`
Expected: FAIL, the import can't be resolved.

- [ ] **Step 3: Implement**

`web/src/settings/shortcutGroups.ts`:

```ts
import type { Action } from "../editor/keymap";

export interface ActionGroup { title: string; actions: Action[] }

const TITLES = ["Moving between lines", "Phrases and tools", "Insert characters", "Text size"] as const;
const LINES = new Set(["save_next", "next", "next_alt", "prev", "prev_alt", "next_untranslated", "first", "go_to_line"]);
const SIZE = new Set(["font_larger", "font_smaller"]);

function titleOf(key: string): (typeof TITLES)[number] {
  if (LINES.has(key)) return "Moving between lines";
  if (key.startsWith("punct_")) return "Insert characters";
  if (SIZE.has(key)) return "Text size";
  return "Phrases and tools";
}

/** The Shortcuts page's sections, each in ACTIONS order; empty sections are dropped. */
export function groupActions(actions: Action[]): ActionGroup[] {
  return TITLES
    .map((title) => ({ title, actions: actions.filter((a) => titleOf(a.key) === title) }))
    .filter((g) => g.actions.length > 0);
}
```

Run: `npx vitest run src/settings/shortcutGroups.test.ts`
Expected: PASS.

- [ ] **Step 4: Rewrite the page's markup**

In `web/src/settings/ShortcutsPage.tsx`, add the imports:

```tsx
import PageHeader from "../ui/PageHeader";
import { groupActions } from "./shortcutGroups";
```

Replace the whole `return (…)` with:

```tsx
  return (
    <main className="settings">
      <PageHeader title="Keyboard shortcuts" subtitle="Editor keys. Press Change, then the new key; Esc cancels." />
      {error && <p className="box danger" role="alert">{error}</p>}
      <div className="shortcut-groups">
        {groupActions(ACTIONS).map((g, gi) => (
          <section key={g.title} className="panel" aria-labelledby={`sc-group-${gi}`}>
            <h2 id={`sc-group-${gi}`} className="label panel-label">{g.title}</h2>
            <ul className="shortcut-list">
              {g.actions.map((a) => {
                const here = capturing === a.key;
                const changed = bindings[a.key] !== a.binding;
                return (
                  <li key={a.key} className={here ? "capturing" : undefined}>
                    <span>
                      {a.label}
                      {changed && <><span className="dot accent" aria-hidden="true" /><span className="visually-hidden"> (changed)</span></>}
                    </span>
                    <kbd>{here ? "Press a key…" : bindings[a.key]}</kbd>
                    <span className="sc-actions">
                      <button type="button" className="small" disabled={bind.isPending}
                        onClick={() => { setProblem(null); setCapturing(here ? null : a.key); }}>
                        {here ? "Cancel" : "Change"}
                      </button>
                      {changed && (
                        <button type="button" className="small quiet" title={`Reset to ${a.binding}`} aria-label={`Reset to ${a.binding}`}
                          disabled={reset.isPending} onClick={() => reset.mutate(a.key)}>Reset</button>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </main>
  );
```

- [ ] **Step 5: Styles**

Append to `web/src/styles/settings.css`:

```css
.shortcut-groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(460px, 100%), 1fr)); gap: 24px; align-items: start; }
.panel-label { padding: 14px 18px 10px; }
.shortcut-list { list-style: none; margin: 0; padding: 0; }
.shortcut-list li { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 12px;
  min-height: 52px; padding: 8px 18px; border-top: 1px solid var(--line); }
.shortcut-list li.capturing { background: var(--accent-soft); }
.shortcut-list li.capturing kbd { border-style: dashed; border-color: var(--accent-text); background: none; color: var(--accent-ink); }
.shortcut-list .dot { margin-left: 8px; vertical-align: 2px; }
.dot.accent { background: var(--accent-text); }
.sc-actions { display: flex; justify-content: flex-end; gap: 4px; }
```

- [ ] **Step 6: Verify**

Run: `npm test && npm run build`
Expected: all pass.

Manual check:
- Press Change on "Find", then Ctrl+G. The red alert says it's already used by "Go to line".
- Change "Find" to Ctrl+Shift+F. A dot and a Reset button appear; Reset restores Ctrl+F.

- [ ] **Step 7: Commit**

```bash
git add web/src/settings/shortcutGroups.ts web/src/settings/shortcutGroups.test.ts web/src/settings/ShortcutsPage.tsx web/src/styles/settings.css
git commit -m "feat(web): Shortcuts grouped by purpose with capture and reset states"
```

---

### Task 9: Import with a drop zone

**Files:**
- Create: `web/src/library/drop.ts`, `web/src/library/drop.test.ts`, `web/src/styles/import.css`
- Modify: `web/src/library/ImportPage.tsx`, `ImportFiles.tsx`, `ImportEpub.tsx`, `SeriesChoice.tsx`, `web/src/styles/index.css`

**Interfaces:**
- Consumes: `PageHeader` (Task 3); `.cols`, `.sec-head`, `.row-fields`, `.inline-form`, `.file-btn` (Task 5); `.box` (Task 2).
- Produces: `acceptFiles<T extends { name: string }>(files: T[], extensions: string[]): { accepted: T[]; rejected: T[] }`.

- [ ] **Step 1: Write the failing test**

`web/src/library/drop.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { acceptFiles } from "./drop";

const f = (name: string) => ({ name });

describe("acceptFiles", () => {
  it("keeps accepted extensions regardless of case and reports the rest", () => {
    const { accepted, rejected } = acceptFiles(
      [f("01.txt"), f("G.CSV"), f("cover.png"), f("notes.txt.bak"), f("txt"), f("folder")], [".txt", ".csv"]);
    expect(accepted.map((x) => x.name)).toEqual(["01.txt", "G.CSV"]);
    expect(rejected.map((x) => x.name)).toEqual(["cover.png", "notes.txt.bak", "txt", "folder"]);
  });
  it("handles an empty drop", () => {
    expect(acceptFiles([], [".txt"])).toEqual({ accepted: [], rejected: [] });
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/library/drop.test.ts`
Expected: FAIL, the import can't be resolved.

- [ ] **Step 3: Implement**

`web/src/library/drop.ts`:

```ts
/** Split dropped or picked files into those with an accepted extension (case-insensitive) and the rest.
 *  A dropped folder arrives as a File without an extension, so it lands in `rejected`. */
export function acceptFiles<T extends { name: string }>(files: T[], extensions: string[]): { accepted: T[]; rejected: T[] } {
  const ok = (file: T) => extensions.some((ext) => file.name.toLowerCase().endsWith(ext.toLowerCase()));
  return { accepted: files.filter(ok), rejected: files.filter((file) => !ok(file)) };
}
```

Run: `npx vitest run src/library/drop.test.ts`
Expected: PASS.

- [ ] **Step 4: Series choice as two fields**

Replace the component in `web/src/library/SeriesChoice.tsx` (keep `appendSeries` as is):

```tsx
export default function SeriesChoice({ series, value, onChange }: {
  series: SeriesRow[]; value: Choice; onChange: (c: Choice) => void;
}) {
  return (
    <div className="row-fields">
      <label className="field"><span>Series</span>
        <select value={value.id} onChange={(e) => onChange({ id: e.target.value, title: "" })}>
          <option value="">Unsorted</option>
          {series.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
        </select>
      </label>
      <label className="field"><span>New series title</span>
        <input value={value.title} onChange={(e) => onChange({ id: "", title: e.target.value })} />
      </label>
    </div>
  );
}
```

- [ ] **Step 5: TXT/CSV card with the drop zone**

In `web/src/library/ImportFiles.tsx`, add `import { acceptFiles } from "./drop";`. Then replace everything from `const submit = …` to the end of the component with:

```tsx
  const [skipped, setSkipped] = useState<string[]>([]);
  const [over, setOver] = useState(false);
  const choose = (list: File[]) => {
    const { accepted, rejected } = acceptFiles(list, [".txt", ".csv"]);
    setFiles(accepted);
    setSkipped(rejected.map((file) => file.name));
    run.reset();
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run.mutate();
  };
  const kb = (bytes: number) => `${Math.max(1, Math.round(bytes / 1024))} KB`;
  const r = run.data;
  return (
    <form className="panel sec" aria-labelledby="import-txt-h" onSubmit={submit}>
      <h2 id="import-txt-h">TXT and CSV files</h2>
      <label className={over ? "drop over" : "drop"}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); choose([...e.dataTransfer.files]); }}>
        <span className="drop-title">Drop files here or choose them</span>
        <span className="hint">.txt chapters, plus an optional glossary .csv · up to 500 files, 12 MB per import</span>
        <input type="file" multiple accept=".txt,.csv" aria-label="Files to import" className="visually-hidden"
          onChange={(e) => choose([...(e.target.files ?? [])])} />
      </label>
      {skipped.length > 0 && (
        <p className="hint">Skipped {skipped.length} {skipped.length === 1 ? "file that is" : "files that are"} not .txt or .csv: {skipped.join(", ")}</p>
      )}
      {files.length > 0 && (
        <ul className="file-list" aria-label="Chosen files">
          {files.map((file) => <li key={file.name}><span className="mono">{file.name}</span><span className="muted">{kb(file.size)}</span></li>)}
        </ul>
      )}
      <SeriesChoice series={series} value={choice} onChange={setChoice} />
      <div className="inline-form">
        <button className="primary" disabled={!files.length || run.isPending}>Import</button>
        {files.length > 0 && <span className="muted">{files.length} {files.length === 1 ? "file" : "files"} chosen</span>}
      </div>
      {run.isError && <p className="error" role="alert">{run.error.message}</p>}
      {r && (
        <div className="box ok result" role="status">
          <p>Imported: {r.imported.length}</p>
          <p>Skipped: {r.skipped.length} (already exist)</p>
          <p>Errors: {r.errors.length}</p>
          {r.warnings.map((w) => <p key={w}>{w}</p>)}
          {r.skipped.length > 0 && <p>Skipped: {r.skipped.join(", ")}</p>}
          {r.errors.map((x) => <p key={x.name} className="error">{x.name} — {x.message}</p>)}
        </div>
      )}
    </form>
  );
}
```

(`useState` is already imported in this file.)

- [ ] **Step 6: EPUB card**

In `web/src/library/ImportEpub.tsx`, replace the component's `return (…)` with:

```tsx
  return (
    <form className="panel sec" aria-labelledby="import-epub-h" onSubmit={submit}>
      <div className="sec-head">
        <h2 id="import-epub-h">EPUB</h2>
        {file && <span className="muted mono">{file.name}</span>}
      </div>
      <div className="inline-form">
        <label className="btn file-btn">
          {file ? "Choose another EPUB" : "Choose an EPUB file"}
          <input type="file" accept=".epub" aria-label="EPUB file" className="visually-hidden"
            onChange={(e) => pick(e.target.files?.[0] ?? null)} />
        </label>
        <span className="hint">Up to 64 MB</span>
      </div>
      {inspect.isPending && <p className="muted">Reading…</p>}
      {book && (
        <>
          <SeriesChoice series={series} value={choice} onChange={setChoice} />
          <label className="field"><span>Volume title</span><input value={volumeTitle} onChange={(e) => setVolumeTitle(e.target.value)} /></label>
          <div className="row-fields">
            {META.map(([key, label]) => (
              <label key={key} className="field"><span>{label}</span>
                <input value={meta[key]} onChange={(e) => setMeta({ ...meta, [key]: e.target.value })} />
              </label>
            ))}
          </div>
          <fieldset className="checklist">
            <legend className="field-legend"><span>Chapters</span><span className="hint">Short pages without images start unchecked</span></legend>
            {book.chapters.map((c) => (
              <label key={c.href} className={checked.has(c.href) ? "check-row" : "check-row dim"}>
                <input type="checkbox" checked={checked.has(c.href)} onChange={(e) => toggle(c.href, e.target.checked)} />
                <span className="title">{c.order}. {c.title}</span>
                <span className="muted">{c.char_count.toLocaleString()} chars{c.image_count ? ` · ${c.image_count} images` : ""}</span>
              </label>
            ))}
          </fieldset>
          <div className="inline-form">
            <button className="primary" disabled={!checked.size || run.isPending}>Import</button>
            <span className="muted">{checked.size} chapters selected · {book.chapters.length - checked.size} unchecked</span>
          </div>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {r && (
        <div className="box ok result" role="status">
          <p><b>{r.imported.length ? "Import complete." : "Import finished — nothing new imported."}</b></p>
          <p>Imported: {r.imported.length}</p>
          <p>Skipped: {r.skipped.length} (already imported)</p>
          <p>Errors: {r.errors.length}</p>
          {r.skipped.length > 0 && <p>Skipped: {r.skipped.join(", ")}</p>}
          {r.empty.length > 0 && (
            <p>No text extracted (0 lines) — these will always read as 0% translated and are omitted from EPUB export: {r.empty.join(", ")}</p>
          )}
          {r.errors.map((x) => <p key={x.title} className="error">Error: {x.title} — {x.message}</p>)}
          <p><Link to={`/series/${r.series_id}`}>Open series</Link></p>
        </div>
      )}
    </form>
  );
```

- [ ] **Step 7: The page**

Replace `web/src/library/ImportPage.tsx` with:

```tsx
import { Link } from "react-router";
import PageHeader from "../ui/PageHeader";
import ImportEpub from "./ImportEpub";
import ImportFiles from "./ImportFiles";
import { useSeriesList } from "./queries";

export default function ImportPage() {
  const series = useSeriesList();
  if (series.isPending) return <main><p className="muted">Loading…</p></main>;
  if (series.isError) return <main><p className="error">{series.error.message}</p></main>;
  return (
    <main className="settings">
      <PageHeader title="Import" crumbs={<><Link to="/">Library</Link><span aria-hidden="true">/</span><span>Import</span></>} />
      <div className="cols import-cols">
        <ImportFiles series={series.data} />
        <ImportEpub series={series.data} />
      </div>
    </main>
  );
}
```

- [ ] **Step 8: Styles**

`web/src/styles/import.css`:

```css
.import-cols > :last-child { flex-grow: 1.4; }
.drop { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; min-height: 132px;
  padding: 20px; border: 1.5px dashed var(--line); border-radius: 8px; background: var(--raised); text-align: center; cursor: pointer; }
.drop:hover, .drop.over { border-color: var(--accent-text); }
.drop:focus-within { outline: 2px solid var(--accent-text); outline-offset: 2px; }
.drop-title { font-weight: 500; }
.file-list { list-style: none; margin: 0; padding: 0; font-size: 14px; }
.file-list li { display: flex; justify-content: space-between; gap: 12px; padding: 8px 2px; border-top: 1px solid var(--line); }
.file-list .mono { min-width: 0; overflow-wrap: anywhere; }
.checklist { min-width: 0; margin: 0; padding: 0; border: 0; }
.field-legend { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; width: 100%; padding: 0 0 6px; font-size: 13px; font-weight: 500; }
.check-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px; min-height: 44px;
  padding: 6px 4px; border-top: 1px solid var(--line); font-size: 14px; }
.check-row.dim .title { color: var(--muted); }
.result { flex-direction: column; gap: 2px; }
.result p { margin: 0; }
```

Append to `web/src/styles/index.css`:

```css
@import "./import.css";
```

- [ ] **Step 9: Verify**

Run: `npm test && npm run build && npx playwright test e2e/import.spec.ts`
Expected: all pass. The import spec still finds "Files to import", "New series title" (twice), "EPUB file", `/1\. Neko chapter/`, "Author", the exact "Import" buttons, "Imported: 2" and "Open series".

Manual check: drag two `.txt` files and a `.png` onto the zone. The two `.txt` files are listed, and a note names the `.png` as skipped.

- [ ] **Step 10: Commit**

```bash
git add web/src/library web/src/styles/import.css web/src/styles/index.css
git commit -m "feat(web): Import cards with a drop zone and EPUB chapter checklist"
```

---

### Task 10: Single-publish dialog

**Files:**
- Create: `web/src/publish/label.ts`, `web/src/publish/label.test.ts`
- Modify: `web/src/publish/PublishDialog.tsx`

**Interfaces:**
- Consumes: `.dlg-*`, `.box`, `.badge`, `.field`, `.check` (Task 2).
- Produces: `confirmLabel(previousScheduled: boolean, scheduling: boolean): string` and `statusTone(status: string): "ok" | "warn" | ""`.

- [ ] **Step 1: Write the failing test**

`web/src/publish/label.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { confirmLabel, statusTone } from "./label";

describe("publish dialog labels", () => {
  it("says anyway only when the previous chapter is still scheduled", () => {
    expect(confirmLabel(false, false)).toBe("Publish");
    expect(confirmLabel(false, true)).toBe("Publish");
    expect(confirmLabel(true, true)).toBe("Schedule anyway");
    expect(confirmLabel(true, false)).toBe("Publish anyway");
  });
  it("colours published and scheduled, and nothing else", () => {
    expect(statusTone("publish")).toBe("ok");
    expect(statusTone("future")).toBe("warn");
    expect(statusTone("draft")).toBe("");
    expect(statusTone("")).toBe("");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/publish/label.test.ts`
Expected: FAIL, the import can't be resolved.

- [ ] **Step 3: Implement**

`web/src/publish/label.ts`:

```ts
/** The confirm button. "Anyway" appears only while the previous chapter is still scheduled (spec §9.4). */
export function confirmLabel(previousScheduled: boolean, scheduling: boolean): string {
  if (!previousScheduled) return "Publish";
  return scheduling ? "Schedule anyway" : "Publish anyway";
}

/** Badge tone for a WordPress status. */
export function statusTone(status: string): "ok" | "warn" | "" {
  if (status === "publish") return "ok";
  if (status === "future") return "warn";
  return "";
}
```

Run: `npx vitest run src/publish/label.test.ts`
Expected: PASS.

- [ ] **Step 4: Rewrite the dialog's markup**

In `web/src/publish/PublishDialog.tsx`, add `import { confirmLabel, statusTone } from "./label";`. Then replace the `return (…)` with:

```tsx
  const statusText = status.isPending ? "checking…" : status.data ? (LABEL[status.data.status] ?? status.data.status) : "unknown";
  const title = doc.chapter_title || doc.title;
  return (
    <dialog ref={ref} onClose={onClose} onCancel={(e) => { if (run.isPending) e.preventDefault(); }}
      aria-label="Publish to WordPress" className="dlg">
      <div className="dlg-head">
        <span className="label">Publish to WordPress</span>
        <h2>{title}</h2>
        <p className="muted">{chapter}</p>
      </div>
      {result ? (
        <div className="dlg-body">
          <p className="box ok" role="status">{result.created || result.updated ? (result.scheduled_for ? "Scheduled!" : result.created ? "Published!" : "Updated!") : "Already published."}</p>
          {result.page_url && <p>Page: <a href={result.page_url} target="_blank" rel="noreferrer">{result.page_url}</a></p>}
          {result.post_url && <p>Post: <a href={result.post_url} target="_blank" rel="noreferrer">{result.post_url}</a></p>}
          {result.password && (
            <label className="field"><span>Password (copy this)</span>
              <input readOnly className="mono" value={result.password} onFocus={(e) => e.currentTarget.select()} /></label>
          )}
          {result.unlock_chapter_index !== null && <p className="muted">Chapter {result.unlock_chapter_index} is now unlocked.</p>}
        </div>
      ) : (
        <div className="dlg-body">
          <p>WP status: <span className={`badge ${statusTone(status.data?.status ?? "")}`}>{statusText}</span>
            {status.data?.remote_error && <span className="muted"> (cached — {status.data.remote_error})</span>}</p>
          {status.data?.status === "publish" && <p className="muted">Republishing will overwrite the live chapter.</p>}
          {status.data?.previous_scheduled && (
            <p className="box warn">Chapter {doc.series_order - 1} is still scheduled and hasn't gone live yet.</p>
          )}
          <label className="check"><input type="checkbox" checked={scheduling} onChange={(e) => setSchedule(e.target.checked)} /><span>Schedule for later</span></label>
          <label className="field"><span>When</span>
            <input type="datetime-local" className="mono" disabled={!scheduling} value={slot} onChange={(e) => setWhen(e.target.value)} /></label>
        </div>
      )}
      {(status.error ?? run.error) && <p className="error" role="alert">{(status.error ?? run.error)!.message}</p>}
      <div className="dlg-foot">
        <button type="button" onClick={onClose}>{result ? "Close" : "Cancel"}</button>
        {!result && (
          <button type="button" className="primary" disabled={run.isPending || status.isPending || status.isError} onClick={() => run.mutate()}>
            {confirmLabel(!!status.data?.previous_scheduled, scheduling)}
          </button>
        )}
      </div>
    </dialog>
  );
```

- [ ] **Step 5: Verify**

Run: `npm test && npm run build && npx playwright test e2e/publish.spec.ts`
Expected: PASS. "WP status: Not published" matches the paragraph's combined text, the exact "Publish" button is found, and the batch test is unchanged.

- [ ] **Step 6: Commit**

```bash
git add web/src/publish/label.ts web/src/publish/label.test.ts web/src/publish/PublishDialog.tsx
git commit -m "feat(web): restyle the publish dialog; Schedule anyway when scheduling"
```

---

### Task 11: Sign in and invite

**Files:**
- Create: `web/src/styles/auth.css`
- Modify: `web/src/auth/Login.tsx`, `web/src/auth/AcceptInvite.tsx`, `web/src/styles/index.css`

**Interfaces:**
- Consumes: `.brand`, `.mark` (Task 2); `.field`, `.hint`, `.box` (Task 2).
- Produces: `.auth`, `.auth-card`.

- [ ] **Step 1: Rewrite the sign-in markup**

In `web/src/auth/Login.tsx`, replace the final `return (…)` with:

```tsx
  return (
    <main className="auth">
      <form className="auth-card" onSubmit={submit}>
        <span className="brand"><span className="mark" aria-hidden="true">訳</span>Translation Assistant</span>
        <h1>Sign in</h1>
        <label className="field"><span>Email</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field"><span>Password</span>
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {login.isError && <p className="box danger" role="alert">{login.error.message}</p>}
        <button className="primary" disabled={login.isPending}>Sign in</button>
        <p className="hint">Accounts are by invitation. Ask the person who runs this server for a link.</p>
      </form>
    </main>
  );
```

- [ ] **Step 2: Rewrite the invite markup**

In `web/src/auth/AcceptInvite.tsx`, replace both returns:

```tsx
  if (accept.isSuccess) {
    return (
      <main className="auth">
        <div className="auth-card">
          <span className="brand"><span className="mark" aria-hidden="true">訳</span>Translation Assistant</span>
          <h1>Account created</h1>
          <p><Link to="/login">Sign in</Link> with your email and password.</p>
        </div>
      </main>
    );
  }
  return (
    <main className="auth">
      <form className="auth-card" onSubmit={submit}>
        <span className="brand"><span className="mark" aria-hidden="true">訳</span>Translation Assistant</span>
        <h1>Create your account</h1>
        {!token && <p className="box danger">This link has no invite token.</p>}
        <label className="field"><span>Email</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field"><span>Password</span>
          <input type="password" autoComplete="new-password" required minLength={12} value={password}
            onChange={(e) => setPassword(e.target.value)} aria-describedby="pw-hint" /></label>
        <p id="pw-hint" className="hint">At least 12 characters.</p>
        <button className="primary" disabled={!token || accept.isPending}>Create account</button>
        {accept.isError && <p className="box danger" role="alert">{accept.error.message}</p>}
      </form>
    </main>
  );
```

- [ ] **Step 3: Styles**

`web/src/styles/auth.css`:

```css
.auth { display: grid; place-items: center; min-height: 100dvh; max-width: none; padding: 48px 16px; }
.auth-card { width: min(400px, 100%); display: flex; flex-direction: column; gap: 18px; padding: 32px;
  background: var(--surface); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 20px 50px -24px var(--shadow); }
.auth-card .mark { width: 40px; height: 40px; border-radius: 4px; font-size: 22px; }
.auth-card h1 { font-family: var(--serif); font-weight: 500; font-size: 30px; line-height: 1.2; }
.auth-card input { min-height: 44px; }
.auth-card button.primary { width: 100%; min-height: 44px; }
.auth-card p { margin: 0; }
```

Append to `web/src/styles/index.css`:

```css
@import "./auth.css";
```

- [ ] **Step 4: Verify**

Run: `npm run build && npm run e2e`
Expected: the whole suite passes; every spec signs in through this form.

- [ ] **Step 5: Commit**

```bash
git add web/src/auth/Login.tsx web/src/auth/AcceptInvite.tsx web/src/styles/auth.css web/src/styles/index.css
git commit -m "feat(web): sign-in and invite cards"
```

---

### Task 12: Phone-width check and docs

**Files:**
- Create: `web/e2e/narrow.spec.ts`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: every restyled page from Tasks 2–11.

- [ ] **Step 1: Write the test**

`web/e2e/narrow.spec.ts`:

```ts
import { expect, test, type Page } from "@playwright/test";

test.use({ viewport: { width: 390, height: 844 } });

const overflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test("sign-in fits a phone", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect(await overflow(page)).toBeLessThanOrEqual(0);
});

test("restyled pages fit a phone without sideways scrolling", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  for (const path of ["/stats", "/settings/profiles", "/settings/mt", "/settings/wp", "/settings/shortcuts", "/import"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    expect(await overflow(page), path).toBeLessThanOrEqual(0);
  }
});
```

- [ ] **Step 2: Run it**

Run: `npx playwright test e2e/narrow.spec.ts`
Expected: PASS. If a page overflows, the failure names its path. Fix that page's CSS so wide content scrolls inside a `.table-scroll` box (or give a flex child `min-width: 0`), never by hiding overflow on `body`, and rerun.

- [ ] **Step 3: Record the phase in CLAUDE.md**

In `CLAUDE.md`, after the paragraph that starts "Phase 6a: acquisition." and ends with the publish dialogs sentence, add:

```markdown
Phase 7a: visual system. Colours, fonts and spacing are tokens in `web/src/styles/tokens.css` (light and
`:root[data-theme="dark"]`); every other stylesheet under `web/src/styles/` (pulled in by `index.css`) uses
tokens, never literal colours. Fonts are self-hosted through `@fontsource` (`web/src/fonts.ts`). The theme
preference is the user setting `ui_theme` (`system`/`light`/`dark`), mirrored in `localStorage` `ta.theme`;
an inline script in `web/index.html` paints it before the bundle loads, `web/src/theme/` owns the rules, and
the account's value wins once `/settings` arrives. Spec: `docs/superpowers/specs/2026-10-14-web-redesign-design.md`.
```

- [ ] **Step 4: Full verification**

Run (repo root): `ruff check . && pytest -q`
Expected: unchanged and passing (no Python changed).

Run (in `web/`): `npm test && npm run build && npm run e2e`
Expected: everything passes.

- [ ] **Step 5: Commit**

```bash
git add web/e2e/narrow.spec.ts CLAUDE.md
git commit -m "test(e2e): restyled pages fit a phone; docs: phase 7a"
```
