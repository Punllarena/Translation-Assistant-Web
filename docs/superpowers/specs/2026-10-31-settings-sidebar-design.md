# One Settings page with a sidebar

Date: 2026-10-31. Replaces the TODO entry "Settings: one Settings page with tabs" (the chosen layout is a sidebar, not tabs).

## Why

The header (`web/src/Shell.tsx`) has seven links after Library: Statistics, Jobs, Editor, Machine translation, WordPress,
Shortcuts and, for admins, Admin. Five of them are settings and crowd the bar. They become one "Settings" link opening a
page with a sidebar, so every setting, personal or server-wide, is reached from one place.

## Goals

1. One header link, "Settings", replacing Editor, Machine translation, WordPress, Shortcuts and Admin. Library, Statistics
   and Jobs stay in the header.
2. A settings page with a sidebar on the left and the chosen section on the right.
3. Sidebar entries, in this order:
   - Personal: Editor, Machine translation, WordPress, Shortcuts.
   - An "Admin" group heading (admins only) with four entries: Server, Invites, Dictionary, Backup & restore.
4. Every old URL keeps working.

## Non-goals

- No change to what any settings form or admin panel does, and no API or database change.
- Statistics and Jobs do not move into Settings.
- No new settings, no search box, no unsaved-changes guard.

## Design

### Routes

A layout route `settings` renders the sidebar and an `<Outlet />`. Children:

| URL | Section |
|---|---|
| `/settings` | redirects (replace) to `/settings/editor` |
| `/settings/editor` | `EditorSettingsPage` |
| `/settings/mt` | `MtSettingsPage` |
| `/settings/wp` | `WpSettingsPage` |
| `/settings/shortcuts` | `ShortcutsPage` |
| `/settings/admin` | redirects to `/settings/admin/server` |
| `/settings/admin/server` | `ServerSettingsForm` |
| `/settings/admin/invites` | `InvitesPanel` |
| `/settings/admin/dictionary` | `DictionaryPanel` |
| `/settings/admin/backup` | `BackupPanel` |

- `/admin` redirects to `/settings/admin/server`. `/settings/profiles` keeps its existing redirect to `/settings/editor`.
- The admin URLs and names above are the designer's choice (the user chose "sidebar entries under an Admin heading").
- Update every link that points at `/admin` or at a settings URL if the target changed: `RunningJobs.tsx` sends the
  `dict_download` job to `/admin`; it must go to `/settings/admin/dictionary`. `OllamaCard`, `MtPanels` and `SeriesWp`
  link to `/settings/mt` and `/settings/wp`, which still work.

### Header

`<NavLink to="/settings/editor">Settings</NavLink>`, marked current for any path under `/settings` (use a custom
`aria-current` the way the Library link does with `LIBRARY`, or `NavLink` with the `/settings` prefix; builder's call).

### Page and sidebar

- The layout owns the single `<main>`. The section components currently render their own `<main>` (and
  `AdminPage` renders `main.settings`); change each section's root to a `div`/`section` so there is one `<main>` per page.
  Keep each section's `PageHeader` title ("Editor", ...), so the right side still reads as a page.
- The sidebar is `<nav aria-label="Settings">` with `NavLink`s (`aria-current="page"` on the open one) and a visually
  distinct, non-link "Admin" group heading. A non-admin never sees the group. Use the existing `useMe()` `is_admin`.
- Admin guard: a non-admin who opens any `/settings/admin/*` URL sees the same "Admin only." box `AdminPage` shows
  today, inside the settings layout. One guard wrapper around the four admin routes, not four copies.
- Admin panels were laid out in a `cols` grid on one page; each now fills the content area alone. Wrap each in the same
  `panel sec` look the settings sections use. Check `web/src/styles/` for the class names; add styles only through tokens
  (never literal colours), in the existing stylesheet for settings.
- Narrow screens (designer's call): below the width where the narrow e2e spec already runs, the sidebar becomes a
  horizontally scrollable row above the content. No horizontal page scroll at 360 px.

### Deleting the old Admin page

`web/src/admin/AdminPage.tsx` is no longer routed. Delete it, or reduce it to the shared guard; builder's call.

## Tests

- Update the Playwright specs that go to `/admin`: `admin.spec.ts` (it clicks the header "Admin" link, now Settings, then
  the sidebar's Admin entry), `dictionaries.spec.ts` (`goto("/settings/admin/dictionary")`), `backup.spec.ts`
  (`/settings/admin/backup`). `narrow.spec.ts` walks `/settings/*` paths; add the sidebar and one admin path to its
  no-horizontal-scroll check. Other specs that `goto("/settings/wp|mt|editor")` need no change.
- New e2e (one spec): each sidebar entry opens its section and is marked current; `/settings` lands on Editor; `/admin`
  lands on the Server section; a non-admin sees no Admin group and gets "Admin only." at `/settings/admin/server`.
- Vitest only if a pure helper appears (for example the "is this path under /settings" test).
- Gate: `npm test`, `npm run e2e` (affected specs), `ruff check .` untouched, `tsc` clean.

## Left to the builder

Exact class names and CSS, the sidebar's width and breakpoint, whether the header link uses `NavLink` or a prefix test,
and the file layout under `web/src/settings/`.

## Delegation

Plan: one plan, front end only. Suitable for DeepSeek V4.1 Flash on its own branch and worktree; Claude reviews.
