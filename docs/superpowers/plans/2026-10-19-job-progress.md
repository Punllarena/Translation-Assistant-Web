# Job Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jobs show live counts, elapsed time and an estimate; pages say jobs run in the background and pick them up again; a header indicator lists running jobs; the ta.db import inserts lines in batches.

**Architecture:** A throttled `JobContext.report()` writes only the job row from its own session, so the ta.db import (one SAVEPOINT, rolled back on a dry run) can report progress without committing its rows. The SPA's `JobProgress` gains counts/elapsed/ETA from pure helpers in `eta.ts`; `ImportTadb` and `DictionaryPanel` resume via the API; `Shell` polls `GET /jobs?active=true` for the indicator. Lines go in as Core `insert(Line)` batches, falling back to per-row SAVEPOINTs for a batch the database rejects.

**Tech Stack:** FastAPI, SQLAlchemy 2, Postgres, pytest; React + TanStack Query, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-19-job-progress-design.md`

## Global Constraints

- Don't edit `api/` while a job runs on the dev server (`--reload` hangs on the job's SSE stream).
- Handlers and the importer `flush()`, never `commit()`; the only commits outside the route boundary are in `api/jobs.py` (`progress`, `run_next`, and the new `report`) and `_put_sync` in `api/routers/mt.py`.
- No Python module over ~400 lines (`api/core/tadb_rows.py` is 327 now; the batch code goes in a new `api/core/tadb_lines.py`).
- Routers via `api_router()`; regenerate `web/src/api/schema.d.ts` (`npm run gen:api`, venv on `PATH`) after API changes.
- Stylesheets use tokens from `web/src/styles/tokens.css`, never literal colours.
- `report()` throttle: ≥1 s between writes; `done == total` always writes. Line batch size: 1,000.
- ETA shown only after ≥10 s of samples and `done > 0`; quiet warning after 60 s without a progress change.
- Header poll: 2 s while any job is active, 15 s while none; refetch on window focus.
- Run pytest with `TA_MT_ALLOW_PRIVATE_URLS=false TA_WP_ALLOW_PRIVATE_URLS=false` (the dev `.env` sets them true and breaks unrelated URL tests).

## Review Focus

- **A batch with one bad line** (NUL byte or over-long `prefix`): that row is skipped and reported as `lines row <id>`, the other 999 are written. → Task 2, `test_a_bad_line_skips_only_itself_in_its_batch`.
- **Cancel mid dry run / mid real run:** dry run leaves nothing; a real run leaves no documents or lines. → Task 3, `test_cancel_during_a_real_import_leaves_nothing`.
- **Progress write must not commit import rows:** a dry run with `on_progress=ctx.report` firing still writes nothing. → Task 3, `test_dry_run_with_progress_reports_writes_nothing`.
- **Coming back after Discard or after 24 h:** `/import/tadb/pending` must not resurrect a dry run whose upload is gone. → Task 4, `test_pending_is_empty_once_the_upload_is_discarded`.
- **`total` of 0 or 1** (jobs that haven't counted yet): indeterminate bar, no percent, no ETA, no division by zero. → Task 5, `eta.test.ts` cases `total 0` / `total 1`.

---

### Task 1: `JobContext.report()` — throttled progress from its own session

**Files:**
- Modify: `api/jobs.py`
- Modify: `tests/conftest.py` (autouse fixture)
- Test: `tests/test_jobs.py`
- Modify: `CLAUDE.md` (sanctioned-commit list)

**Interfaces:**
- Produces: `api.jobs.progress_session: Callable[[], Session]` (module attribute, default `SessionLocal`); `JobContext.report(self, done: int, total: int, message: str = "") -> None`, raising `Cancelled` / `_Interrupted` like `progress()`. `JobContext.__init__` stores `self._reported_at: float | None = None`.

- [ ] **Step 1: Autouse fixture in `tests/conftest.py`**

`_progress_session` (autouse): monkeypatch `api.jobs.progress_session` to `lambda: Session(bind=db.connection(), expire_on_commit=False, join_transaction_mode="create_savepoint")`, so `report()` writes in a separate session on the test connection. Request `db` lazily: only when the test uses `db` (use `request.getfixturevalue("db")` inside the factory) so DB-less tests stay DB-less.

- [ ] **Step 2: Write the failing tests in `tests/test_jobs.py`**

```python
def test_report_writes_the_job_row_and_is_throttled(in_test_db, make_user, kind, monkeypatch):
    clock = iter([100.0, 100.5, 101.6, 101.7])
    monkeypatch.setattr(jobs.time, "monotonic", lambda: next(clock))
    seen = []
    def work(ctx):
        ctx.report(1, 10, "a"); seen.append(_row(ctx))   # first call writes
        ctx.report(2, 10, "b"); seen.append(_row(ctx))   # 0.5 s later: skipped
        ctx.report(3, 10, "c"); seen.append(_row(ctx))   # 1.6 s: writes
        ctx.report(10, 10, "d"); seen.append(_row(ctx))  # done == total: writes
        return {}
    kind("rep", work)
    jobs.enqueue(in_test_db, make_user(email="r@example.com").id, "rep", {})
    jobs.run_next()
    assert seen == [(1, 10, "a"), (1, 10, "a"), (3, 10, "c"), (10, 10, "d")]

def test_report_raises_cancelled_when_cancel_was_requested(...): ...
    # set job.cancel_requested=True via a separate statement before work; ctx.report(1, 2) -> job.state == "cancelled"

def test_report_does_not_commit_the_work_session(...): ...
    # work: db.add(Series(...)) inside ctx.db.begin_nested(); ctx.report(1, 1); then raise JobError
    # assert the Series row is absent afterwards
```
`_row(ctx)` reads `(progress, total, message)` with a fresh `SELECT` through `jobs.progress_session()`.

- [ ] **Step 3: Run, expect FAIL** — `pytest tests/test_jobs.py -k report -v` → `AttributeError: ... 'report'`.

- [ ] **Step 4: Implement `report()`** in `api/jobs.py`: `import time`; read `time.monotonic()` exactly once per call (the throttle test feeds one value per call); skip unless `self._reported_at is None or done >= total or time.monotonic() - self._reported_at >= 1.0`; then in `with progress_session() as s:` run `update(Job).where(Job.id == self.job.id).values(progress=done, total=total, message=message).returning(Job.cancel_requested)`, `s.commit()`, set `_reported_at`; raise `_Interrupted` if `stopping.is_set()`, `Cancelled` if the returned flag is true. A missing row (no result) returns without raising. Update the module docstring's commit list.

- [ ] **Step 5: Run, expect PASS** — `pytest tests/test_jobs.py -v`.

- [ ] **Step 6: CLAUDE.md** — in "Architecture rules", the MT bullet's "the other is the job worker (`JobContext.progress` and `run_next`)" becomes "`JobContext.progress`, `JobContext.report` (job row only, its own session, throttled) and `run_next`".

- [ ] **Step 7: Commit** — `feat(api): throttled job progress that writes only the job row`

---

### Task 2: Batched line inserts

**Files:**
- Create: `api/core/tadb_lines.py`
- Modify: `api/core/tadb_rows.py` (the `lines` loop in `_import_documents`)
- Test: `tests/test_import_tadb.py`

**Interfaces:**
- Produces: `insert_lines(db: Session, batch: list[tuple[str, dict]], report: ImportReport) -> None` — `batch` is `(label, values)` pairs, `values` the `Line` column dict; `BATCH = 1000`.
- Consumes: `_add`-equivalent per-row fallback and `_skip` from `api.core.tadb_schema`.

- [ ] **Step 1: Failing test** — `test_a_bad_line_skips_only_itself_in_its_batch`: build a fixture with `desktop_db`, `_tweak` one line's `raw_text` to contain `char(0)` (Postgres rejects NUL with `DataError`); import; assert `report.skipped["lines"] == 1`, the message list has one entry starting `lines row <that id>`, and `Line` count equals source lines − 1.

- [ ] **Step 2: Run, expect PASS or FAIL** — today's per-row path may already pass it; it pins behaviour across the rewrite. Note which.

- [ ] **Step 3: Implement** `insert_lines`: in `with db.begin_nested(): db.execute(insert(Line), [v for _, v in batch])`, then `report.written["lines"] += len(batch)`. On `IntegrityError`/`DataError`: for each pair, `with db.begin_nested(): db.execute(insert(Line).values(**v))`, counting written or calling `_skip(report, "lines", label, reason)` with the same reason formatting as `_add`. In `_import_documents`, build the dict per row (per-row checks unchanged: cap, empty prefix, `MAX_TEXT_CHARS` via a small `_too_long(values)` helper that reports like `_add`), append to a list, flush with `insert_lines` every `BATCH` rows and once after the loop.

- [ ] **Step 4: Run the whole importer suite** — `pytest tests/test_import_tadb.py tests/test_tadb_api.py -v` → all PASS (counts and messages unchanged).

- [ ] **Step 5: Commit** — `perf(api): insert ta.db lines in batches of 1000`

---

### Task 3: Import progress hook, job wiring, cancel

**Files:**
- Modify: `api/core/tadb_import.py`, `api/core/tadb_rows.py`, `api/core/tadb_lines.py` (if the callback is threaded through), `api/tadb_job.py`
- Test: `tests/test_import_tadb.py`, `tests/test_tadb_api.py`

**Interfaces:**
- Consumes: `JobContext.report` (Task 1), `insert_lines` (Task 2).
- Produces: `import_tadb(..., on_progress: Callable[[int, int, str], None] | None = None)`; `_import_all(conn, db, user_id, report, progress: Progress)` where `Progress` is a small class in `tadb_rows.py`: `Progress(total: int, verb: str, cb)` with `step(n: int, phase: str)` calling `cb(done, total, f"{verb} {phase}")`. `verb` is `"Checking"` for a dry run, `"Importing"` otherwise; phases `"chapters"`, `"lines"`, `"images"`.

- [ ] **Step 1: Failing tests**
  - `test_progress_counts_every_document_line_and_image`: collect calls; last call is `(T, T, "Importing images")` where `T` = documents + lines + images in the fixture; `done` never decreases.
  - `test_dry_run_with_progress_reports_writes_nothing` (in `test_tadb_api.py`): wrap `JobContext.report` with a spy (monkeypatch, calling through); upload, run the dry-run job with the real handler; assert job `done`, `Document` count 0, and the spy's last call is `(T, T, "Checking images")`. Don't assert on the job row's `total`: in tests `report()`'s savepoint is nested inside the import's, so the dry run's rollback undoes it.
  - `test_cancel_during_a_real_import_leaves_nothing`: monkeypatch `api.tadb_job` so `on_progress` sets `cancel_requested` after the first call; run the real job; assert state `cancelled`, 0 `Document`/`Line` rows for the user.

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** — count `documents`, `lines`, `document_images` once from the SQLite connection in `import_tadb`; pass a `Progress` (no-op callback when `on_progress` is None); `step(1, …)` per document and image row (including skipped ones, so `done` reaches `total`), `step(len(batch), "lines")` per line batch plus skipped/orphan lines. In `api/tadb_job.py` pass `on_progress=ctx.report` to both `import_tadb` calls in `_dry_run` and the real run.

- [ ] **Step 4: Run** — `pytest tests/test_import_tadb.py tests/test_tadb_api.py tests/test_jobs.py -v` → PASS.

- [ ] **Step 5: Commit** — `feat(api): ta.db import reports progress and can be cancelled`

---

### Task 4: `GET /import/tadb/pending`

**Files:**
- Modify: `api/routers/tadb.py`, `api/schemas/tadb.py`
- Test: `tests/test_tadb_api.py`
- Regenerate: `web/src/api/schema.d.ts`

**Interfaces:**
- Produces: `GET /import/tadb/pending` → 200 `TadbPendingOut { job: JobOut, upload_id: str }` or 204.

- [ ] **Step 1: Failing tests** — `test_pending_returns_the_running_job`, `test_pending_returns_a_finished_dry_run_while_its_upload_exists`, `test_pending_is_empty_once_the_upload_is_discarded`, `test_pending_is_empty_after_a_real_run`, `test_pending_never_returns_another_users_job`.

- [ ] **Step 2: Run, expect FAIL (404).**

- [ ] **Step 3: Implement** per spec §3: newest `tadb_import` job for the user (`order_by(Job.id.desc()).limit(1)`); return it when queued/running, or when `done` with `params_json["dry_run"]` true and `tadb_uploads.path_for(...)`'s file exists; else `Response(status_code=204)`. `path_for` raising `ValueError` → 204.

- [ ] **Step 4: Run, expect PASS; `npm run gen:api`.**

- [ ] **Step 5: Commit** — `feat(api): pending ta.db import for resuming the page`

---

### Task 5: `eta.ts` and the new `JobProgress`

**Files:**
- Create: `web/src/jobs/eta.ts`, `web/src/jobs/eta.test.ts`
- Modify: `web/src/jobs/JobProgress.tsx`, `web/src/styles/` (whichever file holds job/progress styles; else `controls.css`)

**Interfaces:**
- Produces:
  - `countLine(job: Pick<Job,"message"|"progress"|"total">): string` → `"Checking lines · 71,330 of 482,456 (15%)"`, or just the message when `total <= 1`.
  - `formatDuration(ms: number): string` → `"7 min"`, `"1 h 5 min"`, `"42 s"`.
  - `estimateLeft(first: Sample, last: Sample, total: number): number | null` with `Sample = { at: number; done: number }`; null when `total <= 1`, `last.done <= first.done`, or `last.at - first.at < 10_000`.
  - `leftText(ms: number | null): string | null` → `"about 45 min left"`, `"under a minute left"`, null passthrough.
  - `JobProgress` props add `background?: boolean` (default `true`).

- [ ] **Step 1: Failing vitest cases** in `eta.test.ts`: `countLine` with total 0, total 1, total 482456/done 71330 (expects `(15%)` and locale separators via `toLocaleString("en")`); `estimateLeft` null under 10 s, null when no progress, `(482456-71330)/rate` otherwise; `leftText(30_000)` → `"under a minute left"`, `leftText(45*60_000)` → `"about 45 min left"`.

- [ ] **Step 2: `npm test -- eta` → FAIL.**

- [ ] **Step 3: Implement `eta.ts`; then `JobProgress`:** keep the first sample seen and the latest; a 1 s `setInterval` re-render while not terminal; render count line, `<progress>` with `value` only when `total > 1`, `"{elapsed} elapsed · {left}"` from `started_at`, the quiet warning after 60 s without change (`"No progress for N min. It may still be working; large steps can take a while."`, class `hint`), `"Waiting for another job to finish"` when `state === "queued"`, and `"Runs on the server — you can leave this page and come back."` when `background`.

- [ ] **Step 4: `npm test` → PASS; `npx tsc --noEmit -p .` clean.**

- [ ] **Step 5: Commit** — `feat(web): job progress with counts, elapsed time and an estimate`

---

### Task 6: Resume on return, Cancel for ta.db

**Files:**
- Modify: `web/src/library/ImportTadb.tsx`, `web/src/admin/DictionaryPanel.tsx`
- Test: `web/e2e/tadb.spec.ts`

**Interfaces:**
- Consumes: `GET /import/tadb/pending` (Task 4), `JobProgress` (Task 5).

- [ ] **Step 1: Failing e2e** — `the import card restores a finished dry run`: route-mock `**/api/import/tadb/pending` with a done dry-run job + `upload_id`; open `/import`; expect the counts table and an `Import` button. Second case: running job → progress text visible and a `Cancel` button.

- [ ] **Step 2: Run — `npx playwright test e2e/tadb.spec.ts` → FAIL.**

- [ ] **Step 3: Implement** — `ImportTadb`: `useQuery(["import", "tadb", "pending"], gcTime: 0)`; on data, seed `upload` (`{ upload_id, job_id }`) and, for a done dry run, `dry` from `job.result`; for a running real run, `runJob`. Drop `cancellable={false}` from both `JobProgress` uses; a cancelled real run shows "Cancelled. Upload the file again to import." `DictionaryPanel`: `useQuery(["jobs","active","dict_download"], gcTime: 0)` on `GET /jobs?active=true`; `running = jobId ?? active.data?.find(j => j.kind === "dict_download")?.id ?? null` (same shape as `SyosetuFetch`).

- [ ] **Step 4: Run the e2e spec and `npm test` → PASS.**

- [ ] **Step 5: Commit** — `feat(web): pick up running and finished ta.db and dictionary jobs on return`

---

### Task 7: Header running-jobs indicator

**Files:**
- Create: `web/src/jobs/RunningJobs.tsx`
- Modify: `web/src/Shell.tsx`, `web/src/styles/shell.css`; every job-starting mutation's `onSuccess` (`ImportTadb` send/run, `DictionaryPanel` download, `SyosetuFetch`, `BatchPublish`, `Volumes` illustrations) adds `queryClient.invalidateQueries({ queryKey: ["jobs", "active", "all"] })`
- Test: `web/e2e/` new `jobs.spec.ts`

**Interfaces:**
- Produces: `RunningJobs(): JSX.Element | null`; `jobLink(job: Job): { label: string; to: string | null }` exported from `RunningJobs.tsx` (table in spec §4).

- [ ] **Step 1: Failing e2e** — route-mock `**/api/jobs?active=true` with one running `tadb_import` (`progress 10, total 100, message "Checking lines"`); after login, expect button `1 running`; click → popover shows "Desktop library import", "Checking lines", link to `/import`. With `[]`, the button is absent.

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — query key `["jobs", "active", "all"]`, `refetchInterval: (q) => (q.state.data?.length ? 2000 : 15000)`, `refetchOnWindowFocus: true`; render nothing for 0; `<button popovertarget="running-jobs">⟳ {n} running</button>` + `<div id="running-jobs" popover>` listing rows with `countLine` and a `<progress>` (value only when `total > 1`); a link closes the popover (`hidePopover()`) on click. Place before `<ThemeMenu />` in `.who`.

- [ ] **Step 4: Run e2e spec, `npm test`, `npx tsc --noEmit -p .` → PASS.**

- [ ] **Step 5: Commit** — `feat(web): running jobs indicator in the header`

---

### Task 8: Measure, full suite, docs

- [ ] **Step 1:** Time a dry run of the real 480,716-line `ta.db` before (from the 2026-10-19 run: ~150 rows/s, ~53 min) and after: `python -m tools.import_tadb --db <file> --user <email> --dry-run` with `time`. Record both in the commit message. Expected: under 5 min.
- [ ] **Step 2:** `ruff check .`; `pytest` (flags off); `npm test`; `npm run e2e` → all pass.
- [ ] **Step 3:** CLAUDE.md Phase 6a paragraph: one sentence: the ta.db import reports progress through `JobContext.report` and inserts lines in batches of 1,000 (`api/core/tadb_lines.py`), falling back to per-row on a rejected batch; `GET /import/tadb/pending` resumes the page.
- [ ] **Step 4: Commit** — `docs: job progress and batched ta.db import`
