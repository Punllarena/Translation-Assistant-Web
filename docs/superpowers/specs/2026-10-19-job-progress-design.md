# Job progress you can trust — design

Date: 2026-10-19. Status: approved for planning.

## Why

Importing a real desktop library (119 MB `ta.db`, 1,601 chapters, 480,716 lines) through the
setup wizard sat on "Checking the library" with an empty bar for 45+ minutes. Nothing was wrong:
the dry run was working through the lines at ~150 rows/s. But the page could not tell "slow"
from "dead", so it looked stuck. Two causes:

- `tadb_import` calls `ctx.progress(0, 1, "Checking the library")` once, then nothing until it
  ends. The bar is pinned at 0 of 1.
- Every row is inserted in its own SAVEPOINT (`_add` in `api/core/tadb_rows.py`), which is what
  makes it take 45 minutes per pass (dry run, then the same again for the real import).

Goal: anyone watching a job can see it moving, roughly how long is left, and that they can walk
away; and the ta.db import itself takes minutes, not most of an hour.

## Goals

1. **Real progress.** Jobs report counts while they work; the page shows them with elapsed time
   and an estimate of what is left. Unknown totals show an animated bar, never a frozen empty one.
2. **Background, honestly.** Pages that start a job say it runs on the server, and picking the
   page up again later shows the job (or its finished dry run) instead of a blank form.
3. **Running-jobs indicator.** A small control in the app header shows how many of your jobs are
   running and lists them with progress and a link to where each lives.
4. **Faster ta.db import.** Lines are inserted in batches; per-row inserts only as a fallback for a
   batch the database rejects.

## Non-goals

- A jobs page or job history. Finished jobs already show their outcome where they were started.
- Cancelling from the header list. Cancel stays on the job's own page.
- Push notifications or anything outside the open tab.
- Changing the worker model (one in-process worker, one job at a time, spec §9).
- Progress for jobs other than `tadb_import` beyond what they already report (`dict_download`,
  `syosetu_fetch`, `wp_publish`, `wp_illustrations` already call `ctx.progress` per step). They
  get the new UI for free.

## Anti-goals

- The dry run must still write nothing. A progress update must never commit import rows.
- The import must stay all-or-nothing: a cancelled or failed real import leaves no partial
  library.
- Progress reporting must not noticeably slow the import (no database write per row).
- No new polling storm: the header must not hammer `/jobs` while nothing is running.

## Design

### 1. Progress from the import (server)

**Problem with the existing hook.** `JobContext.progress()` commits the job's work session. The
ta.db import runs inside one SAVEPOINT (`import_tadb`), rolled back for a dry run. Calling
`progress()` mid-import would commit the import's rows. So the import needs a progress path that
writes **only the job row, from a separate session**.

**`JobContext.report(done, total, message)`** (new, `api/jobs.py`):
- Throttled by wall clock: returns immediately unless ≥1 s has passed since the last write, or
  `done == total` (so the final count always lands).
- Writes `progress`, `total`, `message` to the job row in its **own short session** (a module-level
  factory, `progress_session = SessionLocal`, swappable in tests), commits that session only.
- Reads `cancel_requested` in the same session; raises `Cancelled` if set, `_Interrupted` if
  `stopping` is set, exactly like `progress()`.
- This is a third sanctioned commit outside the route boundary, in the same module as the other
  job-worker commits. CLAUDE.md's list is updated.

Why the work session's later write doesn't clobber it: `run_next` only assigns `state`,
`result_json`, `message` (on failure) and `finished_at` on its `job` object; SQLAlchemy updates
only changed columns, so `progress`/`total` written by `report()` survive. The work session holds
no lock on the job row during the import (its last touch was the committed `progress(0, 1, …)`).

**Import hook.** `import_tadb(..., on_progress=None)` gains an optional callback
`(done: int, total: int, message: str) -> None`.
- `total` = `count(documents) + count(lines) + count(document_images)` from the SQLite file
  (counted once, cheap). Profiles, series and glossary are small and not counted.
- `done` is cumulative across phases, so one bar and one rate cover the whole run (lines dominate).
- `message` names the phase: `Checking chapters`, `Checking lines`, `Checking images` for a dry
  run; `Importing chapters`, … for a real run.
- Called after each document row, after each line batch, after each image row. The throttle
  lives in `report()`, so calling it often is fine.

`api/tadb_job.py` passes `ctx.report` as `on_progress`. The initial `ctx.progress(0, 1, …)` stays
(it commits the `running` state before work starts); `report()` takes over from there.

**Cancel now works for the ta.db import.** Because `report()` checks `cancel_requested`, the
existing Cancel button can be shown for `tadb_import` (`cancellable` was `false`). Cancelling a
dry run discards the check; cancelling a real run rolls back the whole import (all-or-nothing is
kept: `run_next` rolls back the work session on `Cancelled`). The uploaded file is deleted on a
cancelled real run (existing `finally`), so importing again means uploading again; the
page says so.

### 2. Progress on the page (`web/src/jobs/JobProgress.tsx`)

While a job is not terminal, the card shows:

```
Checking lines · 71,330 of 482,456 (15%)
[███░░░░░░░░░░░░░░░░░]
7 min elapsed · about 45 min left
Runs on the server — you can leave this page and come back.
[Cancel]
```

- **Count line:** `message · done of total (pct)` when `total > 1`; just `message` otherwise.
  Numbers formatted with `toLocaleString()`.
- **Bar:** `<progress>` with `value` only when `total > 1`; otherwise no `value` (the native
  indeterminate animation). Today it always passes `value`, which freezes at 0.
- **Elapsed:** from the job's `started_at`, ticking every second on the client.
- **Estimate:** from the rate the client observes: the first progress sample it saw and the latest
  (`(total - done) / rate`). Shown only after ≥10 s of samples and `done > 0`; rounded
  ("about 45 min left", "under a minute left"). No estimate when `total ≤ 1`.
- **Quiet warning:** if no progress change has arrived for 60 s while running, show "No progress
  for N min. It may still be working; large steps can take a while." Muted, not an error. (The
  SSE stream only sends changes; the client tracks when the last change arrived.)
- **Queued:** state `queued` shows "Waiting for another job to finish" (one worker runs one job at
  a time; a dictionary download blocks an import).
- **Background line:** the "Runs on the server…" sentence, on by default; a prop
  (`background={false}`) turns it off where leaving isn't meaningful. All current callers keep it.
- The pure parts (formatting, estimate) live in `web/src/jobs/eta.ts` with vitest tests.

### 3. Coming back to a page

Pages already resuming an active job: `BatchPublish`, `Volumes` (illustrations), `SyosetuFetch`.
Two don't:

- **`DictionaryPanel`:** on mount, `GET /jobs?active=true` and follow an active `dict_download`
  (same pattern as `SyosetuFetch`).
- **`ImportTadb`:** on mount, `GET /import/tadb/pending` (new). The server looks at the caller's
  **newest** `tadb_import` job only:
  - queued or running → return it; the page follows it (dry run or real run, from
    `params.dry_run`), with `upload_id` from its params;
  - done, `dry_run` true, and its upload file still exists → return it; the page shows its report
    with Import / Discard;
  - anything else (failed, cancelled, interrupted, a finished real run, upload gone) → 204, blank
    form.

  `GET /import/tadb/pending` returns `{ job: JobOut, upload_id }` or 204. The server decides,
  because only it knows whether the upload file still exists (Discard deletes it; the sweeper
  removes it after 24 h). Discard therefore also stops a finished dry run from coming back.

The setup wizard's step state is in-memory: leaving `/setup` mid-step doesn't come back to that
step. Not changed. The ta.db import step works the same as `/import` and resumes there.

### 4. Running-jobs indicator (`web/src/Shell.tsx`)

- A button in the header's `.who` area, before the theme menu: `⟳ 1 running` (count of your
  queued + running jobs). Hidden when the count is 0.
- Data: `GET /jobs?active=true` via TanStack Query, key `["jobs", "active", "all"]`,
  `refetchInterval` 2 s while the list is non-empty, 15 s while empty, plus refetch on window
  focus. Every mutation that starts a job invalidates this key so the button appears at once.
- Click opens a popover (native `popover` attribute + `popovertarget`, no library) listing each
  job: a human name for the kind, its message, a small bar (same rules as §2), and a link:

  | kind | label | link |
  |---|---|---|
  | `tadb_import` | Desktop library import | `/import` |
  | `dict_download` | Dictionary download | `/admin` |
  | `syosetu_fetch` | Syosetu fetch | `/series/{params.series_id}` |
  | `wp_publish` | WordPress publish | `/` |
  | `wp_illustrations` | Volume illustrations | `/series/{params.series_id}` |
  | other | the kind string | none |

- The setup wizard has no header; not added there.
- Styles in `web/src/styles/shell.css`, tokens only.

### 5. Faster ta.db import (`api/core/tadb_rows.py`)

- **Lines** (the bulk) are inserted with Core `insert(Line)` in batches of 1,000 rows (dicts, not
  ORM objects), each batch in one SAVEPOINT. This also keeps 480k `Line` objects out of the
  session's identity map.
- Each row is still checked before batching: the `MAX_TEXT_CHARS` check, the `MAX_LINES` cap and
  the empty-prefix fix stay per row and report as today.
- If a batch raises `IntegrityError` or `DataError`, its SAVEPOINT is rolled back and that batch is
  retried **row by row** (one SAVEPOINT each, as today), so a bad row is still skipped and reported
  by its `row <id>` label and never aborts the run. Other exceptions propagate, as today.
- `report.written["lines"]` counts the same as before.
- Documents, images, profiles, series and glossary stay per-row ORM (a few thousand rows; documents
  need their ids for the line batches).
- **Expected:** thousands of rows/s instead of ~150. Verify with the real 480k-line file and
  record the before/after time in the plan's final task.

## Constraints

- CLAUDE.md rules apply: handlers `flush()` not `commit()` (the import is a job, not a route);
  modules stay under ~400 lines (`tadb_rows.py` is at 327; the batch helper may need its own
  module, `api/core/tadb_lines.py`); routers via `api_router()`; regenerate `schema.d.ts` after
  API changes.
- Don't edit `api/` while a job is running on the dev server: `--reload` hangs waiting for the
  job's SSE stream. Build after the current dry run finishes.

## Testing

- `report()`: throttles (two calls inside 1 s write once; `done == total` always writes); raises
  `Cancelled` after `cancel_requested`; doesn't commit the work session (a dry run with
  `on_progress=ctx.report` still writes nothing). Tests swap `api.jobs.progress_session` for a
  factory giving a separate `Session` on the test connection with
  `join_transaction_mode="create_savepoint"`.
- Import: same reports as before for a fixture with a bad line in a batch (the row is skipped and
  reported, the rest of its batch is written); `on_progress` sees a final `done == total`.
- `GET /import/tadb/pending`: active job; finished dry run with upload present; after Discard → 204;
  a later real run hides the dry run; another user's job never returned.
- vitest: `eta.ts` formatting and estimate.
- Playwright: the header indicator appears for an active job (route-mocked `/jobs`); ImportTadb
  restores a pending dry run (route-mocked).

## Left to the builder

- Exact copy for the phase messages and the estimate's rounding.
- Popover positioning and the narrow-width layout of the header button.
- Whether the line batch size is 1,000 or something nearby, if measurement says so.
