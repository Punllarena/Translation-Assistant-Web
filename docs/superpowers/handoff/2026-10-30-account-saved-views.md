# Handoff — account-saved Library view, sort and filters (plan `2026-10-30-account-saved-views.md`)

Branch: `opencode/account-saved-views`, created from the tip of `opencode/series-page-table`
(`8cc1d792d1faa5629115d07359d069cdb5b50c3d`), not from `main` and not from the gallery branch.

Spec: `docs/superpowers/specs/2026-10-30-series-page-revision-design.md` §5.

Status: both tasks done and committed. The two dependency files required before Task 1 existed on the
base branch: `api/settings_rules.py` (`check`, `series_columns`) and
`web/src/settings/useAccountPref.ts`.

## Commits

```
1f95c19 feat(library): view, sort and filters saved on the account
e3512d5 feat(settings): validate the Library's saved view, sort and filters
```

(`git log --oneline opencode/series-page-table..HEAD`. The commit that adds this handoff file follows
the list, so it is not in it.)

## Per task

**Task 1 — done.** The three rules (`library_view`, `library_sort`, `library_filters`) are in
`api/settings_rules.py`; `library_view` is `shelf`/`list`, `library_sort` is exactly
`{key, dir}` with the seven sort keys and `asc`/`desc`, `library_filters` is exactly
`{sources, statuses, wordpress, archived}` with known list members and known enum values. Anything
else is 422; `null` still clears (the shared `check` returns None for null first).

Deviations:
- Tests went into `tests/test_settings_api.py`, not the plan's `tests/test_settings.py`: there is no
  such file on this branch, and every settings-API rule test (including `series_columns`) lives in
  `test_settings_api.py`.
- More rejection cases than the plan's list: a non-list view, non-object values, unknown status /
  WordPress / archived values, missing filter keys, extra keys on both `library_sort` and
  `library_filters`, and a non-string list member. These follow the Global Constraints ("extra keys
  in the objects are 422; list members must be known and are 422 otherwise"), which the plan's five
  cases alone did not pin down.

**Task 2 — done.** `parseView`, `parseSort`, `parseFilters` exist and the old readers
(`readView` / `readSort` / `readFilters`) now delegate to them, so a saved value from an older build
falls back per field. `resolvePref` is exported from `useAccountPref.ts` and the hook uses it.
`Library.tsx` reads the three values through `useAccountPref` and no longer has its own
`useState` + `write*` pairs.

Deviations:
- The plan's E2E step asks for one new scenario (account wins when this browser has none). I added a
  second, "a browser's existing choice is written up once when the account has none", because the
  migration is a Global Constraint and item 5 of Review Focus and was otherwise untested. It seeds
  `ta.libraryView` / `ta.librarySort` directly, reloads, asserts the account got them, then clears
  the browser and asserts a fresh browser takes them back.
- `resetPrefs` in `web/e2e/library-filters.spec.ts` now also `DELETE`s the three account settings,
  and every test in the file resets before it starts. Without that, a filter saved to the account by
  one test would leak into the next: the e2e database is reset once per run, not per test.
- `CLAUDE.md` (Step 6) now says the Library's view, sort and filters are account settings mirrored
  in `localStorage`, with the validation location and both spec links.
- The plan names Task 2 Step 3's test as "pure helper only"; the hook's own refs (`touched`,
  `migrated`) and the serialised writes are not unit-tested (the vitest environment is `node`, with
  no jsdom or React Testing Library). They are covered by reasoning in Notes for review, the two E2E
  scenarios, and review focus 3/5 below.

## Changes to `web/src/settings/useAccountPref.ts` and why

1. **`localFormat?: "json" | "text"` (default JSON).** `ta.libraryView` has always held a bare
   string (`list`), written by `viewPref.writeView`, not JSON. The old hook always did
   `JSON.parse`/`JSON.stringify`, so with that key it would have thrown on read (no first paint, and
   no migration upload) and written `"list"` (quoted) on set. `Library.tsx` passes
   `localFormat: "text"` for the view and leaves the other two as JSON, so the bytes in
   `ta.libraryView` stay exactly what older builds wrote and read.
2. **`resolvePref` extracted.** Pure rule: account present → parsed account value, no upload;
   account absent with a browser value → the browser value and that value as the upload; neither →
   the fallback and no upload. The hook and the test share it.
3. **One `useMutation`, optimistic `onMutate`, scoped writes.** `onMutate` puts the new value in the
   `["settings"]` cache so the UI never flashes back. The PUT response is deliberately *not* written
   back to the cache: a slow earlier response must not overwrite a newer choice. `scope: { id: key }`
   serialises the PUTs per key in call order, so two quick changes end with the last one on the
   account, and the first-load migration PUT can never land after an explicit change.
4. **`touched` ref.** Set by `set()`; the load effect returns as soon as it is true. A `GET
   /settings` that started before the user's change therefore cannot overwrite that change, and no
   migration upload happens after it.
5. **`migrated` ref and `settings.isSuccess`.** The browser-to-account upload runs at most once per
   hook mount and only after a *successful* `/settings` load; a failed load leaves the browser value
   in charge and writes nothing up.

The previous public shape — `useAccountPref({ key, local, parse, fallback })` returning
`[value, set]` — is unchanged, so `ChapterTable.tsx` (`series_columns`) needed no edit.

## Final verification

- `ruff check .` — all checks passed (run with the venv).
- `pytest` — full suite, exit 0, 1737 tests collected and all passing
  (`TA_DATABASE_URL=…@127.0.0.1:5432/ta_test`).
- `cd web && npm test` — 54 files, 379 tests passed.
- `cd web && npm run build` — `tsc --noEmit` and vite build succeeded (only the pre-existing
  >500 kB chunk warning).
- `cd web && npm run e2e -- library` — 9 passed (3 old library-filters, 2 new ones, 4 `library.spec`),
  with `TA_E2E_DATABASE_URL=postgresql+psycopg://ta:ta@127.0.0.1:5432/ta_e2e` and the venv on `PATH`
  (the Playwright webServer shells out to `python -m tools.e2e_seed`).

## Notes for review

**How the first-load upload avoids overwriting a change the user made before `/settings` loaded.**
The hook reads `touched` first thing in the load effect. `set()` sets it synchronously in the event
handler, before its PUT is queued, so any account snapshot that arrives afterwards (even one whose
GET was already in flight) is ignored: the user's value stays on screen and the PUT already carries
it. The complementary race — the migration PUT and a click in the same window — is closed twice:
`touched` skips the migration if the click came first, and the mutation `scope` puts the writes in
call order if the migration fired first, so the explicit change is the last write on the account.
`migrated` keeps a second `settings` cache update from re-uploading.

**What I guessed.**
- That `ta.librarySort` / `ta.libraryFilters` are JSON and only `ta.libraryView` is a bare string
  (checked against `viewPref.ts` and existing tests); hence the per-hook `localFormat` rather than
  changing the view key's format.
- That a failed PUT should leave the optimistic cache value alone (the old hook did the same,
  swallowing errors) rather than reverting; a later refetch of `/settings` will restore the account's
  value.
- That the server's exact-key-set validation is the right reading of "extra keys in the objects are
  422" for `library_sort` too, not only `library_filters`.
- That `resetPrefs` deleting account settings is the right cleanup for the E2E suite (a shared user
  account and a database reset once per run).

**Where to read first.**
1. `web/src/settings/useAccountPref.ts` — the whole first-paint / account-wins / one-time-upload rule
   and the write path.
2. `web/src/library/Library.tsx` — the three hook calls and the `localFormat: "text"` on the view.
3. `api/settings_rules.py` — `_check_sort` / `_check_filters` and the three key branches.
4. `web/e2e/library-filters.spec.ts` — the two new scenarios and why `resetPrefs` is now async.
