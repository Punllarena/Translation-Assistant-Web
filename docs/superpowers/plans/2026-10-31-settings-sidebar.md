# Settings Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the header's five settings links with one "Settings" link opening a page with a sidebar (personal sections, plus an admin-only group).

**Architecture:** A `settings` layout route renders a sidebar `nav` and an `Outlet`; each existing settings page and admin panel becomes a child route. Old URLs redirect. Front end only.

**Tech Stack:** React, react-router (`createRoutesFromElements`), Playwright, vitest.

**Spec:** `docs/superpowers/specs/2026-10-31-settings-sidebar-design.md`

## Global Constraints

- No API or database change; no settings form or admin panel changes behaviour.
- Colours and spacing only through tokens (`web/src/styles/tokens.css`); never literal colours.
- Admin URLs: `/settings/admin/server|invites|dictionary|backup`; `/admin` redirects to `/settings/admin/server`; `/settings` redirects to `/settings/editor`; `/settings/profiles` keeps its redirect.
- Exactly one `<main>` per page: the layout owns it, sections render a `div`/`section` root.
- A non-admin on any `/settings/admin/*` URL sees the box `Admin only.` (class `box danger`), inside the layout.
- Library, Statistics and Jobs stay in the header.

## Review Focus

- A non-admin typing `/settings/admin/dictionary` gets "Admin only." and no admin request fires.
- `/admin`, `/settings` and `/settings/admin` redirect with `replace`, so Back does not loop.
- The header "Settings" link stays marked current on every `/settings/*` path, including admin ones.
- No horizontal scroll at 360 px on any settings or admin section.
- `RunningJobs` sends a `dict_download` job to the Dictionary section, not a dead `/admin`.

---

### Task 1: Layout, routes, header, redirects

**Files:**
- Create: `web/src/settings/SettingsLayout.tsx`, `web/src/settings/AdminOnly.tsx`, `web/src/settings/settingsNav.ts`
- Modify: `web/src/App.tsx`, `web/src/Shell.tsx`, `web/src/jobs/RunningJobs.tsx:25`, `web/src/styles/settings.css`
- Modify (root element only: `<main>` to `<div>`): `web/src/settings/EditorSettingsPage.tsx`, `MtSettingsPage.tsx`, `WpSettingsPage.tsx`, `ShortcutsPage.tsx`
- Delete or reduce: `web/src/admin/AdminPage.tsx`
- Test: `web/src/settings/settingsNav.test.ts`

**Interfaces:**
- Produces: `PERSONAL: {to, label}[]` and `ADMIN: {to, label}[]` in `settingsNav.ts` (labels Editor, Machine translation, WordPress, Shortcuts / Server, Invites, Dictionary, Backup & restore); `isSettingsPath(pathname: string): boolean` (true for `/settings` and anything under `/settings/`); `<AdminOnly />` (layout route element: renders `<Outlet />` for `useMe().data?.is_admin`, else the `Admin only.` box).

- [ ] **Step 1: Write the failing test** in `settingsNav.test.ts`: `isSettingsPath("/settings/admin/server")` true, `"/settings"` true, `"/settingsx"` false, `"/"` false; `ADMIN.map(i => i.to)` equals the four admin URLs in spec order.
- [ ] **Step 2: Run** `cd web && npx vitest run src/settings/settingsNav.test.ts`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `settingsNav.ts`** as specified.
- [ ] **Step 4: Run the test.** Expected: PASS.
- [ ] **Step 5: Implement `SettingsLayout`** (`<main className="settings-layout">` holding `<nav aria-label="Settings">` with `NavLink`s from `PERSONAL`, then, when `useMe().data?.is_admin`, a non-link "Admin" heading and the `ADMIN` links; then `<Outlet />`). Wrap each admin panel in a small route element that gives it `PageHeader` plus the `panel sec` look (`ServerSettingsForm`, `InvitesPanel`, `DictionaryPanel`, `BackupPanel` are existing components in `web/src/admin/`).
- [ ] **Step 6: Wire `App.tsx`** per the spec's route table (layout route `settings`; admin children under an `AdminOnly` layout route; redirects with `<Navigate replace>`; `admin` path redirects to `/settings/admin/server`). Header in `Shell.tsx`: one `NavLink to="/settings/editor"` labelled "Settings" with `aria-current="page"` when `isSettingsPath(pathname)`; remove the five old links. `RunningJobs.tsx`: `dict_download` goes to `/settings/admin/dictionary`.
- [ ] **Step 7: Styles** in `settings.css`: two-column layout (sidebar fixed width, content flexible); below the breakpoint `narrow.spec.ts` already uses, the sidebar is a horizontally scrollable row. Tokens only.
- [ ] **Step 8: Verify** `cd web && npx tsc --noEmit && npm test`. Expected: clean, all pass.
- [ ] **Step 9: Commit** `feat(settings): one Settings page with a sidebar`.

### Task 2: End-to-end specs

**Files:**
- Create: `web/e2e/settings-sidebar.spec.ts`
- Modify: `web/e2e/admin.spec.ts`, `web/e2e/dictionaries.spec.ts`, `web/e2e/backup.spec.ts`, `web/e2e/narrow.spec.ts`

**Interfaces:**
- Consumes: the routes and `nav aria-label="Settings"` from Task 1. Use the sign-in helper pattern at the top of `admin.spec.ts`.

- [ ] **Step 1: Update existing specs.** `admin.spec.ts`: first test clicks header link "Settings", then the sidebar's "Server" link; the other `goto("/admin")` become `goto("/settings/admin/invites")` / `/settings/admin/dictionary`. `dictionaries.spec.ts` and `backup.spec.ts`: `goto("/settings/admin/dictionary")` and `/settings/admin/backup`. `narrow.spec.ts`: add `/settings/admin/server` to its path list.
- [ ] **Step 2: Write `settings-sidebar.spec.ts`** with tests: `"each sidebar entry opens its section"` (click every entry; heading visible; entry has `aria-current="page"`; header Settings link current), `"old URLs land in the sidebar"` (`/settings` -> `/settings/editor`; `/admin` -> `/settings/admin/server`), `"a non-admin sees no Admin group"` (create or use a non-admin e2e account if the seed has one; otherwise intercept `**/api/auth/me` to return `is_admin: false` and assert no "Admin" heading and that `goto("/settings/admin/server")` shows "Admin only.").
- [ ] **Step 3: Run** `cd web && npm run e2e -- admin dictionaries backup narrow settings-sidebar settings-late-load mt-settings publish editor`. Expected: all pass (venv active, Postgres up, `ta_e2e` reset, per `CLAUDE.md`).
- [ ] **Step 4: Update `CLAUDE.md`**: a short "Settings page" paragraph (routes, sidebar, admin group) and delete the TODO entry "Settings: one Settings page with tabs".
- [ ] **Step 5: Commit** `test(settings): sidebar e2e and moved admin URLs`.
