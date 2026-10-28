# WordPress plugin 1.6.0: volume labels, Illustrations scheduling and status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send the plugin 1.6.0's new optional fields from ta-web: a per-volume `chapter_label` on chapter
publishes, `first_chapter_index` and `publish_date` on the Illustrations upload, a schedule slot for the
Illustrations chapter in batch publish, and a live status lookup for the Illustrations page.

**Architecture:** Two pure lookups join `chapter_number` in `api/library.py` (a chapter's position in its
volume, a volume's first chapter number). `build_chapter` (`api/publish.py`) adds the label to `doc_meta`,
and `build_payload` / `build_illustrations_payloads` (`api/core/wp.py`) copy the new fields into the
payloads. `illustrations.upload` takes an optional schedule and writes it back; the batch gives the
Illustrations chapter a slot; `wp_http` gains the illustrations form of `/status`, which the status refresh
uses instead of skipping the chapter. No migration, no SPA change.

**Tech Stack:** FastAPI, SQLAlchemy 2, httpx (`MockTransport` in tests), pytest.

**Spec:** `C:\dev\translation-assistant-publisher\docs\superpowers\specs\2026-10-28-volumes-and-chapter-navigation-design.md`,
section "ta-web side" (read the whole spec once: sections A, B and "Compatibility" explain what the plugin does
with each field). The plugin half is Punllarena/translation-assistant-publisher#1.

## Global Constraints

- Every new field is optional for the plugin; older plugins ignore them, so ta-web ships before or after it.
  Never make ta-web depend on a 1.6.0 answer for anything but the Illustrations status lookup.
- `chapter_label` is sent only when the series has no `syosetu_url` **and** the chapter has a `volume_id`.
  Value exactly `f"{volume.wp_name} Chapter {n}"`, `n` = 1-based position among the volume's chapters ordered
  by `(series_order, id)`, Illustrations chapters not counted. Loose chapters, chapters of series without
  volumes, and syosetu chapters send no `chapter_label` key at all.
- `chapter_index`, `previous_chapter_index`, passwords and the unlock chain stay series-wide (`chapter_number`);
  the label never feeds any of them.
- A changed label alone never causes the `confirm_republish` 409: store no label, compare no label.
- `first_chapter_index` = `chapter_number` of the volume's first non-Illustrations chapter by
  `(series_order, id)`, published or not; the key is omitted when the volume has none. It goes on **every**
  illustrations payload (`replace` and `append`); `publish_date` goes on the first (`replace`) payload only.
- `publish_date` format is the existing `wp_date()` (`%Y-%m-%dT%H:%M:%SZ`, UTC).
- Illustrations status: `GET /status` with `api_key`, `series_slug`, `illustrations=1`, `volume_title=<wp_name>`
  and **no** `chapter` param (the plugin answers 400 when both are present).
- Never treat a 409 from the plugin as an error path; the existing `ok_409` handling in `wp_http._send` stays.
- Routers via `api_router()`; handlers `flush()`, never `commit()`; no Python module over ~400 lines.
- Postgres at `127.0.0.1` (`TA_DATABASE_URL=postgresql+psycopg://ta:ta@127.0.0.1:5432/ta_test`); one pytest run at a time.

## Review Focus

1. **A chapter moved between volumes or reordered** must get the label of where it is *now* (position and the new
   volume's `wp_name`), while its `chapter_index` stays the series-wide number. Test: Task 1
   `test_label_follows_the_chapter_into_another_volume`.
2. **An Illustrations chapter sitting first in the volume** must not shift the label numbers (first text chapter is
   "Chapter 1"), and `first_chapter_index` must be the series-wide number, not 1, for Volume 2. Tests: Task 1
   `test_label_counts_chapters_in_the_volume_not_illustrations`, Task 2 `test_upload_sends_first_chapter_index_and_schedule`.
3. **A frozen `wp_volume_title`** (volume renamed after its first publish) must win in the label and the status
   lookup, so they match the published ToC heading. Tests: Task 1 `test_label_uses_the_frozen_wordpress_volume_name`,
   Task 4 `test_refresh_status_asks_for_the_illustrations_page`.
4. **A plugin older than 1.6.0** answers the illustrations status form with a 400 ("Missing series_slug or chapter"):
   the refresh must keep the cached status and show the message as `remote_error`, never 500 or wipe the status.
   Test: Task 4 `test_refresh_status_of_illustrations_on_an_old_plugin_keeps_the_cache`.
5. **An unscheduled batch** (`schedule: false`) must still send no `publish_date` for the Illustrations chapter and record
   `publish`; a scheduled single chapter publish must be unchanged. Test: Task 3
   `test_batch_now_publishes_illustrations_without_a_date`.

Accepted gap (no test): with a pre-1.6.0 plugin a scheduled Illustrations upload goes live at once, yet ta-web records
`future` until the next status refresh, which that plugin cannot answer. The `/illustrations` answer carries no post
status to check against.

---

### Task 1: `chapter_label` on chapter publishes

**Files:**
- Modify: `api/library.py` (add `volume_position` after `chapter_number`)
- Modify: `api/publish.py` (`build_chapter`)
- Modify: `api/core/wp.py` (`build_payload`)
- Test: `tests/test_core_wp.py`, `tests/test_wp_publish.py`

**Interfaces:**
- Produces: `volume_position(db: Session, doc: Document) -> int | None` in `api/library.py` — `None` when
  `doc.volume_id is None` or `doc.is_illustrations`; otherwise 1 + the number of non-Illustrations documents in
  the same volume whose `(series_order, id)` sorts before `doc`'s.
- Produces: `doc_meta["chapter_label"]: str` (always present in `Chapter.doc_meta`, `""` when no label).
- `build_payload` reads `doc_meta.get("chapter_label")`, so callers that build `doc_meta` by hand (tests,
  the summary) need no change.

- [ ] **Step 1: Write the failing core tests** in `tests/test_core_wp.py`

```python
def test_build_payload_sends_chapter_label():
    doc_meta, series_meta, lines = _sample_meta()
    doc_meta["chapter_label"] = "Volume 2 Chapter 3"
    assert build_payload(doc_meta, series_meta, lines, api_key="k")["chapter_label"] == "Volume 2 Chapter 3"


def test_build_payload_omits_blank_chapter_label():
    doc_meta, series_meta, lines = _sample_meta()
    assert "chapter_label" not in build_payload(doc_meta, series_meta, lines, api_key="k")
    doc_meta["chapter_label"] = ""
    assert "chapter_label" not in build_payload(doc_meta, series_meta, lines, api_key="k")


def test_build_payload_never_labels_the_synopsis():
    doc_meta, series_meta, lines = _sample_meta()
    doc_meta.update(series_order=0, chapter_label="Volume 1 Chapter 1")
    assert "chapter_label" not in build_payload(doc_meta, series_meta, lines, api_key="k")
```

- [ ] **Step 2: Write the failing route tests** in `tests/test_wp_publish.py` (uses the file's `wp_site` / `ready`
  fixtures; `posted` is `wp_site[1]`; import `Series` from `api.models` if needed)

```python
def _volume(db, series, subtitle, order):
    vol = Volume(series_id=series.id, subtitle=subtitle, volume_order=order)
    db.add(vol)
    db.flush()
    return vol


def test_label_counts_chapters_in_the_volume_not_illustrations(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    v1, v2 = _volume(db, ready, "One", 1), _volume(db, ready, "Two", 2)
    make_doc(me, ["一"], series=ready, order=1, volume=v1)
    make_doc(me, ["二"], series=ready, order=2, volume=v1)
    illus = make_doc(me, [], series=ready, order=3, volume=v2, title="Illustrations")
    illus.is_illustrations = True
    a = make_doc(me, ["三"], series=ready, order=4, volume=v2)
    b = make_doc(me, ["四"], series=ready, order=5, volume=v2)
    db.flush()
    for d in (a, b):
        assert app_client.post(f"/documents/{d.id}/wp/publish", json={}).status_code == 200
    assert [(p["chapter_index"], p["chapter_label"]) for p in posted] == [
        (3, f"{v2.wp_name} Chapter 1"), (4, f"{v2.wp_name} Chapter 2")]


def test_no_label_for_loose_chapters_or_syosetu_series(app_client, me, ready, make_series, make_doc, wp_site, db):
    _, posted = wp_site
    loose = make_doc(me, ["一"], series=ready, order=1)
    syo = make_series(me, "Syo")
    syo.wp_series_slug, syo.wp_series_title_short = "syo", "Syo"
    syo.syosetu_url = "https://ncode.syosetu.com/n1234ab/"
    vol = _volume(db, syo, "One", 1)
    in_vol = make_doc(me, ["二"], series=syo, order=1, volume=vol)
    db.flush()
    for d in (loose, in_vol):
        assert app_client.post(f"/documents/{d.id}/wp/publish", json={}).status_code == 200
    assert all("chapter_label" not in p for p in posted)


def test_label_uses_the_frozen_wordpress_volume_name(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    vol = _volume(db, ready, "One", 1)
    vol.wp_volume_title = "Book One"
    doc = make_doc(me, ["一"], series=ready, order=1, volume=vol)
    db.flush()
    app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert posted[0]["chapter_label"] == "Book One Chapter 1"


def test_label_follows_the_chapter_into_another_volume(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    v1, v2 = _volume(db, ready, "One", 1), _volume(db, ready, "Two", 2)
    make_doc(me, ["一"], series=ready, order=1, volume=v1)
    moved = make_doc(me, ["二"], series=ready, order=2, volume=v1)
    make_doc(me, ["三"], series=ready, order=3, volume=v2)
    db.flush()
    r = app_client.post(f"/volumes/{v2.id}/documents", json={"document_ids": [moved.id]})
    assert r.status_code == 200
    db.refresh(moved)
    app_client.post(f"/documents/{moved.id}/wp/publish", json={})
    assert posted[-1]["chapter_label"] == f"{v2.wp_name} Chapter 2"
    assert posted[-1]["chapter_index"] == moved.series_order == 3


def test_a_changed_label_alone_needs_no_confirmation(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    vol = _volume(db, ready, "One", 1)
    doc = make_doc(me, ["一"], series=ready, order=2, volume=vol)
    doc.wp_chapter_index = 2  # published once as chapter 2; WordPress no longer has it
    db.flush()
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 200
    assert posted[-1]["chapter_label"] == f"{vol.wp_name} Chapter 1"
```

`POST /volumes/{id}/documents` (`assign_documents`) appends the chapter at the volume's end and `arrange()` renumbers,
so the moved chapter becomes `series_order` 3, second in Two.

- [ ] **Step 3: Run them to see them fail**

Run: `pytest tests/test_core_wp.py tests/test_wp_publish.py -k "label" -v`
Expected: FAIL (`KeyError: 'chapter_label'` / key missing).

- [ ] **Step 4: Implement**

- `volume_position` in `api/library.py` as in Interfaces (one `count()` query, like `chapter_number`).
- In `build_chapter`, after `volume` is read: `label = f"{volume.wp_name} Chapter {volume_position(db, doc)}"` when
  `volume is not None and not series.syosetu_url`, else `""`; add `"chapter_label": label` to `doc_meta`.
- In `build_payload`, inside the existing `if doc_meta["series_order"] != 0:` block:
  `if doc_meta.get("chapter_label"): payload["chapter_label"] = doc_meta["chapter_label"]`.

- [ ] **Step 5: Run the tests and the WordPress suites**

Run: `pytest tests/test_core_wp.py tests/test_wp_publish.py tests/test_wp_jobs.py tests/test_wp_volume_name.py -v` then `ruff check .`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add api/library.py api/publish.py api/core/wp.py tests/test_core_wp.py tests/test_wp_publish.py
git commit -m "feat(wp): send a per-volume chapter_label"
```

---

### Task 2: Illustrations upload sends `first_chapter_index` and a schedule

**Files:**
- Modify: `api/library.py` (add `first_chapter_number`)
- Modify: `api/core/wp.py` (`build_illustrations_payloads`)
- Modify: `api/illustrations.py` (`upload`)
- Test: `tests/test_core_wp.py`, `tests/test_wp_jobs.py`

**Interfaces:**
- Consumes: `chapter_number(db, doc)` (existing).
- Produces: `first_chapter_number(db: Session, volume_id: int) -> int | None` in `api/library.py` — `chapter_number`
  of the volume's first non-Illustrations document by `(series_order, id)`; `None` when there is none.
- Produces: `build_illustrations_payloads(doc_meta, series_meta, images, api_key, cover=None, *, scheduled_date: str | None = None)`;
  reads `doc_meta.get("first_chapter_index")` (an `int` or `None`).
- Produces: `upload(db, c, doc, endpoint, key, progress=None, *, scheduled: datetime | None = None) -> dict` (same return shape).

- [ ] **Step 1: Write the failing core test** in `tests/test_core_wp.py` (import `build_illustrations_payloads`)

```python
def test_illustrations_payloads_carry_first_chapter_index_and_date(monkeypatch):
    monkeypatch.setattr("api.core.wp._ILLUS_BATCH_BYTES", 10)
    images = [{"src_path": f"{n}.png", "data": b"X" * 6} for n in "ab"]
    meta = {"series_title": "S", "volume_title": "Volume 2", "first_chapter_index": 14}
    series_meta = {"series_slug": "s", "series_title_short": "S"}
    ps = build_illustrations_payloads(meta, series_meta, images, api_key="k",
                                      scheduled_date="2026-11-01T11:00:00Z")
    assert [p["mode"] for p in ps] == ["replace", "append"]
    assert [p["first_chapter_index"] for p in ps] == [14, 14]
    assert ps[0]["publish_date"] == "2026-11-01T11:00:00Z" and "publish_date" not in ps[1]
    bare = build_illustrations_payloads({"series_title": "S", "first_chapter_index": None},
                                        series_meta, images[:1], api_key="k")
    assert "first_chapter_index" not in bare[0] and "publish_date" not in bare[0]
```

- [ ] **Step 2: Write the failing upload test** in `tests/test_wp_jobs.py` (uses `plates`, `ready`, `wp_site`)

```python
def test_upload_sends_first_chapter_index_and_schedule(me, ready, make_doc, wp_site, db):
    from datetime import UTC, datetime

    from api import illustrations
    v1 = Volume(series_id=ready.id, subtitle="Vol 0")
    db.add(v1)
    db.flush()
    for i in (1, 2):
        make_doc(me, [f"行{i}"], series=ready, order=i, volume=v1)
    vol, doc = plates(me, ready, make_doc, db)
    doc.series_order = 3
    make_doc(me, ["三"], series=ready, order=4, volume=vol)  # unpublished: still counts
    db.flush()
    when = datetime(2026, 11, 1, 11, tzinfo=UTC)
    with publish_job.http_client() as c:
        illustrations.upload(db, c, doc, SITE, "k" * 12, scheduled=when)
    body = wp_site["posted"][0][1]
    assert (body["first_chapter_index"], body["publish_date"]) == (3, "2026-11-01T11:00:00Z")
    assert (doc.wp_status, doc.wp_scheduled_for, doc.wp_published_at) == ("future", when, when)


def test_upload_without_chapters_omits_first_chapter_index(me, ready, make_doc, wp_site, db):
    from api import illustrations
    _, doc = plates(me, ready, make_doc, db)
    with publish_job.http_client() as c:
        illustrations.upload(db, c, doc, SITE, "k" * 12)
    body = wp_site["posted"][0][1]
    assert "first_chapter_index" not in body and "publish_date" not in body
    assert doc.wp_status == "publish" and doc.wp_scheduled_for is None
```

- [ ] **Step 3: Run them to see them fail**

Run: `pytest tests/test_core_wp.py tests/test_wp_jobs.py -k "first_chapter_index or illustrations_payloads" -v`
Expected: FAIL (unexpected keyword `scheduled` / missing keys).

- [ ] **Step 4: Implement**

- `first_chapter_number` in `api/library.py` as in Interfaces.
- `build_illustrations_payloads`: add `first_chapter_index` to `base` when `doc_meta.get("first_chapter_index") is not None`
  (so it reaches every batch); add `publish_date` to the `i == 0` payload when `scheduled_date` is given.
- `upload`: pass `{"series_title": ..., "volume_title": volume.wp_name, "first_chapter_index": first_chapter_number(db, volume.id)}`
  and `scheduled_date=publish.wp_date(scheduled) if scheduled else None`. The write-back becomes
  `wp_status = "future" if scheduled else "publish"`, `wp_published_at = scheduled or datetime.now(UTC)`,
  `wp_scheduled_for = scheduled` (the same rule as `publish.record`).

- [ ] **Step 5: Run the tests and the WordPress suites**

Run: `pytest tests/test_core_wp.py tests/test_wp_jobs.py tests/test_wp_publish.py -v` then `ruff check .`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add api/library.py api/core/wp.py api/illustrations.py tests/test_core_wp.py tests/test_wp_jobs.py
git commit -m "feat(wp): send first_chapter_index and publish_date with the illustrations page"
```

---

### Task 3: Batch publish gives the Illustrations chapter a schedule slot

**Files:**
- Modify: `api/routers/wp.py` (`batch_publish`)
- Modify: `api/publish_job.py` (`_publish_one`)
- Test: `tests/test_wp_jobs.py`

**Interfaces:**
- Consumes: `illustrations.upload(..., scheduled=...)` from Task 2.
- Job params are unchanged in shape: each item is `{"document_id", "scheduled_for"}`; the Illustrations item now
  carries a slot like any other.

- [ ] **Step 1: Replace the obsolete test.** `test_batch_gives_illustrations_no_slot` pins the old requirement
  (spec item 4 reverses it). Delete it and add, in its place:

```python
def test_batch_gives_illustrations_a_slot(app_client, me, ready, make_doc, wp_site, db):
    vol, doc = plates(me, ready, make_doc, db)
    texts = [make_doc(me, [f"行{i}"], series=ready, order=i + 1, volume=vol) for i in (1, 2)]
    r = app_client.post("/wp/batch", json={
        "document_ids": [d.id for d in (doc, *texts)], "schedule": True,
        "start": "2026-11-01T20:00:00+09:00", "chapters_per_day": 2, "tz": "Asia/Tokyo"})
    assert r.status_code == 202
    params = db.get(Job, r.json()["id"]).params_json["chapters"]
    assert [p["scheduled_for"] for p in params] == [
        "2026-11-01T20:00:00+09:00", "2026-11-01T21:00:00+09:00", "2026-11-02T21:00:00+09:00"]
    jobs.run_next()
    dates = [(p, b.get("publish_date")) for p, b in wp_site["posted"]]
    assert dates == [(ILLUS, "2026-11-01T11:00:00Z"), (PUBLISH, "2026-11-01T12:00:00Z"),
                     (PUBLISH, "2026-11-02T12:00:00Z")]
    db.refresh(doc)
    assert doc.wp_status == "future"
    assert doc.wp_scheduled_for == datetime(2026, 11, 1, 11, tzinfo=UTC)  # import datetime, UTC at the top


def test_batch_now_publishes_illustrations_without_a_date(app_client, me, ready, make_doc, wp_site, db):
    vol, doc = plates(me, ready, make_doc, db)
    make_doc(me, ["一"], series=ready, order=2, volume=vol)
    app_client.post("/wp/batch", json={"document_ids": [doc.id], "schedule": False})
    jobs.run_next()
    assert all("publish_date" not in b for _, b in wp_site["posted"])
    db.refresh(doc)
    assert doc.wp_status == "publish" and doc.wp_scheduled_for is None
```

These are the three slots `test_batch_schedules_in_order_and_records_each` already pins (no default time set, so the
next day keeps 21:00); the point is that the Illustrations chapter now takes the **first** one.

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/test_wp_jobs.py -k "illustrations" -v`
Expected: `test_batch_gives_illustrations_a_slot` FAILS (first `scheduled_for` is `None`).

- [ ] **Step 3: Implement**

- `batch_publish`: drop the `numbered` count and the "takes no slot" comment; compute
  `publish.batch_slots(body.start, len(docs), ...)` (or `[None] * len(docs)`) and give every item `next(slots)`.
- `_publish_one`: in the Illustrations branch call `illustrations.upload(db, c, doc, endpoint, key, scheduled=scheduled)`
  and return `"scheduled_for": item["scheduled_for"]` (already in `row`); drop the "no schedule slot" comment.

- [ ] **Step 4: Run the WordPress suites**

Run: `pytest tests/test_wp_jobs.py tests/test_wp_publish.py -v` then `ruff check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add api/routers/wp.py api/publish_job.py tests/test_wp_jobs.py
git commit -m "feat(wp): schedule the Illustrations chapter in batch publish"
```

---

### Task 4: Status refresh asks WordPress about the Illustrations page; docs

**Files:**
- Modify: `api/core/wp_http.py` (add `check_illustrations_status`)
- Modify: `api/routers/wp.py` (`refresh_status`, and the `publish_illustrations` docstring)
- Modify: `docs/TODO.md`, `CLAUDE.md`
- Test: `tests/test_core_wp_http.py`, `tests/test_wp_publish.py`

**Interfaces:**
- Produces: `check_illustrations_status(c: httpx.Client, endpoint_url: str, api_key: str, series_slug: str, volume_title: str) -> dict`
  in `api/core/wp_http.py`: `GET site_base(endpoint_url) + STATUS_PATH` with params
  `{"api_key", "series_slug", "illustrations": 1, "volume_title"}`, `timeout=10`, through `_send` (no `ok_409`).
- `refresh_status` keeps its response shape; for the Illustrations chapter `previous_scheduled` stays `False` and
  `suggested_slot` `None` (its single publish offers no date).

- [ ] **Step 1: Write the failing HTTP test** in `tests/test_core_wp_http.py`

```python
def test_illustrations_status_sends_the_illustrations_form():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"status": "future", "post_url": "u"})

    with make(handler) as c:
        out = wp_http.check_illustrations_status(c, SITE, "key", "sword", "Volume 2")
    assert out == {"status": "future", "post_url": "u"}
    q = dict(seen[0].url.params)
    assert seen[0].url.path == "/wp-json/ta-publisher/v1/status"
    assert q == {"api_key": "key", "series_slug": "sword", "illustrations": "1", "volume_title": "Volume 2"}
```

- [ ] **Step 2: Replace `test_refresh_status_skips_the_illustrations_chapter`** in `tests/test_wp_publish.py`
  (spec item 5 reverses it) with:

```python
def test_refresh_status_asks_for_the_illustrations_page(app_client, me, ready, make_doc, monkeypatch, db):
    calls = []

    def handle(request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={"status": "future", "post_url": "x"})

    monkeypatch.setattr(wp_router, "http_client",
                        lambda: wp_router.wp_http.client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr("api.publish.check_user_url", lambda url, allow, label: None)
    vol = Volume(series_id=ready.id, subtitle="V1", wp_volume_title="Book One")
    db.add(vol)
    db.flush()
    illus = make_doc(me, [], series=ready, order=1, title="Illustrations", volume=vol)
    illus.is_illustrations = True
    illus.wp_status = "publish"
    db.flush()
    r = app_client.post(f"/documents/{illus.id}/wp/status")
    assert r.status_code == 200
    assert calls[0]["illustrations"] == "1" and calls[0]["volume_title"] == "Book One"
    assert "chapter" not in calls[0]
    assert (r.json()["cached_status"], r.json()["status"], r.json()["post_url"]) == ("publish", "future", "x")
    assert r.json()["previous_scheduled"] is False and r.json()["suggested_slot"] is None
    db.refresh(illus)
    assert illus.wp_status == "future"


def test_refresh_status_of_illustrations_on_an_old_plugin_keeps_the_cache(
        app_client, me, ready, make_doc, monkeypatch, db):
    monkeypatch.setattr(wp_router, "http_client", lambda: wp_router.wp_http.client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"error": "Missing series_slug or chapter"}))))
    monkeypatch.setattr("api.publish.check_user_url", lambda url, allow, label: None)
    vol = Volume(series_id=ready.id, subtitle="V1")
    db.add(vol)
    db.flush()
    illus = make_doc(me, [], series=ready, order=1, title="Illustrations", volume=vol)
    illus.is_illustrations = True
    illus.wp_status, illus.wp_post_url = "future", "keep"
    db.flush()
    r = app_client.post(f"/documents/{illus.id}/wp/status")
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["post_url"]) == ("future", "keep")
    assert r.json()["remote_error"] == "Missing series_slug or chapter"
```

- [ ] **Step 3: Run them to see them fail**

Run: `pytest tests/test_core_wp_http.py tests/test_wp_publish.py -k "status" -v`
Expected: FAIL (`check_illustrations_status` missing; refresh makes no call).

- [ ] **Step 4: Implement**

- `check_illustrations_status` as in Interfaces, next to `check_status`.
- `refresh_status`: replace the early return with a branch inside the existing `try`: for `doc.is_illustrations`,
  read `volume = db.get(Volume, doc.volume_id)` and call `check_illustrations_status(c, endpoint, key,
  series.wp_series_slug, volume.wp_name)`; otherwise `check_status` as today. Both feed
  `publish.apply_remote_status`. After the `try`, compute `previous, slot` with `suggested_slot` only for a
  non-Illustrations chapter (`False, None` otherwise). An Illustrations chapter with no `volume_id` (never true
  under the marking rules) keeps the cached status without asking.
- `publish_illustrations` docstring: drop "The plugin has no status lookup for that page"; the stored status still
  guards re-publishing (unchanged behaviour).

- [ ] **Step 5: Update the docs**

- `docs/TODO.md`: under "WordPress: volume-aware chapter indexing" and "WordPress plugin: volume Illustrations page
  first", replace each body with one paragraph: designed in the plugin's
  `docs/superpowers/specs/2026-10-28-volumes-and-chapter-navigation-design.md` (plugin 1.6.0,
  Punllarena/translation-assistant-publisher#1) and its "ta-web side"; ta-web sends `chapter_label`,
  `first_chapter_index` and the Illustrations `publish_date`, and asks `/status?illustrations=1`. Keep both headings.
- `CLAUDE.md`, in the "Volume Illustrations chapter" paragraph: replace "batch publish uploads it the same way." with
  "batch publish uploads it the same way and gives it a schedule slot (`publish_date` on the first batch); its status
  refresh asks `/status?illustrations=1&volume_title=<wp_name>`." In the "Volume naming" paragraph append:
  "Chapters in a volume of a non-syosetu series also send `chapter_label` = `f\"{wp_name} Chapter {n}\"`
  (`volume_position` in `api/library.py`); the label never feeds the series-wide `chapter_index`."

- [ ] **Step 6: Run everything**

Run: `ruff check .` then `pytest`
Expected: ruff clean, full suite PASS. No `web/` change, so `npm test` and `npm run gen:api` are not needed
(`WpStatusOut`, `IllustrationsIn` and `BatchPublishIn` are unchanged).

- [ ] **Step 7: Commit**

```bash
git add api/core/wp_http.py api/routers/wp.py tests/test_core_wp_http.py tests/test_wp_publish.py docs/TODO.md CLAUDE.md
git commit -m "feat(wp): status refresh for the Illustrations page; point TODOs at the 1.6.0 spec"
```
