# Handoff: settings sidebar

Branch `opencode/settings-sidebar`, worktree of `C:\dev\ta-web`. Front end only, no API or database change.
Commits:

- `ed7a4a1` feat(settings): one Settings page with a sidebar
- `39bd068` test(settings): sidebar e2e and moved admin URLs
- the commit that adds this note

Plan: `docs/superpowers/plans/2026-10-31-settings-sidebar.md` (all boxes ticked). Spec:
`docs/superpowers/specs/2026-10-31-settings-sidebar-design.md`.

## Task 1 — layout, routes, header, redirects

Done as written.

- `web/src/settings/settingsNav.ts`: `PERSONAL` (Editor, Machine translation, WordPress, Shortcuts),
  `ADMIN` (Server, Invites, Dictionary, Backup & restore), `isSettingsPath`.
- `web/src/settings/SettingsLayout.tsx`: `<main className="settings-layout">`
  with `<nav aria-label="Settings">`, `NavLink`s, the non-link "Admin" heading when `useMe().data?.is_admin`, then
  `<Outlet />` in a `div.settings-content`.
- `web/src/settings/AdminOnly.tsx`: the one guard for the four admin children; a non-admin sees
  `p.box.danger` "Admin only." inside the layout (while `/auth/me` is still pending it shows `Loading…`,
  like `RequireAuth`).
- `web/src/settings/AdminSections.tsx`: `AdminServer`, `AdminInvites`, `AdminDictionary`, `AdminBackup`, each a
  `div.settings` with a `PageHeader` (h1 Server / Invites / Dictionary / Backup & restore). `ServerSettingsForm`
  is a bare form, so `AdminServer` wraps it in `section.panel.sec` with `h2#server-h`; the other three panels were
  already `panel.sec` and are used unchanged.
- `App.tsx`: `settings` layout route; index and `admin` children are `<Navigate replace>` to
  `/settings/editor` and `/settings/admin/server`; the four admin paths sit under the `AdminOnly` layout route;
  the top-level `admin` route redirects with `replace`; `settings/profiles` still redirects to Editor.
- `Shell.tsx`: one `Link to="/settings/editor"` labelled Settings with custom `aria-current="page"` from
  `isSettingsPath(pathname)`; the five old links are gone. Library / Statistics / Jobs unchanged.
- `RunningJobs.tsx`: `dict_download` opens `/settings/admin/dictionary`.
- Roots of `EditorSettingsPage`, `MtSettingsPage`, `WpSettingsPage`, `ShortcutsPage` changed `<main>` -> `<div>`
  (classes kept). `web/src/admin/AdminPage.tsx` deleted (nothing else imported it).
- `settings.css`: `.settings-layout` grid, sidebar links with `aria-current` styling, Admin heading; below
  `60rem` (the breakpoint the other stylesheets use) the sidebar becomes a horizontally scrollable row.
  Tokens only, no literal colours.

## Task 2 — end-to-end specs

- `admin.spec.ts`: first test clicks the header Settings link then the sidebar's Server link; the other two use
  `/settings/admin/invites` and `/settings/admin/dictionary`.
- `dictionaries.spec.ts` and `backup.spec.ts`: both `goto("/admin")` calls each point at
  `/settings/admin/dictionary` / `/settings/admin/backup`.
- `narrow.spec.ts`: `/settings/admin/server` added to the phone path list.
- New `web/e2e/settings-sidebar.spec.ts`: "each sidebar entry opens its section" (all eight entries, h1 visible,
  entry `aria-current="page"`, header Settings current), "old URLs land in the sidebar" (`/settings` ->
  `/settings/editor` and Back leaves Settings, proving `replace`; `/admin` -> `/settings/admin/server`), and
  "a non-admin sees no Admin group" (intercepts `**/api/auth/me` with `is_admin: false`, asserts no "Admin"
  heading, no Server link, "Admin only." at `/settings/admin/server`, and that no `/api/admin/` request fires).
- `CLAUDE.md`: new "Settings page" paragraph; `docs/TODO.md`: the "Settings: one Settings page with tabs" entry
  deleted.

### One change outside the plan's file list

`web/e2e/mt-settings.spec.ts` was not in the plan's modify list, but it clicked the header link
`"Machine translation"`, which Task 1 removes, so the plan's own Step 3 (run `mt-settings`) could not pass
without it. I changed that one line to `page.goto("/settings/mt")`. Nothing else in the spec changed.

## Commands run and their real results

All from the worktree root unless noted.

1. `cd web; npm ci` — the fresh worktree had no `node_modules`. Output: `added 102 packages` (later `npm test`
   ran fine).
2. `cd web; npx vitest run src/settings/settingsNav.test.ts` before `settingsNav.ts` existed — **FAIL** as
   expected:
   `Error: Cannot find module './settingsNav' imported from .../settingsNav.test.ts`,
   `Test Files 1 failed (1)`, `Tests no tests`.
3. Same command after implementing — **PASS**: `Test Files 1 passed (1)`, `Tests 3 passed (3)`.
4. `cd web; npx tsc --noEmit` — clean, no output (exit 0).
5. `cd web; npm test` — **PASS**: `Test Files 56 passed (56)`, `Tests 397 passed (397)`.
6. Environment for Playwright:
   - `docker compose up -d postgres` **failed**: `Bind for 127.0.0.1:5432 failed: port is already allocated`.
     The main repo's `ta-web-postgres-1` container already publishes `127.0.0.1:5432`, so I used it (and
     removed the half-created `t3-860a653f-postgres-1` container this command made). Postgres was up at
     `127.0.0.1:5432` for the e2e run.
   - `C:\dev\ta-web\.venv\Scripts` put on `PATH` (no `.venv` in this worktree); imports resolve to this
     worktree's `api/` because the e2e seed and uvicorn run from its cwd.
   - `$env:TA_DATABASE_URL="postgresql+psycopg://ta:ta@127.0.0.1:5432/ta_test"`,
     `$env:TA_E2E_DATABASE_URL="postgresql+psycopg://ta:ta@127.0.0.1:5432/ta_e2e"`.
7. `cd web; npm run e2e -- admin dictionaries backup narrow settings-sidebar settings-late-load mt-settings publish editor`
   — **PASS**: `31 passed (1.7m)` (the `editor` filter also matched `editor-nav.spec.ts`). The API and Vite
   webServers started normally from `playwright.config.ts`, `ta_e2e` was reset, and no test was retried or skipped.
8. `cd web; npx tsc --noEmit` and `npm test` again after the e2e edits — same clean/pass result as 4 and 5.

Not run, per instructions: `pytest` (another agent may use `ta_test`) and `ruff check .` (no Python changed).

## Not verified

- I did not open the app in a browser beyond Playwright; visual detail (sidebar width, spacing, dark theme) is
  only covered by the token-only CSS and by `narrow.spec.ts`'s no-horizontal-scroll check at 390 px.
- The full Playwright suite was not run: only the eight named filters plus the new spec, as the plan's Step 3 says.
- No pytest/ruff, as above.

## Decisions made

- Sidebar breakpoint is `60rem`, matching `base.css` / `shell.css` / `controls.css` (the phone spec runs at 390 px,
  far below it).
- The header link is a `Link` with a custom `aria-current` (the Library link's pattern) rather than a `NavLink`,
  because `NavLink` would only mark `/settings/editor`.
- Admin wrappers live in one `AdminSections.tsx`; `InvitesPanel` / `DictionaryPanel` / `BackupPanel` were not
  changed because they already render `section.panel.sec`.
- The non-admin e2e case intercepts `/api/auth/me` instead of seeding a second account: `tools/e2e_seed.py` seeds
  only the admin, and the plan allows the interception.
- The new spec also checks that Back leaves Settings after the `/settings` redirect, to cover the plan's review
  focus on `replace`; that is the only assertion added beyond the plan's wording.
