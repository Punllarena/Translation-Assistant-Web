# Account-saved Library view, sort and filters — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Library's view (bookshelf/list), sort and filters are saved on the account, like the theme, and a
browser's existing choices are copied up the first time.

**Architecture:** Three user settings (`library_view`, `library_sort`, `library_filters`) validated in
`api/settings_rules.py`; `Library.tsx` reads them through `useAccountPref` (both from the first plan), with the
existing `localStorage` keys kept as the fast first paint.

**Tech Stack:** FastAPI; React 19, TanStack Query; vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-series-page-revision-design.md` §5. Depends on the first plan,
`2026-10-30-series-page-table.md` (Task 3 `settings_rules.check`, Task 4 `useAccountPref`).

## Global Constraints

- Keys: `library_view` (`"shelf" | "list"`), `library_sort` (`{key, dir}`, key one of `modified`, `syosetu`,
  `added`, `title`, `progress`, `published`, `chapters`; dir `asc | desc`), `library_filters`
  (`{sources: [syosetu|epub|other], statuses: [ongoing|on_hold|dropped|completed], wordpress: any|published|none, archived: hide|include|only}`).
- `localStorage` keys stay `ta.libraryView`, `ta.librarySort`, `ta.libraryFilters`.
- The account's value wins once `/settings` loads; with no account value and a browser value, the browser's is
  written up once (first browser wins).
- `null` for any key clears it (allowed by the API).

## Review Focus

1. A saved value from an older build with an unknown sort key or filter tick — the SPA falls back per field
   (existing `readSort` / `readFilters` rules), never a blank Library. Test in Task 2.
2. `/settings` failing to load — the Library keeps the `localStorage` value and never writes up. Test in Task 2.
3. Two quick changes before the first PUT returns — the last choice is what the account keeps (writes are in
   order; the cache is updated optimistically). Test in Task 2.
4. A browser with blocked storage — choices apply for the page load and still save to the account. Test in Task 2.
5. The migration PUT racing an explicit change on first load — the explicit change wins. Test in Task 2.

---

### Task 1: Validate the three library settings

**Files:**
- Modify: `api/settings_rules.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `settings_rules.check` (first plan, Task 3).
- Produces: rules for `library_view`, `library_sort`, `library_filters` (shapes in Global Constraints; extra keys
  in the objects are 422; list members must be known and are 422 otherwise).

- [ ] **Step 1: Failing tests**

```python
def test_library_settings_round_trip(app_client, me):
    body = {"library_view": "list", "library_sort": {"key": "title", "dir": "asc"},
            "library_filters": {"sources": ["epub"], "statuses": [], "wordpress": "any", "archived": "hide"}}
    r = app_client.put("/settings", json=body)
    assert r.status_code == 200 and {k: r.json()[k] for k in body} == body

@pytest.mark.parametrize("key,bad", [
    ("library_view", "grid"),
    ("library_sort", {"key": "nope", "dir": "asc"}),
    ("library_sort", {"key": "title"}),
    ("library_filters", {"sources": ["web"], "statuses": [], "wordpress": "any", "archived": "hide"}),
    ("library_filters", {"sources": [], "statuses": [], "wordpress": "any", "archived": "hide", "x": 1}),
])
def test_library_settings_rejected(app_client, me, key, bad):
    assert app_client.put("/settings", json={key: bad}).status_code == 422
```

- [ ] **Step 2: Run** — `pytest tests/test_settings.py -v` — FAIL.
- [ ] **Step 3: Implement** the three rules.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(settings): validate the Library's saved view, sort and filters"`.

---

### Task 2: Library reads and writes the account

**Files:**
- Modify: `web/src/library/libraryPrefs.ts`, `libraryPrefs.test.ts`, `web/src/library/viewPref.ts`, `viewPref.test.ts`,
  `web/src/library/Library.tsx`, `web/src/settings/useAccountPref.ts` (if a test below shows a gap)
- Test: `web/src/settings/useAccountPref.test.ts` (pure helper only — see Step 3), `web/e2e/library-filters.spec.ts`

**Interfaces:**
- Produces: `parseView(v: unknown): LibraryView`, `parseSort(v: unknown): LibrarySort`,
  `parseFilters(v: unknown): LibraryFilters` (the field-by-field fallbacks `readSort` / `readFilters` already
  apply, now on any value); `readSort` etc. become `parseSort(readJson(...))`.
  `resolvePref<T>(account: unknown, hasAccount: boolean, local: T | null, parse: (v: unknown) => T, fallback: T): { value: T; upload: T | null }`
  — exported from `useAccountPref.ts` so the rule is testable without React: account present → its parsed value,
  no upload; absent and `local` set → `local`, upload `local`; neither → fallback, no upload.

- [ ] **Step 1: Failing vitest**

```ts
test("parseSort falls back per field", () => {
  expect(parseSort({ key: "gone", dir: "asc" })).toEqual(DEFAULT_SORT);
  expect(parseSort({ key: "title", dir: "asc" })).toEqual({ key: "title", dir: "asc" });
});
test("parseFilters drops unknown ticks", () => {
  expect(parseFilters({ sources: ["epub", "web"], statuses: [], wordpress: "x", archived: "only" }))
    .toEqual({ ...DEFAULT_FILTERS, sources: ["epub"], archived: "only" });
});
test("account wins", () => expect(resolvePref("list", true, "shelf", parseView, "shelf")).toEqual({ value: "list", upload: null }));
test("browser value is uploaded once when the account has none", () =>
  expect(resolvePref(undefined, false, "list", parseView, "shelf")).toEqual({ value: "list", upload: "list" }));
test("nothing anywhere", () => expect(resolvePref(undefined, false, null, parseView, "shelf")).toEqual({ value: "shelf", upload: null }));
```

- [ ] **Step 2: Run** — `cd web && npx vitest run src/library src/settings` — FAIL.
- [ ] **Step 3: Implement.** `useAccountPref` (from the first plan) uses `resolvePref`; the upload is skipped when
  the user changed the value before settings loaded (track a `touched` ref), and never runs when `/settings`
  errored. Writes go through one `useMutation` with `onMutate` updating the `["settings"]` cache, so the latest
  value is what shows. `Library.tsx` swaps its three `useState`s for `useAccountPref` with
  `{ key: "library_view", local: "ta.libraryView", parse: parseView, fallback: "shelf" }` and the like.
- [ ] **Step 4: E2E** — in `library-filters.spec.ts` add: set list view and a filter, clear `localStorage` in the
  page, reload → the list view and the filter are back (from the account).
- [ ] **Step 5: Run** — `npx vitest run`, `npm run build`, `npm run e2e -- library` — PASS.
- [ ] **Step 6: Docs** — `CLAUDE.md` Library redesign / filters paragraphs: the prefs are now account settings
  (`library_view`, `library_sort`, `library_filters`) mirrored in `localStorage`.
- [ ] **Step 7: Full check and commit** — `ruff check .`, `pytest`, `npm test`;
  `git commit -m "feat(library): view, sort and filters saved on the account"`.
