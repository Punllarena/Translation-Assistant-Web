# Ollama background translation

## Intent

Ollama suggestions came from the desktop app, where one person's machine translated the line they were looking
at, live. On a server that pattern wastes the user's Ollama box: it sits idle at night and is slow while they work.
The user wants Ollama to translate ahead of time, on a schedule they set for off-peak hours, so that opening a
chapter the next morning shows a ready suggestion on every line. They also want to see what the model did (its
reasoning and its numbers) to choose models and settings, and they want saved output to clean itself up.

The first real machine is CPU-only (i5-8400, 6 cores, 16 GB, Intel UHD 630, so no GPU inference) running a gemma
E2B model that also serves other web apps. A dedicated box comes later, about one generation newer with 32 GB.
Everything must work on the small box and scale by raising settings, not by changing design.

## Goals

- A per-user **Ollama queue** of series, volumes or chapters, run in a **scheduled time window** (or "Run now").
- Translation in **labelled chunks of whole paragraphs** with the previous lines as read-only context, so sentences
  split across lines and paragraphs keep their flow.
- **Saved suggestions** on every line, shown instantly in the editor, with a **Reasoning** dialog (Reasoning /
  Stats / Prompt tabs).
- **Statistics** per chunk (tokens, times, tokens/s, model load), with an **Ollama tab** on the Statistics page.
- **Retention**: a chapter's saved output is cleared 3 months after every line is translated; manual flush at any
  level.
- Already-translated lines never trigger Ollama unless the user asks.
- A **Jobs page** for every kind of job, with the Ollama queue as one tab.

## Non-goals

- A background **syosetu fetch** schedule. A later update; the Jobs page's Scheduled tab is built so it can join.
- **Pronouns and gender.** The user ruled them out: the source rarely says, and context won't fix it.
- **A "memory" the model writes** (series notes, summaries). Context is the previous lines only.
- **Several suggestions per line** (rerolls or models side by side). One saved suggestion per line; Reroll replaces it.
- **Few-shot examples from translation memory.**
- **A benchmark script.** The user skipped it; the Stats tab answers the same question after real runs.
- Ollama on the admin's server. See "Your own server" below.

## Anti-goals

- A night run must never block other jobs (imports, publishes, dictionary downloads) for anyone. The current
  worker runs one job at a time for the whole server (`api/jobs.py`); hours of Ollama in that lane would.
- Never send two requests at once to one user's Ollama server. It is shared with their other apps.
- Never lose lines to a bad model answer. A malformed answer costs time (retries), never silently drops a line.
- Never translate a line that already has a translation, unless the user clicked for it.
- Never let a stale suggestion pass as current: if the source line changed, the card says so.

## Decided by the user

### Your own server

- Each user provides their own Ollama server (the existing `ollama` credential with its `endpoint_url`). The admin
  does not supply one. The operator default (`TA_OLLAMA_URL`, the `ollama_url` admin override in
  `api/server_settings.py`, the field in `web/src/admin/ServerSettingsForm.tsx`) goes away, and Ollama answers
  "Set an Ollama URL under Settings → Machine translation" until the user sets theirs. `check_user_url` still guards
  it. A server on a private address (the user's own LAN box) works when the admin turns on the existing server-wide
  `TA_MT_ALLOW_PRIVATE_URLS` (or its admin-settings row); no Ollama-only switch. The Settings page's refusal message
  should say that this switch is what allows it.
- **Guard hardening (review).** `check_user_url` (`api/mt/urls.py`) today skips every address check when private
  addresses are allowed. It must always refuse link-local and metadata targets (`169.254.0.0/16`, `fe80::/10`,
  `0.0.0.0`/`::`, and hosts such as `metadata.google.internal`) even with the override on, because the override is
  for LAN boxes, not cloud metadata. This applies to every caller (LibreTranslate, WordPress), which is intended.
  A run re-checks the URL at its start and before each chunk, since a run lasts hours.
- *(My call.)* The migration copies the effective operator URL into the `ollama` credential of each user who has
  Ollama enabled and no URL of their own, so nobody's Ollama stops working on upgrade.
- No admin cap on lines. The user's own settings decide how hard their server works.
- One active Ollama run per account at a time.

### Scheduling and the queue

- Ollama work can run as a scheduled task in a time window (for example 01:00–07:00) in the user's own time zone.
  When the window closes mid-run, the run stops after the current chunk and the next window carries on.
- The user chooses what to queue: a series, a volume, or chapters.
- Lines and chapters already translated are skipped.

### Context: labelled chunks (option 3)

- The run sends **chunks** of lines, each line labelled, and the model answers with the same labels.
- Each request also carries the **last few lines of the previous chunk** (source and translation) as read-only
  context.
- **Chunk size** and **context lines** are user settings, with **presets**.
- Names come from the glossary, which the app already applies to the source before MT (`display_line` in
  `api/routers/lines.py` replaces glossary terms). That stays the text sent.

### The editor

- Same editor page. The Ollama card (`web/src/editor/MtPanels.tsx`) shows the saved suggestion with **Use**,
  **Reasoning** and **Reroll**, and a badge: when it was made and by which model ("prepared 02:14 · qwen3:14b").
- **Reasoning** opens a modal (native `showModal()`, like the publish dialogs) with tabs **Reasoning | Stats |
  Prompt** (mockup option B). Under the reasoning, a one-line stats summary. A model that did not reason gets
  "This model didn't reason" in that tab; the dialog still opens for the other two.
- A line with no saved suggestion: by-hand translation sends **the whole chunk the line belongs to**, not the line
  alone.

### Retention

- A chapter counts as **translated** when every line has a translation. The 3-month clock starts then.
- The user can flush by hand.

### Pages

- **Jobs page** (mockup B): one page for every job, tabs **Running | Ollama queue | Scheduled | History**.
- **Statistics page**: the current page becomes the **Translation** tab, unchanged; a new **Ollama** tab (mockup as
  shown) has four figures (average tokens/s over 30 days, lines prepared over 30 days, used as-is / edited /
  ignored, chunk retry rate), a per-run chart switchable between tokens/s, lines per hour and seconds per chunk, a
  table by model and preset, and recent runs linking to Jobs → History.

## Proposed and agreed in playback

These were offered as guesses and the user said they looked right.

- Reasoning and stats are saved with the suggestion. Stats belong to a **chunk**; a line's dialog says "from lines
  10–24".
- Already-translated lines are checked **when the run reaches them**, not at queue time.
- Queuing a **series** is a standing order: chapters added later are picked up.
- Each schedule can be switched off without deleting it.
- The chunk's context window (`num_ctx`) is worked out from chunk size and context lines; `num_thread` is an
  optional advanced field.
- Reasoning is requested only from models that support it. Today `api/mt/ollama.py` sends `think: true` on every
  request, which some Ollama versions refuse for models that cannot think.
- Chapter "translated" clock = the newest `translated_at` among its lines, taken when the last empty line is filled.
  Clearing a line again makes the chapter untranslated and stops the clock; it restarts when complete again.
- Clean-up is a scheduled job, visible under Scheduled and History.
- Flush at every level: one chapter (⋯ menu), selected chapters, a volume, a series (Volumes tab), everything
  (Jobs → Ollama queue). Each asks through `ConfirmDialog`. Flushing a queued chapter leaves it queued.
- **Stats survive a flush.** Only generated text, reasoning and prompt are deleted.
- Ollama stops using `mt_cache`. Its existing `ollama:*` rows are deleted once, in the migration.
- "Used as-is / edited / ignored" is computed when the user saves a line that has a suggestion, and kept as a number
  that survives the clean-up.
- By hand on a line with no translation and no saved suggestion: the card starts on its own (as today). On a line
  that already has a translation: a **Translate chunk** button, nothing automatic.
- While a by-hand chunk runs, the card says "Translating lines 10–24…", the line's own text appears as soon as its
  part of the answer arrives, and the other lines of the chunk are saved too.
- An account's Ollama work goes to its server one request at a time. A by-hand chunk jumps ahead: the night run
  pauses after its current chunk and resumes afterwards.
- Reroll re-sends the same chunk and replaces the saved results of the lines it asked for.

## How it works

### Lines, paragraphs and chunks

Lines have a `prefix` (`api/core/text.py`): `%` starts a paragraph (one source line), `$` is a sentence that the
parse characters split off the line before it, `""` is a blank line. A **paragraph** is a `%` line and the `$` lines
after it. Mid-sentence splits are always `$` lines, so:

- A chunk is a run of **whole paragraphs**, filled up to the chunk size in lines. A paragraph longer than the
  chunk size is a chunk on its own.
- Blank lines and lines whose display text is empty are not sent and get no suggestion.
- Chunks are cut the same way by night runs, by hand and by Reroll, from the same settings, so "the chunk a line
  belongs to" is well defined: cut the chapter from its first line and take the chunk containing the line.
- In each chunk, lines with a translation, and lines with a current (not stale) saved suggestion, are **context**
  (source plus translation or suggestion shown, not asked). Only lines with neither are **asked**, so a good
  suggestion is never overwritten by a run or by another line's by-hand request. A chunk with nothing to ask is
  skipped. *(My call.)*
- By hand on a line also asks that line, whatever it has. **Reroll** asks every line of the chunk that has no
  translation, replacing their suggestions.
- **Stale** is judged on the line's raw source (`raw_text`), not the glossary-applied display text, so a glossary or
  parse-character edit does not make a series' suggestions stale. A stale suggestion on an untranslated line counts as
  missing: the next run asks it again. *(My call.)*
- **Context lines**: the last N lines before the chunk (source, and the translation if it has one, otherwise the
  saved suggestion if any), marked as context only.

### The request

- The system prompt is the user's (`ollama_system_prompt`, default `DEFAULT_SYSTEM_PROMPT`), followed by format
  instructions the app owns: what the labels mean, that context lines are not to be translated, and that a `$` line
  may be left empty when its meaning was carried into the line before.
- The user message lists context lines, then the chunk's lines as `[<line_number>] <display text>`, with the asked
  lines marked.
- Ollama structured output: `format` is a JSON schema `{"lines": [{"id": int, "text": string}]}`, so even a 2B
  model cannot drift from the shape.
- Options: `num_ctx` from the settings (estimate tokens from the text sent plus room for the answer, rounded up to a
  sensible step), `num_thread` when set, `keep_alive` long enough to keep the model loaded between chunks of a run.
- **Too big for the model (review):** the model's maximum context comes from `/api/show` (remembered per model, like
  the thinking capability). When a chunk's estimate exceeds it, the chunk is split before sending, by the same
  halving rule as a failed answer, and the run's History notes how many chunks were clamped.
- `think` only when the model reports the thinking capability (`/api/show` `capabilities`), checked once per run or
  by-hand request and remembered for the model.

### Checking the answer

- Every asked id is present exactly once, in order, with no ids that were not asked.
- An empty text is accepted only for a `$` line.
- On failure the chunk is split in half (at a paragraph boundary when possible, otherwise at any line) and each half
  is retried, down to single lines. A single line that still fails is recorded as failed for that run and left
  without a suggestion; the run goes on. Retries count toward the chunk retry rate.

### Saved data (my call on the shape)

- **`ollama_chunks`**: one row per request that returned. User, series, document (SET NULL on delete, so stats
  survive deleted chapters), run job id (nullable for by-hand), source (`run` / `manual` / `reroll`), model, preset
  name, chunk size, context lines, first and last line number, Ollama's `prompt_eval_count`, `eval_count`,
  `prompt_eval_duration`, `eval_duration`, `load_duration`, `total_duration`, time to first token, retry depth,
  created at. Plus `reasoning` and `prompt` text, set to NULL on flush.
- **`ollama_suggestions`**: one row per asked line. Line (CASCADE), chunk, text (NULL once flushed), a hash of the
  line's `raw_text` when it was sent (stale when it no longer matches), and the outcome fields
  (`outcome`: `used` / `edited` / `ignored`, plus a similarity number), set when the line is first saved with a
  translation while a suggestion exists. A new suggestion for the line replaces the old row.
- **Outcomes live on the chunk (review):** when a line is saved, the chunk's `used_count` / `edited_count` /
  `ignored_count` is incremented (and the line's suggestion row records that it was scored, so it counts once).
  Statistics read only the chunk counters, so flushes, cleared lines and deleted chapters never change them.
- `ollama_suggestions` has a unique index on `line_id` (one suggestion per line). `lines(document_id, line_number)`
  is already unique, which serves the run's scan.
- The thresholds for "used" (equal after whitespace and punctuation normalisation) and "edited" (similarity at or
  above a cut-off) are the builder's, kept in one pure module with tests.

### Running Ollama off the main job worker

- A run is still a **`jobs` row** (kind `ollama_run`), so Running, History, cancel and SSE progress work like every
  other job. The general worker's `_claim` must skip that kind.
- A separate **Ollama runner** in the lifespan claims `ollama_run` jobs, at most one per user, several users in
  parallel (a small server-wide cap, the builder's call). It uses async `httpx` like the MT backends.
- **Claiming (review):** the runner claims with `SELECT … FOR UPDATE SKIP LOCKED` like `_claim`, and a partial unique
  index on `jobs (user_id) WHERE kind = 'ollama_run' AND state IN ('queued', 'running')` makes "one run per account"
  a database rule, not just a check in a request. The app stays a single API process (the `jobs.py` ponytail); the
  per-user lane below is in-process, and the spec relies on that, as the existing worker does.
- **Per-user lane**: all Ollama requests for a user, from runs and by hand, go through one lane. By-hand requests jump
  ahead.
- **Preemption is graceful (review, option A):** an in-flight chunk is never aborted, because on the target CPU it is
  up to a minute of work that would be thrown away. A by-hand request waits for the current chunk to finish (the card
  says "Waiting for the night run's current chunk…"), runs, and then the run continues.
- A run **derives its work** from the queue each time it needs the next chunk (queued items in order, the chapters
  they cover, lines with no translation and no current suggestion). Nothing is kept about where it stopped, so a
  window ending, a cancel, a server restart or an edit to the queue all resume correctly.
- **Unreachable server**: retry the chunk a few times with a growing pause, then end the run with a message. The next
  window or Run now tries again.
- A run ends when the queue has nothing left to ask, the window closes, or the user cancels. Results so far stay.

### The schedule

- The app has no scheduler today. A small **scheduler tick** in the lifespan (about once a minute) starts a user's
  `ollama_run` when their window opens and nothing is running, and asks a running one to stop at the window's end.
  It also starts the nightly clean-up.
- User schedule (stored as a user setting, `ollama_schedule`): enabled, start time, end time (a window may cross
  midnight), days of the week, IANA time zone (defaults to the browser's, like `/stats?tz=`).
- **Run now** starts a run outside the window. It stops only when the work runs out or the user cancels.

### The queue

- **`ollama_queue_items`**: user, kind (`series` / `volume` / `documents`), target ids, position, created at.
  Reorder by drag; remove with ⋯.
- Series items are standing orders and stay until removed. Volume and chapter items leave the queue when the run
  finds nothing left to ask in them.
- Rows show lines still to ask and an estimated time from the user's recent tokens/s for their current model and
  preset (no estimate before the first run).
- Added from the Jobs page (**Add**: pick series, then optionally a volume or chapters) and from a series' Volumes tab
  (selection bar → "Queue for Ollama"; volume ⋯ → "Queue volume"; the series → "Queue series").
- A cap on queue items per user (the builder's call, something like 100) keeps the table bounded. Hitting it gives a
  plain message naming the cap. Finished volume and chapter items already leave the queue on their own, so there is
  no "clear completed" action.

### Settings → Machine translation → Ollama

Next to the existing model and system prompt:

- **Preset** with values (my starting numbers, to be tuned against real stats):
  - Small CPU (≈2B): 12 lines, 5 context lines
  - Medium (4–8B): 25 lines, 10 context lines
  - Large / GPU: whole chapter, 0 context lines
  - Custom: shown when either number is edited
- **Chunk size** (lines, or "whole chapter") and **context lines**.
- **CPU threads** (`num_thread`), optional, under an advanced fold.
- New user setting keys, parsed with defaults in `api/mt/prefs.py` like the existing ones.

### The editor

- `GET /mt/stream` keeps serving the other backends. Ollama gets its own endpoints (the builder names them): read
  the saved suggestion for a line, start the line's chunk (SSE: per-line results as each JSON entry completes,
  `thinking`, then stats, then done), and reroll.
- **Stream format (review):** the server parses Ollama's streamed JSON incrementally and sends one SSE event per
  completed entry, `event: line` with `data: {"line_number": 12, "text": "…"}`, plus `thinking`, `stats`, `error` and
  `done` events. The client never parses partial JSON. The schema is fixed, so a small purpose-built scanner is
  enough; the builder may use a library instead. Answer checks (ids, order, empties) still run on the whole answer
  before anything is saved, so a line shown live from an answer that then fails the check is replaced by the
  retried halves' results.
- **Reroll says its reach (review):** the button reads "Reroll lines 10–24" (or its tooltip does), since it replaces
  every untranslated line of the chunk, not just the current one.
- Card states: saved (badge + Use / Reasoning / Reroll), stale (the source changed since: the badge says "source
  changed", and the dialog's Prompt tab shows the text that was sent, so the difference can be seen; Reroll offered), running ("Translating lines 10–24…"), waiting (the lane is busy: "Waiting for the night run's current
  chunk"), translated with nothing saved (**Translate chunk**), error (Retry), not set up (link to settings).
- When a chunk finishes, the editor refreshes the saved suggestions of the other lines in it.
- Saving a line computes its outcome (see Saved data), in the existing line save path.

### Jobs page

- A new route with tabs **Running | Ollama queue | Scheduled | History**, reachable from the header's running-jobs
  button.
- **Running**: active jobs of every kind (`GET /jobs?active=true`), progress and Cancel.
- **Ollama queue**: the schedule summary with an Edit link, the queue, Add, Run now, Flush everything.
- **Scheduled**: the user's Ollama window (on/off, edit) and, read-only, the nightly clean-up. Built so the syosetu
  fetch schedule can be added later.
- **History**: finished jobs of every kind, newest first, paged. An Ollama run opens to its stats: lines asked and
  done, lines failed, chunks, retries, average tokens/s, duration, why it ended.

### Retention and flush

- The **clean-up job** (server-wide, nightly, via the scheduler tick) finds chapters where every line with display
  text has a translation and the newest `translated_at` is more than 3 months old, and clears their suggestion text
  and chunk reasoning and prompt. Chunk stats and outcomes stay.
- **No `documents.completed_at` (review suggestion declined):** the clean-up starts from documents that still hold
  unflushed suggestion text, a small set by construction (it only grows with Ollama use and shrinks every night),
  and checks completeness for those alone. A stored completion stamp would have to be kept right by every path that
  writes lines (editor saves, Edit Source, split, merge, imports, series find and replace), and one missed path would
  silently keep or wrongly clear output. The 3-month clock is the newest `translated_at`, already indexed.
- **Flush** endpoints for a chapter, chapters, a volume, a series and everything do the same clearing at once.
- The migration deletes `mt_cache` rows whose backend starts with `ollama:`; Ollama no longer reads or writes the
  cache.

### Statistics → Ollama

- A new endpoint (`GET /stats/ollama?tz=`) built from `ollama_chunks` and outcomes, bucketed per run and per
  model + preset in the viewer's zone, like `GET /stats`.
- The page splits into **Translation** (the current content, unchanged) and **Ollama** tabs.

## Constraints

- Architecture rules in `CLAUDE.md` hold: routers from `api_router()`, handlers only `flush()`, tenancy via
  `scoped()`, models imported in `api/models/__init__.py`, autogenerated migrations, modules under ~400 lines.
- The Ollama runner and the scheduler commit outside the request boundary. They join the sanctioned exceptions and
  `CLAUDE.md` says so.
- Ollama calls take an injected `httpx.AsyncClient`; tests use `httpx.MockTransport`, never a live server.
- Chunk cutting, answer checking, `num_ctx` estimate, outcome scoring and preset values are pure modules with unit
  tests.
- Tests drive the runner and the scheduler tick directly, the way they drive `jobs.run_next()`.
- E2E: a Playwright flow with a mocked Ollama endpoint for the editor card and the Reasoning dialog, following the
  E2E conventions.

## Left to the builder

- Endpoint names and payloads; `npm run gen:api` after.
- Table and column names beyond what is described, and indexes.
- The server-wide cap on parallel runs, the retry count and pauses for an unreachable server, the queue item cap,
  the `keep_alive` value, the `num_ctx` rounding.
- Outcome thresholds (see Saved data).
- How the Volumes tab menus are worded.
- Splitting the work into phases and plans.
