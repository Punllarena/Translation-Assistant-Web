# Handoff — series page table, WordPress tags, Ollama, delete (plan `2026-10-30-series-page-table.md`)

Branch: `opencode/series-page-table` (from `main`).

Spec: `docs/superpowers/specs/2026-10-30-series-page-revision-design.md`. This is the first of the three
2026-10-30 plans; the other two (`2026-10-30-series-gallery.md`, `2026-10-30-account-saved-views.md`) were
committed with the spec as docs and are untouched.

Status: Tasks 1–9 done and committed; the WordPress plugin check (Task 5 step 3) says Reschedule is safe to
ship, so no part of Task 5 was skipped.

## Commits

```
375c9b0 test(e2e): series page table; docs
c1f4b0d feat(series): Ollama in Tools, delete asks about images
d027fd8 feat(series): volume summary line and progress bars
f781963 feat(series): select mode, quick picks and a sticky selection bar
a992885 feat(series): WordPress tag states, detail popover and Reschedule
cadefa9 feat(series): toggleable chapter columns saved on the account
5094063 feat(settings): validate series_columns
b0cba11 feat(library): delete a chapter and move its images to the Illustrations chapter
11f0d13 feat(library): character, word and Ollama counts on the chapter list
4187316 docs(series): series page revision spec and plans
```

(`git log --oneline main..HEAD`. The commit that adds this handoff file follows the list, so it is not in it.)

## The WordPress plugin check (Task 5, step 3)

**Result: re-publishing an existing chapter with a new `publish_date` moves the post's date and keeps it
scheduled, so Reschedule is implemented as the plan describes.**

What I read (read only; nothing in the plugin repo was changed):

- `plugins/translation-assistant-publisher/includes/class-publisher.php`
  - `TAP_Publisher::publish()` (existing chapter branch, lines 66–127) routes an already-published chapter to
    `update_chapter_page()` for the reader page and `update_post()` for the teaser post.
  - `TAP_Publisher::update_chapter_page()` (lines 475–510) and `TAP_Publisher::update_post()` (lines 361–386)
    both build `$args` and call `TAP_Publisher::apply_schedule($args, $data, true)` before `wp_update_post()`.
  - `TAP_Publisher::apply_schedule()` (lines 317–335): with a non-empty `publish_date` it sets
    `post_date_gmt`, `post_date` (converted to `wp_timezone()`) and `post_status = 'future'`, on create *and*
    on update; with none it sets `publish` and `current_time('mysql')`.
- `translation-assistant-publisher.php`: `tap_validate_fields()` (lines 81–90) accepts `publish_date` on every
  request, and `tap_handle_publish()` (95–134) passes the body to `publish()` unchanged.

So a second `/publish` with a different `publish_date` sends new `post_date`/`post_date_gmt` with
`post_status = 'future'` to `wp_update_post()` for both the page and the post. WordPress reschedules
`publish_future_post` on a `future_to_future` transition, so the chapter stays scheduled at the new time.
The plugin has no test for *rescheduling* (`tests/test-publish-legacy.php::test_schedule_then_unschedule` covers
schedule → unschedule only); ta-web already sends `publish_date` on a re-publish (`api/core/wp.py` `payload()`),
so the SPA side needed nothing new in `api/`.

## Per task

**Task 1 — done.** `list_documents` gained the three counts in the same grouped query (no per-row queries):
`char_count` over non-blank lines (whitespace and U+3000 stripped), `word_count` from the translations
(blank translations skipped), `ollama_waiting` from a `ollama_suggestions` join where `text IS NOT NULL` —
the predicate `api/ollama/store.py` uses. `DocumentListItem` and `schema.d.ts` regenerated. Tests in
`tests/test_documents.py` (4 new).

**Task 2 — done.** `api/image_moves.py` (`free_name`, `check_can_move`, `move_images`) and
`DELETE /documents/{id}?images=delete|move`. `illustrations._syosetu` is now the public `is_syosetu`.
`tests/test_image_moves.py` (8 new) covers the append order with a renamed clash, creating the chapter,
the three 409s, the unchanged default and a move with no images. The move re-points rows (no copies), keeps
`exclude_export`, flushes one at a time so ids keep the order, and `arrange()` runs as before.

**Task 3 — done.** `api/settings_rules.py` (`check`, `SERIES_COLUMNS`, `BAD_COLUMNS`, and `BAD_SCHEDULE` moved
there from the router); `put_settings` loops `check` over the body. Tests: **deviation** — added to the existing
`tests/test_settings_api.py` instead of creating `tests/test_settings.py`, because that module already owns
`PUT /settings` and a near-identical second file would be confusing.

**Task 4 — done.** `useAccountPref` (localStorage paint, account wins, a browser-only value PUT up once,
`set` writes both plus the query cache), `chapterColumns.ts` (15 ids, defaults, `parseColumns`, `shownColumns`,
`toggleColumn`), `chapterCells.tsx` (`cell`, `cellClass`, `HEADERS`), the Columns ▾ `menuitemcheckbox` menu,
fixed table layout with an ellipsised title and a horizontal wrapper. Tests: `chapterColumns.test.ts`.
**Deviations**: (a) `web/src/library/queuedForOllama.ts` + test is a file the plan's map did not list — the
"Queued" state needed one pure, testable place for "documents / volume / series item → chapter ids";
(b) in Task 4 the table passed `shownColumns(chosen, true)` because `useWpConfigured` arrives in Task 5; Task 5
switched it to the real flag.

**Task 5 — done** (all of it; see the plugin check). `wpTag.ts` (state, labels, tones, `menuPublishLabel`),
`WpTagButton.tsx` (the tag button and its popover), `useWpConfigured.ts`, `PublishDialog` modes
(`publish` / `reschedule` / `update`; Reschedule forces Schedule on, prefills from `wp_scheduled_for`, sends
`confirm_republish: true` itself; the 409 retry is now a `ConfirmDialog` "Publish anyway?"), `ChapterMenu`,
`SeriesPage` (no WordPress tab without a credential), selection-bar Publish… hidden without one.
**Deviations**: (a) the popover is `position: fixed`, placed from the button's rect — an absolutely positioned
popover inside `.chapters-wrap` (an `overflow-x: auto` container) is clipped; (b) a scheduled **Illustrations**
chapter's menu item reads "Update post…", not `menuPublishLabel`'s "Reschedule…", because it has no Reschedule;
(c) `useWpConfigured` uses the query key `["wp", "credentials"]` so the WordPress settings page's save
invalidates it (that page fetches the same `GET /credentials`); (d) the publish mode is frozen in `ChapterMenu`
when the dialog opens: e2e showed the dialog renaming itself from "Publish to WordPress" to "Update post" after
the chapter published, while showing "Published!" — the first full e2e run failed on exactly that.

**Task 6 — done.** `chapterPicks.ts` (quick picks; the `rangeToggle` "shown rows only" test repeated from the
plan), `useStatusCheck.ts` (first 50, sequential, `invalidateLibrary` after each, Stop finishes the request in
flight), select mode in `ChapterTable` (row click, shift range over rendered rows, grip hidden, title as text,
Esc / Done / Clear leave it), the selection bar moved out of `<thead>` into a sticky `div.selbar` above the
wrapper with `--selbar-h` measured by a `ResizeObserver`, Queue / Flush removed from it.
**Deviations**: (a) the bar shows while selecting even with 0 selected (otherwise Select ▾ would be
unreachable) and its action buttons are disabled at 0; (b) `ChapterTable` keeps a `checkedCount` for
"Checked the first 50 of N" rather than widening `useStatusCheck`'s interface; (c) a click on the WordPress tag
in select mode also toggles the row — only `.ch-menu` clicks are excluded, as the plan says.

**Task 7 — done.** `volumeSummary.ts` (`volumeSummary`, `summaryText`; "Published?" counts as posted, `next` is
the earliest scheduled time still ahead), the summary line above the bar, and the progress cell as
`pbar` + percent in token colours. Tests: `volumeSummary.test.ts`.

**Task 8 — done.** `deletePlan.ts` (+ test), `DeleteChaptersDialog.tsx` used by both the selection bar and the
chapter ⋯ menu (radios when images exist, "Move their images…" only when something can move, the stuck note,
`images=move` only for the chapters that can), and the Tools tab's Ollama section (queue the series, flush
behind a ConfirmDialog). **Deviation**: `VolumesTab.tsx` still carries its series-wide Queue/Flush toolbar; the
plan does not list that file, but the spec's goal says series-wide actions live in Tools, so those two places
now duplicate each other — a reviewer may want to drop the toolbar's copy.

**Task 9 — done.** Seed: `Series page spec`, one volume, three chapters (`Spec one`, a 200-character `長…`,
`Spec image` with a 1×1 PNG `document_images` row). `web/e2e/series-page.spec.ts` covers select mode (row click
does not navigate), shift-click range, no page overflow at 1280×800 and 375×812, Columns ▾ Images surviving a
reload (then restored to the defaults for the rest of the suite), and deleting the image chapter through
"Move their images…" until the Illustrations chapter appears. `docs/TODO.md`: the old "Series page" section is
gone and "WordPress plugin: series-wide status route" is added (newest first). `CLAUDE.md`: a "Series page
revision" paragraph. **Deviations**: (a) `web/e2e/library.spec.ts`'s bulk-delete test now clicks **Clear** after
Cancel before asserting the title links: ticking a checkbox enters select mode, where titles are text, not
links. The assertions themselves are unchanged (Cancel still keeps both chapters). (b) Ticking a checkbox now
also sets the shift-range anchor (a small `ChapterTable` change in this commit) — without it, a shift-click
after a checkbox tick had no anchor to range from. (c) The `ChapterMenu` mode freeze fix from the first full
e2e run is in this commit too.

## Final verification

- `ruff check .` — clean.
- `pytest` (full) — **1722 passed** in 391 s (exit 0).
- `cd web && npm test` — **53 files, 373 tests pass**.
- `cd web && npm run build` — `tsc --noEmit` and `vite build` clean (only the pre-existing chunk-size warning).
- `cd web && npm run e2e` (full, `TA_E2E_DATABASE_URL=…@127.0.0.1:5432/ta_e2e`) — **86 passed** in 3.0 m.
  `npm run e2e -- series-page` alone on a fresh run — 5 passed.
- Nothing is pushed; no pull request.

## Notes for review

- **Where to read first**: `api/image_moves.py` (the rename-instead-of-drop rule and the 409 order),
  `web/src/publish/WpTagButton.tsx` (fixed-position popover, the invalidate-on-check effect),
  `web/src/settings/useAccountPref.ts` (the write-up-once migration and the effect dependencies that keep it
  from looping), `web/src/library/ChapterTable.tsx` (select mode and the bar measurement).
- **Guessed / decided by me where the plan was silent**:
  - `char_count`/`word_count` count only non-blank source lines, as the plan's "over non-blank lines only" says;
    a translated line whose source is blank is not counted in words.
  - The 409 `images=move` checks run before loading the images, so `?images=move` on a loose or syosetu chapter
    with no images is still a 409 (the plan's order; the SPA only sends `move` when there is an image).
  - Column widths and the bar's layout (`ch-tools`, `ch-summary`, `.pbar`, `.wp-pop`, `.badge.muted`,
    `menuitemcheckbox` ticks in `controls.css`) are my calls inside the tokens.
  - The delete dialog uses ConfirmDialog with a radio group in its message; the wording is the plan's
    ("Move their images…", "N chapters are outside a volume or in a syosetu series; their images will be
    deleted."), "their" even for one chapter so the e2e text matches.
  - The summary line sits between the Columns/Select tools and the sticky bar; the progress bar is in the
    Progress cell, so "45%" now follows a 3em bar.
- **Known limitation**: the sticky `<thead>` sits inside `.chapters-wrap` (`overflow-x: auto`), which is a
  scroll container, so on most browsers it sticks to that wrapper's (non-vertical) scrollport — i.e. the header
  does not actually stay on screen while the page scrolls. The plan asks for both the wrapper and the sticky
  header; making it work would need a different overflow strategy (e.g. no wrapper, or a measured sticky
  offset). Worth deciding in review.
- **E2E ordering now matters more**: `series.spec.ts`'s WordPress-tab test needs a `wordpress` credential, which
  `publish.spec.ts` creates and `series.spec.ts` only has because it runs later in the alphabetical order. It
  was independent before this plan (the tab was always shown). Running `npm run e2e -- series` on a fresh
  database will fail on that tab; the full run is fine.
- `web/openapi.json` is gitignored; `npm run gen:api` was run after each API change and `schema.d.ts` is
  committed with the API commits.
- `docs/superpowers/handoff/` is in `.gitignore` (no handoff has ever been tracked). This file was committed
  with `git add -f`, as the task asked; if handoffs are meant to stay local, drop that commit.
- The `series_columns` write-up happens once per mount (a ref guard), which also keeps React 19 StrictMode's
  double effect from sending two PUTs.
- The plugin check was done by reading the plugin only (no PHP/WP run locally); the plugin's own tests have no
  reschedule case, so the behaviour rests on `apply_schedule` plus WordPress's `future_to_future` rescheduling.
