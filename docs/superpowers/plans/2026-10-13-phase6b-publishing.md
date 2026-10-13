# Phase 6b — Publishing and Statistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the publishing half of spec phase 6:
- WordPress publish of one chapter, with the re-publish safeguard, passwords and scheduling;
- batch publish/schedule of selected chapters and per-volume illustration upload, both as jobs;
- per-user WordPress settings (endpoint, API key, defaults) and per-series WordPress fields;
- statistics: heatmap, per-day table, streaks, period comparisons, per-series breakdown.

**Architecture:**
- **Ported core, no DB imports:**
  - `api/core/wp.py`: the desktop `wp_publisher.py` payload builders, slug, password, auto-schedule and URL helpers, verbatim.
  - `api/core/wp_http.py`: the desktop `check_status`, `publish`, `publish_illustrations` over an injected `httpx.Client` (split out because the desktop module is 432 lines).
  - `api/core/images.py`: the desktop `imageopt.shrink_image`, Pillow instead of Qt.
  - `api/core/stats.py`: the desktop `compute_streaks` and `compute_period_comparisons`, verbatim, plus `summarize`.
- **DB layer:** `api/wp_prefs.py` (per-user WordPress preferences in `user_settings`), `api/publish.py` (the desktop `wp_publish_flow.py` without Qt: config, chapter build, result write-back, schedule helpers), `api/publish_job.py` (the `wp_publish` and `wp_illustrations` job handlers).
- **Routers:** `api/routers/wp.py` (prefs, connection test, status refresh, one-chapter publish, batch and illustrations enqueue) and `api/routers/stats.py`.
- **SPA:** Settings → WordPress; WordPress fields and TOC link on the series page; Publish dialog per picker row; batch publish from the picker selection; Publish illustrations per volume; a Statistics page with an SVG heatmap.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 / Postgres (`timezone()` bucketing), httpx (`MockTransport` in tests), Pillow and tzdata (new runtime dependencies), React 19, TanStack Query, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-10-web-app-port-design.md` (§4 credentials, §10 Publishing and statistics, §12 Testing, §15 phase 6). Desktop reference (read-only): `/home/pun/workspace/TranslationAssistant-PySide6-Port/` — `translation_assistant/wp_publisher.py`, `imageopt.py`, `ui/wp_publish_flow.py`, `ui/dlg_open.py` (`_on_publish_batch`, `_BatchPublishDialog`), `ui/dlg_wp_settings.py`, `ui/dlg_series.py` (`_on_set_wp_fields`, `_toc_url`), `ui/main_widget.py` (`_on_publish_volume_illustrations`), `ui/dlg_stats.py`, `db.py` (`get_*_stats`, `get_wp_dates`), `core.py` (`compute_streaks`, `compute_period_comparisons`). WordPress plugin (read-only): `/home/pun/workspace/wp-dev/plugins/translation-assistant-publisher/`.

## Global Constraints

- **Routers:**
  - Every router is built with `api_router()`. Handlers `flush()` and never `commit()`.
  - `tests/test_commit_boundary.py` must keep passing.
- **Commits outside the request:** only the two sanctioned ones — the job worker (`api/jobs.py`) and the `/mt/stream` cache write. The new job handlers commit only through `ctx.progress()`.
- **Tenancy:**
  - Fetch user-owned rows with `scoped()` / `scoped_volume()`; an id in a body goes through `owned_ref()`.
  - Another user's id is a 404 (path) or 422 (body), never a 403. A job only ever touches rows owned by `job.user_id`, and only with `job.user_id`'s credential.
- **Secrets:** the WordPress API key is a `wordpress` row in `api_credentials` (Fernet, spec §4). No endpoint returns it, and no error message or job row contains it.
- **Network:**
  - No live network in tests. WordPress HTTP goes through an injected `httpx.Client`; tests use `httpx.MockTransport`.
  - Every WordPress call first passes `check_user_url` (`api/mt/urls.py`) unless `TA_WP_ALLOW_PRIVATE_URLS=true`. Redirects are never followed.
- **Module size:** no Python module over ~400 lines; no React component file over ~300.
- **Migrations:** none expected. If a model changes, autogenerate (`alembic revision --autogenerate`).
- **API types:** run `npm run gen:api` in `web/` after API changes the SPA consumes. Commit `web/src/api/schema.d.ts`; `web/openapi.json` is gitignored.
- **Environment:**
  - venv `.venv` with `.[dev,mecab]`, and `TA_SECRET_KEY=dev-secret-key-at-least-32-characters-long`.
  - Postgres runs on localhost:5432. Never run `docker compose down`.
  - `pytest -q` prints only dots, so judge a run by its exit code.
- **Commit trailers:** a `Co-Authored-By` line for the authoring model, plus whatever `Claude-Session:` line the executing session's harness specifies. Put one blank line between the subject and the trailers.
- **E2E conventions** (CLAUDE.md):
  - Each spec owns its seeded rows.
  - Seed names must not contain "E2E chapter".
  - The database resets once per run.

## Rulings (user choices marked ✔)

1. ✔ **Image downscaling uses Pillow** (new runtime dependency), porting `shrink_image` (longest side ≤ 1600 px, JPEG ≤ 350 KB, quality 82 → 40). Undecodable input, and decompression bombs, return the original bytes.
2. ✔ **Statistics bucket days in the viewer's time zone.** The SPA sends its IANA zone (`Intl.DateTimeFormat().resolvedOptions().timeZone`) as `?tz=`; Postgres buckets with `timezone(:tz, translated_at)`. The desktop bucketed by UTC.
3. ✔ **One-chapter publish is a request; batch publish and volume illustrations are jobs** (`wp_publish`, `wp_illustrations`).
   ```python
   # ponytail: a publish request holds a pool connection for up to ~25 s (status + publish timeouts); make it a job if that starves the pool
   ```
4. **WordPress credentials and preferences:**
   - The endpoint URL and API key are one `api_credentials` row: `kind="wordpress"`, `name=""`, `secret` = the plugin key, `endpoint_url` = the site or publish URL (normalized at call time, as the desktop did).
   - The other desktop `WP*` QSettings become `user_settings` keys with the desktop defaults: `wp_password_enabled` (false), `wp_unlock_after` (3, 1–99), `wp_attribution_enabled` (true), `wp_default_schedule_time` ("" or `HH:MM`), `wp_chapters_per_day` (1, 1–99), `wp_schedule_scope_global` (false). A value of the wrong shape reads as its default.
   - `stats_metric` (`paragraphs` | `chars` | `en_words`) is a `user_settings` key too.
5. **SSRF:** `check_user_url(endpoint, TA_WP_ALLOW_PRIVATE_URLS, "WordPress")` runs before every WordPress call (test, status, publish, each job). It is a new flag, default false; the MT flag is not reused, so allowing a private Ollama does not allow a private WordPress. The WordPress client never follows redirects: a 3xx is an error naming the `Location`, because each hop would need the check again and the request carries the API key.
6. **Re-publish safeguard (spec §10), enforced by the server:**
   - Single publish first asks WordPress for the chapter's status. If the cached `wp_status` or the remote status is `publish` or `future`, the publish is a 409 unless the body says `confirm_republish: true`. The SPA turns the 409 into a confirm and resends.
   - If the status check fails (WordPress unreachable), the cached status decides — the desktop's behaviour.
   - Batch publish checks the cached status only (as the desktop batch did). Without the batch's `confirm_republish`, an already-live chapter is a failed row "already published or scheduled", and the rest continue. So re-running an interrupted batch resumes it.
7. **Dates:**
   - `documents.wp_published_at` holds the WordPress date: the publish time, or the scheduled slot. This is what the importer stored from the desktop's `wp_date`. `wp_scheduled_for` is the slot when scheduled, else NULL.
   - `get_wp_dates` becomes `wp_dates()` over `wp_published_at` for `wp_status in ('publish','future')`.
   - A status refresh writes the remote status and post URL but never the dates. (The desktop wrote `result.get("date")`, which the plugin's `/status` never returns, so it wiped `wp_date`.) A remote `not_found` clears `wp_status` and `wp_post_url`.
8. **Scheduling time zone:** the client sends aware datetimes and, where "same day" matters (`compute_auto_schedule`, batch slots), its IANA zone. The desktop used the machine's local zone. WordPress receives UTC `%Y-%m-%dT%H:%M:%SZ`, as before.
9. **`wp_post_id` stays NULL.** The plugin's response carries `page_url`/`post_url` but no post id. Task 12 updates the model comment.
10. **Passwords** generated for password-protected chapters are returned in the publish response and kept in the batch job's `result_json`, so the batch summary can show them later. They are WordPress post passwords that readers receive, not account secrets.
11. **Chapter title:** the payload's `chapter_title` is `documents.chapter_title`, or `documents.title` when that is empty (web-created chapters).
12. **`resolve_wp_password_enabled` takes `bool | None`** (the `series.wp_password_enabled` column) instead of the desktop's `"1"`/`"0"`/`None` settings dict. This is the one signature change in the port.
13. **Connection test** calls `/status` with the saved key and a probe slug. The desktop POSTed `{}` without a key, which could not tell a wrong key from a right one. A 401 reads "rejected the API key"; a `not_found` answer means connected.
14. **One active `wp_publish` job per user:** a second enqueue while one is queued or running is a 409 (SELECT-only check, the same race as the syosetu fetch).
15. **Jobs hardening (phase 6a carry-over):** a job row deleted while it runs (its user was deleted) ends quietly instead of logging a failure, and the job SSE ends when the row disappears.

## Review Focus

1. **A WordPress endpoint pointing inward:** `http://127.0.0.1/`, `http://10.0.0.5/`, `http://169.254.169.254/`, or a public host that answers with a redirect to one of those. Each is refused before any request leaves for the bad address, with a readable 422 (or a failed job), never a 500. Tested in Tasks 2 and 3.
2. **A chapter already live on WordPress that the app thinks is unpublished** (cached `wp_status` empty, remote `publish`): single publish is a 409 until confirmed. If the status check fails, the cached status decides, and a failed publish writes nothing (502). Tested in Task 4.
3. **Hostile or huge images on the publish path:** an undecodable blob, an alpha PNG, or an image past Pillow's decompression-bomb limit. Each publishes (the original bytes when it cannot be decoded) and never 500s. Illustrations over the ~800 KB budget split into several requests. Tested in Tasks 2 and 6.
4. **Time zones:** an unknown or malicious `tz` (`Mars/Base`, `../../etc/passwd`, 200 characters) is a 422. A line translated at 23:30 UTC counts on the next day for `Asia/Tokyo`. Auto-schedule "same day" is judged in the sent zone. Tested in Tasks 4 and 7.
5. **Tenancy and partial failure in jobs:** another user's document in a batch is a 422 at enqueue; a chapter deleted after enqueue is a failed row; one WordPress error fails only its row; cancel stops between chapters and keeps what was published. Tested in Task 6.

---

### Task 1: Port the WordPress payload builders

**Files:**
- Create: `api/core/wp.py`, `tests/test_core_wp.py`

**Interfaces:**
- Produces (all verbatim from the desktop unless noted):
  - `class WPPublishError(Exception)` with `.message: str`, `.status_code: int | None`
  - `slugify(text) -> str`, `build_chapter_body(lines) -> str`, `get_first_line(lines) -> str`
  - `build_image_payload(lines, images) -> list[dict]`
  - `build_illustrations_payloads(doc_meta, series_meta, images, api_key, cover=None) -> list[dict]`
  - `resolve_wp_password_enabled(series_value: bool | None, global_enabled: bool) -> bool` (ruling 12)
  - `compute_password_fields(chapter_index, unlock_after) -> tuple[str | None, int | None]`
  - `compute_auto_schedule(prev_wp_date, wp_dates, chapters_per_day, default_time, tz=None) -> datetime` (naive, in `tz`)
  - `build_payload(doc_meta, series_meta, lines, api_key, *, password, unlock_chapter_index, scheduled_date, attribution, images, cover, previous_chapter_index) -> dict`
  - `ENDPOINT_PATH = "/wp-json/ta-publisher/v1/publish"`, `normalize_endpoint_url(url) -> str`, `site_base(url) -> str`, `toc_page_url(endpoint_url, series_slug) -> str`
  - Image dicts: `{"id", "anchor_position", "src_path", "data"}`; line dicts: `{"prefix", "translated_text"}`.

- [ ] **Step 1: Port the desktop tests**
  - Copy `/home/pun/workspace/TranslationAssistant-PySide6-Port/tests/test_wp_publisher.py` to `tests/test_core_wp.py`.
  - Change every `from translation_assistant.wp_publisher import ...` to `from api.core.wp import ...`, and drop `publish` from the first import (it moves to Task 2).
  - Delete the HTTP tests (they move to Task 2): every `test_publish_*` that patches `urllib`, the four `test_check_status_*`, and the four `test_publish_illustrations_*`. Delete the now-unused `json`, `patch`, `MagicMock`, `URLError`, `HTTPError` imports.
  - Replace the four `test_publish_wp_password_resolution_*` tests (ruling 12) with:

```python
@pytest.mark.parametrize(("series", "global_on", "expected"), [
    (True, False, True), (False, True, False), (None, True, True), (None, False, False),
])
def test_password_resolution_series_override_then_global(series, global_on, expected):
    assert resolve_wp_password_enabled(series, global_enabled=global_on) is expected
```

  - Add one test for the helper the desktop inlined three times:

```python
from api.core.wp import site_base


@pytest.mark.parametrize("url", [
    "https://example.com", "https://example.com/",
    "https://example.com/wp-json/ta-publisher/v1/publish",
    "https://example.com/wp-json/ta-publisher/v1/publish/",
])
def test_site_base_strips_the_publish_path_and_slashes(url):
    assert site_base(url) == "https://example.com"
```

- [ ] **Step 2: Run them to verify they fail**
  - Run: `pytest tests/test_core_wp.py -q`
  - Expected: FAIL with `ModuleNotFoundError: No module named 'api.core.wp'`.

- [ ] **Step 3: Write `api/core/wp.py`**
  - Module docstring:

```python
"""WordPress publish payloads, from the desktop translation_assistant/wp_publisher.py:
the builders, slug, password, auto-schedule and URL helpers, verbatim. The HTTP calls
are in api/core/wp_http.py (the desktop module is 432 lines)."""
```

  - Take verbatim from `translation_assistant/wp_publisher.py`: `WPPublishError`, `slugify`, `_BOLD_RE`, `_bold_to_html`, `build_chapter_body`, `get_first_line`, `_encode_image`, `build_image_payload`, `_ILLUS_BATCH_BYTES`, `build_illustrations_payloads`, `_ALPHANUM`, `compute_password_fields`, `_WP_DATE_FMT`, `compute_auto_schedule`, `build_payload`, `normalize_endpoint_url`, `toc_page_url`, with their docstrings and comments. Keep the stdlib imports they use (`base64`, `mimetypes`, `posixpath`, `re`, `secrets`, `string`, `datetime`...); drop `json`, `urllib.*`.
  - Rename `_ENDPOINT_PATH` to `ENDPOINT_PATH` (Task 2 imports it).
  - Replace `resolve_wp_password_enabled` with:

```python
def resolve_wp_password_enabled(series_value: bool | None, global_enabled: bool) -> bool:
    """Password protection for a publish: the series override (series.wp_password_enabled)
    when set, else the user's default. The desktop took its "1"/"0"/None settings dict."""
    return global_enabled if series_value is None else series_value
```

  - Add `site_base` and use it in `toc_page_url`:

```python
def site_base(url: str) -> str:
    """The site root of an endpoint URL: the desktop stripped the publish path inline in
    toc_page_url, check_status and publish_illustrations."""
    base = url.rstrip("/")
    if base.endswith(ENDPOINT_PATH):
        base = base[: -len(ENDPOINT_PATH)]
    return base


def toc_page_url(endpoint_url: str, series_slug: str) -> str:
    """Series TOC page URL — site root + slug, same shape as the server's page_url."""
    return f"{site_base(endpoint_url)}/{series_slug}/"
```

- [ ] **Step 4: Run the tests to verify they pass**
  - Run: `pytest tests/test_core_wp.py -q && ruff check api/core/wp.py tests/test_core_wp.py`
  - Expected: PASS, no lint errors.

- [ ] **Step 5: Commit**

```bash
git add api/core/wp.py tests/test_core_wp.py
git commit -m "feat(api): port the WordPress payload builders"
```

---

### Task 2: WordPress HTTP client and image downscaling

**Files:**
- Create: `api/core/wp_http.py`, `api/core/images.py`, `tests/test_core_wp_http.py`, `tests/test_core_images.py`
- Modify: `pyproject.toml` (add `"Pillow>=10.4"` and `"tzdata>=2024.1"` to `dependencies`)

**Interfaces:**
- Consumes: `WPPublishError`, `ENDPOINT_PATH`, `normalize_endpoint_url`, `site_base` from Task 1.
- Produces:
  - `wp_http.client(transport: httpx.BaseTransport | None = None) -> httpx.Client`
  - `wp_http.check_status(c, endpoint_url, api_key, series_slug, chapter) -> dict`
  - `wp_http.publish(c, endpoint_url, payload) -> dict` (a 409 answer is a result, not an error)
  - `wp_http.publish_illustrations(c, endpoint_url, payload) -> dict`
  - `images.shrink_image(data: bytes, max_dim=1600, target_bytes=350_000) -> bytes` (returns `data` itself when it leaves it alone)

- [ ] **Step 1: Install the new dependencies**
  - Add `"Pillow>=10.4",` and `"tzdata>=2024.1",` to `[project] dependencies` in `pyproject.toml` (tzdata: `zoneinfo` needs a zone database, and slim containers may lack `/usr/share/zoneinfo`).
  - Run: `pip install -e ".[dev,mecab]"`

- [ ] **Step 2: Write the failing HTTP tests** in `tests/test_core_wp_http.py`:

```python
import json

import httpx
import pytest

from api.core import wp_http
from api.core.wp import WPPublishError

SITE = "https://blog.example.com"


def make(handler):
    return wp_http.client(transport=httpx.MockTransport(handler))


def test_publish_posts_json_to_the_normalized_endpoint():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"created": True, "post_url": f"{SITE}/p/1"})

    with make(handler) as c:
        assert wp_http.publish(c, SITE + "/", {"a": 1}) == {"created": True, "post_url": f"{SITE}/p/1"}
    assert str(seen[0].url) == SITE + "/wp-json/ta-publisher/v1/publish"
    assert json.loads(seen[0].content) == {"a": 1}


def test_publish_409_is_a_result():
    with make(lambda r: httpx.Response(409, json={"created": False, "page_url": "x"})) as c:
        assert wp_http.publish(c, SITE, {}) == {"created": False, "page_url": "x"}
    with make(lambda r: httpx.Response(409, text="<html>")) as c:
        assert wp_http.publish(c, SITE, {}) == {"created": False}


def test_plugin_error_key_is_the_message():
    with make(lambda r: httpx.Response(500, json={"error": "Failed to create page"})) as c:
        with pytest.raises(WPPublishError) as e:
            wp_http.publish(c, SITE, {})
    assert e.value.message == "Failed to create page" and e.value.status_code == 500


def test_non_json_success_is_an_error():
    with make(lambda r: httpx.Response(200, text="<html>maintenance</html>")) as c:
        with pytest.raises(WPPublishError, match="non-JSON"):
            wp_http.publish(c, SITE, {})


def test_redirects_are_not_followed():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    with make(handler) as c:
        with pytest.raises(WPPublishError, match="127.0.0.1/admin"):
            wp_http.publish(c, SITE, {})
    assert len(calls) == 1


def test_connection_error_names_the_url_but_not_the_key():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with make(handler) as c:
        with pytest.raises(WPPublishError) as e:
            wp_http.check_status(c, SITE, "sekret-key", "slug", 3)
    assert SITE in e.value.message and "sekret-key" not in e.value.message
    assert e.value.status_code is None


def test_check_status_sends_key_slug_and_chapter_to_the_site_root():
    seen = []

    def handler(request):
        seen.append(request.url)
        return httpx.Response(200, json={"status": "publish", "post_url": "u"})

    with make(handler) as c:
        out = wp_http.check_status(c, SITE + "/wp-json/ta-publisher/v1/publish", "k", "s", 2)
    assert out == {"status": "publish", "post_url": "u"}
    assert seen[0].path == "/wp-json/ta-publisher/v1/status"
    assert dict(seen[0].params) == {"api_key": "k", "series_slug": "s", "chapter": "2"}


def test_check_status_401():
    with make(lambda r: httpx.Response(401, json={"error": "Invalid API key"})) as c:
        with pytest.raises(WPPublishError) as e:
            wp_http.check_status(c, SITE, "k", "s", 1)
    assert (e.value.message, e.value.status_code) == ("Invalid API key", 401)


def test_publish_illustrations_posts_to_the_illustrations_route():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"created": True, "page_url": "g"})

    with make(handler) as c:
        assert wp_http.publish_illustrations(c, SITE + "/wp-json/ta-publisher/v1/publish", {})["page_url"] == "g"
    assert seen == ["/wp-json/ta-publisher/v1/illustrations"]


def test_a_json_list_body_is_an_error_not_a_crash():
    with make(lambda r: httpx.Response(200, json=[1, 2])) as c:
        with pytest.raises(WPPublishError):
            wp_http.publish(c, SITE, {})
```

- [ ] **Step 3: Write the failing image tests** in `tests/test_core_images.py`:

```python
import io
import os

from PIL import Image

from api.core.images import shrink_image


def encode(img, fmt):
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def test_small_images_are_returned_as_is():
    data = encode(Image.new("RGB", (10, 10)), "PNG")
    assert shrink_image(data) is data


def test_undecodable_data_is_returned_as_is():
    data = b"not an image" * 40_000
    assert shrink_image(data) is data


def test_a_big_image_becomes_a_smaller_jpeg_within_1600px():
    noise = Image.frombytes("RGB", (2400, 1800), os.urandom(2400 * 1800 * 3))
    data = encode(noise, "PNG")
    out = shrink_image(data)
    assert out[:2] == b"\xff\xd8" and len(out) < len(data)
    assert max(Image.open(io.BytesIO(out)).size) <= 1600


def test_alpha_png_converts_to_jpeg():
    rgba = Image.frombytes("RGBA", (1200, 1200), os.urandom(1200 * 1200 * 4))
    out = shrink_image(encode(rgba, "PNG"))
    assert Image.open(io.BytesIO(out)).mode == "RGB"


def test_a_decompression_bomb_is_returned_as_is(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)  # anything over 2000 px raises
    data = encode(Image.frombytes("RGB", (800, 800), os.urandom(800 * 800 * 3)), "PNG")
    assert shrink_image(data) is data
```

- [ ] **Step 4: Run them to verify they fail**
  - Run: `pytest tests/test_core_wp_http.py tests/test_core_images.py -q`
  - Expected: FAIL with `ModuleNotFoundError` for `api.core.wp_http` and `api.core.images`.

- [ ] **Step 5: Write `api/core/wp_http.py`**

```python
"""WordPress HTTP calls, from the desktop translation_assistant/wp_publisher.py
(check_status, publish, publish_illustrations), over an injected httpx.Client instead
of urllib so tests use MockTransport (spec §12)."""

import httpx

from api.core.wp import WPPublishError, normalize_endpoint_url, site_base

STATUS_PATH = "/wp-json/ta-publisher/v1/status"
ILLUSTRATIONS_PATH = "/wp-json/ta-publisher/v1/illustrations"


def client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    # No redirects: every hop would need the SSRF check again, and the body carries the
    # API key. The error names the Location so the user can save that address instead.
    return httpx.Client(transport=transport, follow_redirects=False, timeout=15)


def _message(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and (body.get("error") or body.get("message")):
        return str(body.get("error") or body.get("message"))
    return f"HTTP {r.status_code} {r.reason_phrase}"


def _send(c: httpx.Client, method: str, url: str, *, timeout: float,
          ok_409: bool = False, **kwargs) -> dict:
    """``url`` carries no query string, so it is safe to show (the status key is in params)."""
    try:
        r = c.request(method, url, timeout=timeout, **kwargs)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise WPPublishError(f"Could not reach {url}: {type(exc).__name__}") from exc
    if r.is_redirect:
        raise WPPublishError(
            f"{url} redirected to {r.headers.get('location', '?')}; save that address instead",
            r.status_code,
        )
    if ok_409 and r.status_code == 409:  # the desktop read a 409 as "already there"
        try:
            body = r.json()
        except ValueError:
            body = None
        return body if isinstance(body, dict) else {"created": False}
    if r.is_error:
        raise WPPublishError(_message(r), r.status_code)
    try:
        body = r.json()
    except ValueError:
        raise WPPublishError(f"Server returned non-JSON response: {r.content[:200]!r}") from None
    if not isinstance(body, dict):
        raise WPPublishError("Server returned an unexpected response")
    return body


def check_status(c: httpx.Client, endpoint_url: str, api_key: str, series_slug: str,
                 chapter: int) -> dict:
    params = {"api_key": api_key, "series_slug": series_slug, "chapter": chapter}
    return _send(c, "GET", site_base(endpoint_url) + STATUS_PATH, params=params, timeout=10)


def publish(c: httpx.Client, endpoint_url: str, payload: dict) -> dict:
    return _send(c, "POST", normalize_endpoint_url(endpoint_url), json=payload,
                 timeout=15, ok_409=True)


def publish_illustrations(c: httpx.Client, endpoint_url: str, payload: dict) -> dict:
    return _send(c, "POST", site_base(endpoint_url) + ILLUSTRATIONS_PATH, json=payload,
                 timeout=60)
```

  - The connection message uses `type(exc).__name__`, not `str(exc)`: httpx messages can include the request URL, and the status URL's query holds the key.

- [ ] **Step 6: Write `api/core/images.py`**

```python
"""Shrink oversized images before they go into a WordPress publish payload, from the
desktop translation_assistant/imageopt.py (Pillow instead of Qt).

EasyWP's proxy resets any request whose body exceeds ~1 MB, and EPUB covers / colour
plates are 500-750 KB JPEGs that base64-inflate past that on their own."""

import io

from PIL import Image

_QUALITY_STEPS = (82, 70, 60, 50, 40)


def shrink_image(data: bytes, max_dim: int = 1600, target_bytes: int = 350_000) -> bytes:
    """A smaller JPEG rendering of ``data``.

    Returns ``data`` unchanged (same object) when it is already under ``target_bytes``,
    cannot be decoded (decompression bombs included), or no re-encoding beats the original.
    """
    if len(data) <= target_bytes:
        return data
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)  # keeps aspect, never enlarges
            img = im.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        return data
    out = b""
    for quality in _QUALITY_STEPS:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        out = buf.getvalue()
        if len(out) <= target_bytes:
            return out
    return out if out and len(out) < len(data) else data
```

  - `UnidentifiedImageError` is an `OSError`; a truncated file raises `OSError` from `thumbnail()`; the bomb check raises in `open()`.

- [ ] **Step 7: Run the tests to verify they pass**
  - Run: `pytest tests/test_core_wp_http.py tests/test_core_images.py -q && ruff check .`
  - Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml api/core/wp_http.py api/core/images.py tests/test_core_wp_http.py tests/test_core_images.py
git commit -m "feat(api): WordPress HTTP client and Pillow image downscaling"
```

---

### Task 3: WordPress settings and connection test

**Files:**
- Create: `api/wp_prefs.py`, `api/publish.py` (config part), `api/schemas/wp.py`, `api/routers/wp.py`, `tests/test_wp_settings.py`
- Modify: `api/config.py`, `api/deps.py`, `api/main.py`, `api/schemas/documents.py`, `.env.example`, `tests/test_config.py`

**Interfaces:**
- Consumes: `wp_http.client`, `wp_http.check_status`, `WPPublishError`; `check_user_url` (`api/mt/urls.py`); `decrypt_secret` (`api/security.py`).
- Produces:
  - `Settings.wp_allow_private_urls: bool = False` (`TA_WP_ALLOW_PRIVATE_URLS`)
  - `wp_prefs.KEYS: tuple[str, ...]`, `@dataclass(frozen=True) WpPrefs` with fields `wp_password_enabled: bool`, `wp_unlock_after: int`, `wp_attribution_enabled: bool`, `wp_default_schedule_time: str`, `wp_chapters_per_day: int`, `wp_schedule_scope_global: bool`; `wp_prefs.parse(stored: dict) -> WpPrefs`; `wp_prefs.load(db, user_id) -> WpPrefs`
  - `publish.NotReady(Exception)` (message says what to fix and where), `publish.wp_config(db, user_id) -> tuple[str, str]` (endpoint, key)
  - `deps.parse_zone(name: str) -> ZoneInfo` (422 on anything unknown) and `deps.zone(tz: str = Query("UTC", max_length=64)) -> ZoneInfo` (a dependency)
  - `routers/wp.py`: `router`, `http_client` (the seam tests replace), `GET /wp/prefs -> WpPrefsOut`, `POST /wp/test -> WpTestOut`
  - `DocumentOut` gains `wp_published_at: datetime | None` and `wp_scheduled_for: datetime | None`

- [ ] **Step 1: Write the failing tests** in `tests/test_wp_settings.py`:

```python
import httpx
import pytest

from api import wp_prefs
from api.routers import wp as wp_router

SITE = "https://blog.example.com"


@pytest.fixture
def wp_site(monkeypatch):
    """A fake WordPress: `answers[path]` is (status, json); every request is recorded."""
    answers = {"/wp-json/ta-publisher/v1/status": (200, {"status": "not_found", "post_url": None})}
    calls = []

    def handle(request):
        calls.append(request)
        status, body = answers.get(request.url.path, (404, {"error": "no route"}))
        return httpx.Response(status, json=body)

    monkeypatch.setattr(wp_router, "http_client",
                        lambda: wp_router.wp_http.client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr("api.publish.check_user_url", lambda url, allow, label: None)
    return answers, calls


def save_wp(app_client, url=SITE, key="plugin-key-1234"):
    r = app_client.post("/credentials", json={"kind": "wordpress", "secret": key, "endpoint_url": url})
    assert r.status_code == 201


def test_prefs_have_the_desktop_defaults(app_client, me):
    assert app_client.get("/wp/prefs").json() == {
        "wp_password_enabled": False, "wp_unlock_after": 3, "wp_attribution_enabled": True,
        "wp_default_schedule_time": "", "wp_chapters_per_day": 1, "wp_schedule_scope_global": False,
    }


def test_saved_prefs_are_read_and_bad_shapes_fall_back(app_client, me):
    app_client.put("/settings", json={
        "wp_password_enabled": True, "wp_unlock_after": 0, "wp_default_schedule_time": "20:30",
        "wp_chapters_per_day": "2", "wp_schedule_scope_global": True,
    })
    p = app_client.get("/wp/prefs").json()
    assert p["wp_password_enabled"] is True and p["wp_schedule_scope_global"] is True
    assert p["wp_default_schedule_time"] == "20:30"
    assert p["wp_unlock_after"] == 3 and p["wp_chapters_per_day"] == 1  # out of range / wrong type


@pytest.mark.parametrize("value", ["24:00", "8:00", "20:30:00", 2030])
def test_bad_schedule_times_read_as_unset(value):
    assert wp_prefs.parse({"wp_default_schedule_time": value}).wp_default_schedule_time == ""


def test_connection_test_needs_a_credential(app_client, me, wp_site):
    r = app_client.post("/wp/test")
    assert r.status_code == 422 and "Settings → WordPress" in r.json()["detail"]


def test_connection_test_ok(app_client, me, wp_site):
    _, calls = wp_site
    save_wp(app_client)
    assert app_client.post("/wp/test").json()["ok"] is True
    assert calls[0].url.params["api_key"] == "plugin-key-1234"


def test_connection_test_reports_a_rejected_key(app_client, me, wp_site):
    answers, _ = wp_site
    answers["/wp-json/ta-publisher/v1/status"] = (401, {"error": "Invalid API key"})
    save_wp(app_client)
    body = app_client.post("/wp/test").json()
    assert body["ok"] is False and "rejected the API key" in body["message"]


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.5/", "http://169.254.169.254/",
                                 "ftp://example.com/"])
def test_private_and_non_http_endpoints_are_refused_before_any_request(app_client, me, monkeypatch, url):
    calls = []
    monkeypatch.setattr(wp_router, "http_client", lambda: wp_router.wp_http.client(
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={}))))
    save_wp(app_client, url=url)
    r = app_client.post("/wp/test")
    assert r.status_code == 422 and calls == []


def test_private_endpoints_are_allowed_with_the_flag(app_client, me, monkeypatch):
    from api.config import get_settings
    monkeypatch.setattr(get_settings(), "wp_allow_private_urls", True)
    monkeypatch.setattr(wp_router, "http_client", lambda: wp_router.wp_http.client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"status": "not_found"}))))
    save_wp(app_client, url="http://127.0.0.1:8080/")
    assert app_client.post("/wp/test").json()["ok"] is True


def test_document_out_carries_the_wp_dates(app_client, me, make_doc):
    doc = make_doc(me, ["x"])
    body = app_client.get(f"/documents/{doc.id}").json()
    assert body["wp_published_at"] is None and body["wp_scheduled_for"] is None
```

  - In `tests/test_config.py` add:

```python
def test_wp_private_urls_default_off(monkeypatch):
    from api.config import Settings
    monkeypatch.setenv("TA_SECRET_KEY", "x" * 32)
    assert Settings().wp_allow_private_urls is False
```

- [ ] **Step 2: Run them to verify they fail**
  - Run: `pytest tests/test_wp_settings.py tests/test_config.py -q`
  - Expected: FAIL (`ImportError: cannot import name 'wp_prefs'`, missing setting).

- [ ] **Step 3: Config and time zones**
  - In `api/config.py`, after `mt_allow_private_urls`:

```python
    # The same guard for the user's WordPress endpoint. Separate on purpose: allowing a
    # private Ollama must not also allow a private WordPress.
    wp_allow_private_urls: bool = False
```

  - In `.env.example`, after `TA_MT_ALLOW_PRIVATE_URLS=false`, add `TA_WP_ALLOW_PRIVATE_URLS=false`.
  - Append to `api/deps.py` (add `from zoneinfo import ZoneInfo, ZoneInfoNotFoundError` and `Query` to the fastapi import):

```python
def parse_zone(name: str) -> ZoneInfo:
    """An IANA zone name from the browser (Intl...timeZone); 422 for anything else,
    including path tricks such as "../../etc/passwd", which ZoneInfo rejects."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"tz: unknown time zone {name[:64]!r}"
        ) from exc


def zone(tz: str = Query("UTC", max_length=64)) -> ZoneInfo:
    return parse_zone(tz)
```

- [ ] **Step 4: Preferences** — write `api/wp_prefs.py`:

```python
"""Per-user WordPress preferences: the desktop's WP* QSettings (dlg_wp_settings.py) as
user_settings keys, with the desktop defaults. A value of the wrong shape reads as its
default, so a bad PUT /settings can never break a publish."""

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import UserSetting

KEYS = ("wp_password_enabled", "wp_unlock_after", "wp_attribution_enabled",
        "wp_default_schedule_time", "wp_chapters_per_day", "wp_schedule_scope_global")
_TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


@dataclass(frozen=True)
class WpPrefs:
    wp_password_enabled: bool
    wp_unlock_after: int
    wp_attribution_enabled: bool
    wp_default_schedule_time: str  # "HH:MM", or "" for none
    wp_chapters_per_day: int
    wp_schedule_scope_global: bool


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _int(value: Any, default: int) -> int:
    ok = isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 99
    return value if ok else default  # the desktop spin boxes' range


def parse(stored: dict[str, Any]) -> WpPrefs:
    t = stored.get("wp_default_schedule_time")
    return WpPrefs(
        wp_password_enabled=_bool(stored.get("wp_password_enabled"), False),
        wp_unlock_after=_int(stored.get("wp_unlock_after"), 3),
        wp_attribution_enabled=_bool(stored.get("wp_attribution_enabled"), True),
        wp_default_schedule_time=t if isinstance(t, str) and _TIME.fullmatch(t) else "",
        wp_chapters_per_day=_int(stored.get("wp_chapters_per_day"), 1),
        wp_schedule_scope_global=_bool(stored.get("wp_schedule_scope_global"), False),
    )


def load(db: Session, user_id: int) -> WpPrefs:
    rows = db.scalars(select(UserSetting).where(
        UserSetting.user_id == user_id, UserSetting.key.in_(KEYS)))
    return parse({r.key: r.value_json for r in rows})
```

- [ ] **Step 5: The config half of `api/publish.py`** (Task 4 appends the rest):

```python
"""WordPress publish machinery, from the desktop ui/wp_publish_flow.py without Qt: the
user's WordPress config, the chapter build, the result write-back and the schedule
helpers. Used by api/routers/wp.py and api/publish_job.py."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.models import ApiCredential
from api.mt.urls import check_user_url
from api.security import decrypt_secret

WHERE = "under Settings → WordPress"


class NotReady(Exception):
    """Something the user must fix first; the message says what and where."""


def wp_config(db: Session, user_id: int) -> tuple[str, str]:
    """(endpoint_url, api_key) of the user's WordPress credential, SSRF-checked (ruling 5).
    Blocking: it resolves DNS."""
    row = db.scalar(select(ApiCredential).where(
        ApiCredential.user_id == user_id, ApiCredential.kind == "wordpress",
        ApiCredential.name == ""))
    if row is None or not row.endpoint_url:
        raise NotReady(f"Set your WordPress endpoint and API key {WHERE}.")
    try:
        key = decrypt_secret(row.secret_enc)
    except ValueError:
        raise NotReady(f"Your saved WordPress API key cannot be read; enter it again {WHERE}.") from None
    problem = check_user_url(row.endpoint_url, get_settings().wp_allow_private_urls, "WordPress")
    if problem:
        raise NotReady(problem)
    return row.endpoint_url, key
```

- [ ] **Step 6: Schemas** — write `api/schemas/wp.py` (Tasks 4 and 6 append to it):

```python
from pydantic import BaseModel


class WpPrefsOut(BaseModel):
    wp_password_enabled: bool
    wp_unlock_after: int
    wp_attribution_enabled: bool
    wp_default_schedule_time: str
    wp_chapters_per_day: int
    wp_schedule_scope_global: bool


class WpTestOut(BaseModel):
    ok: bool
    message: str
```

  - In `api/schemas/documents.py` `DocumentOut`, after `wp_post_url: str`, add `wp_published_at: datetime | None` and `wp_scheduled_for: datetime | None`.

- [ ] **Step 7: The router** — write `api/routers/wp.py`:

```python
"""WordPress (spec §10): preferences, connection test, status refresh, one-chapter
publish, and the batch publish and volume illustrations jobs (api/publish_job.py)."""

from dataclasses import asdict

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from api import publish, wp_prefs
from api.core import wp_http
from api.core.wp import WPPublishError
from api.deps import current_user, db_session
from api.models import User
from api.routing import api_router
from api.schemas.wp import WpPrefsOut, WpTestOut

router = api_router(tags=["wp"])

http_client = wp_http.client  # the seam tests replace
PROBE_SLUG = "ta-web-connection-test"


def _ready(fn, *args):
    """Run a publish step; NotReady is the user's to fix, so a 422 with its message."""
    try:
        return fn(*args)
    except publish.NotReady as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/wp/prefs", response_model=WpPrefsOut)
def get_prefs(user: User = Depends(current_user), db: Session = Depends(db_session)) -> WpPrefsOut:
    return WpPrefsOut(**asdict(wp_prefs.load(db, user.id)))


@router.post("/wp/test", response_model=WpTestOut)
def test_connection(user: User = Depends(current_user), db: Session = Depends(db_session)) -> WpTestOut:
    """Ruling 13: ask /status with the saved key; not_found for the probe slug is success."""
    endpoint, key = _ready(publish.wp_config, db, user.id)
    try:
        with http_client() as c:
            wp_http.check_status(c, endpoint, key, PROBE_SLUG, 1)
    except WPPublishError as exc:
        if exc.status_code == 401:
            return WpTestOut(ok=False, message="WordPress answered, but rejected the API key.")
        return WpTestOut(ok=False, message=exc.message)
    return WpTestOut(ok=True, message="Connected; WordPress accepted the API key.")
```

  - In `api/main.py`, import `wp` with the other routers and add `app.include_router(wp.router)` after `app.include_router(epub.router)`.

- [ ] **Step 8: Run the tests to verify they pass**
  - Run: `pytest tests/test_wp_settings.py tests/test_config.py tests/test_commit_boundary.py -q && ruff check .`
  - Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add api/config.py api/deps.py api/main.py api/wp_prefs.py api/publish.py api/schemas/wp.py api/schemas/documents.py api/routers/wp.py .env.example tests/test_wp_settings.py tests/test_config.py
git commit -m "feat(api): WordPress settings, SSRF-checked config and connection test"
```

---

### Task 4: Publish one chapter

**Files:**
- Modify: `api/publish.py` (append), `api/schemas/wp.py` (append), `api/routers/wp.py` (append)
- Create: `tests/test_wp_publish.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces (in `api/publish.py`):
  - `LIVE = ("publish", "future")`, `wp_date(dt: datetime) -> str` (UTC `%Y-%m-%dT%H:%M:%SZ`)
  - `check_series(series: Series) -> None` (raises `NotReady`), `series_meta(series) -> dict`
  - `@dataclass(frozen=True) Chapter` (the desktop `PublishJob`): `doc_meta`, `series_meta`, `lines`, `inline_images`, `cover_image`, `password`, `unlock_chapter_index`, `prev_wp_chapter_index`
  - `build_chapter(db, doc: Document, prefs: WpPrefs) -> Chapter` (raises `NotReady`)
  - `payload(ch: Chapter, api_key: str, *, scheduled: datetime | None, attribution: bool) -> dict`
  - `record(doc, result: dict, scheduled: datetime | None) -> bool`
  - `apply_remote_status(doc, result: dict) -> None`
  - `wp_dates(db, user_id, series_id: int | None) -> list[str]`
  - `suggested_slot(db, doc, prefs, tz) -> tuple[bool, datetime | None]`
  - `batch_slots(start: datetime, n: int, per_day: int, default_time: str, tz) -> list[datetime]`
  - `image_dict(im: DocumentImage) -> dict` (shrunk)
- Produces (routes): `POST /documents/{id}/wp/status?tz=` → `WpStatusOut`; `POST /documents/{id}/wp/publish` (`PublishIn`) → `PublishOut`.

- [ ] **Step 1: Write the failing tests** in `tests/test_wp_publish.py`:

```python
import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from api import publish
from api.models import DocumentImage
from api.routers import wp as wp_router

SITE = "https://blog.example.com"
STATUS = "/wp-json/ta-publisher/v1/status"
PUBLISH = "/wp-json/ta-publisher/v1/publish"


@pytest.fixture
def wp_site(monkeypatch):
    answers = {STATUS: (200, {"status": "not_found", "post_url": None}),
               PUBLISH: (200, {"created": True, "updated": False, "page_url": f"{SITE}/s/s-c1/",
                               "post_url": f"{SITE}/2026/s-c1/"})}
    posted = []

    def handle(request):
        if request.method == "POST":
            posted.append(json.loads(request.content))
        code, body = answers[request.url.path]
        return httpx.Response(code, json=body)

    monkeypatch.setattr(wp_router, "http_client",
                        lambda: wp_router.wp_http.client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr("api.publish.check_user_url", lambda url, allow, label: None)
    return answers, posted


@pytest.fixture
def ready(app_client, me, make_series, db):
    """WordPress configured, and a series with its WordPress fields."""
    app_client.post("/credentials", json={"kind": "wordpress", "secret": "k" * 12, "endpoint_url": SITE})
    s = make_series(me, "Sword")
    s.wp_series_slug, s.wp_series_title_short = "sword", "SotW"
    db.flush()
    return s


def test_publish_sends_the_desktop_payload_and_records_the_result(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    doc = make_doc(me, ["一", "二"], series=ready, order=1, title="The Beginning")
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert r.status_code == 200
    assert r.json()["created"] is True and r.json()["password"] is None
    p = posted[0]
    assert (p["api_key"], p["series_slug"], p["chapter_index"]) == ("k" * 12, "sword", 1)
    assert p["chapter_title"] == "SotW The Beginning"
    assert p["chapter_body"].startswith("<p>tr:一</p>\n<p>tr:二</p>")
    assert "automatically published" in p["chapter_body"] and p["first_line"] == "tr:一"
    db.refresh(doc)
    assert (doc.wp_status, doc.wp_post_url, doc.wp_chapter_index) == ("publish", f"{SITE}/2026/s-c1/", 1)
    assert doc.wp_published_at is not None and doc.wp_scheduled_for is None


def test_scheduled_publish_sends_utc_and_records_future(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    doc = make_doc(me, ["一"], series=ready, order=1)
    r = app_client.post(f"/documents/{doc.id}/wp/publish",
                        json={"scheduled_for": "2026-11-01T20:00:00+09:00"})
    assert r.status_code == 200
    assert posted[0]["publish_date"] == "2026-11-01T11:00:00Z"
    db.refresh(doc)
    assert doc.wp_status == "future"
    assert doc.wp_scheduled_for == doc.wp_published_at == datetime(2026, 11, 1, 11, tzinfo=UTC)


def test_naive_schedule_is_422(app_client, me, ready, make_doc, wp_site):
    doc = make_doc(me, ["一"], series=ready, order=1)
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={"scheduled_for": "2026-11-01T20:00:00"})
    assert r.status_code == 422


def test_republish_needs_confirmation_cached(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    doc = make_doc(me, ["一"], series=ready, order=1)
    doc.wp_status = "publish"
    db.flush()
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 409
    assert posted == []
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={"confirm_republish": True})
    assert r.status_code == 200 and len(posted) == 1


def test_republish_needs_confirmation_when_only_wordpress_knows(app_client, me, ready, make_doc, wp_site):
    answers, posted = wp_site
    answers[STATUS] = (200, {"status": "future", "post_url": "u"})
    doc = make_doc(me, ["一"], series=ready, order=1)
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 409
    assert posted == []


def test_unreachable_status_falls_back_to_cache_and_a_failed_publish_writes_nothing(
        app_client, me, ready, make_doc, wp_site, db):
    answers, _ = wp_site
    answers[STATUS] = (500, {"error": "down"})
    answers[PUBLISH] = (500, {"error": "Failed to create page"})
    doc = make_doc(me, ["一"], series=ready, order=1)
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert r.status_code == 502 and r.json()["detail"] == "Failed to create page"
    db.refresh(doc)
    assert doc.wp_status == "" and doc.wp_published_at is None


def test_password_protection_follows_series_then_user(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    app_client.put("/settings", json={"wp_password_enabled": True, "wp_unlock_after": 1})
    doc = make_doc(me, ["一"], series=ready, order=3)
    body = app_client.post(f"/documents/{doc.id}/wp/publish", json={}).json()
    assert len(body["password"]) == 12 and body["unlock_chapter_index"] == 2
    assert posted[0]["password"] == body["password"]
    ready.wp_password_enabled = False  # the series override wins
    db.flush()
    other = make_doc(me, ["二"], series=ready, order=4)
    assert app_client.post(f"/documents/{other.id}/wp/publish", json={}).json()["password"] is None


def test_unpublishable_chapters_are_422(app_client, me, ready, make_doc, wp_site, db):
    blank = make_doc(me, ["一"], series=ready, order=1, translated=False)
    assert "No translated lines" in app_client.post(f"/documents/{blank.id}/wp/publish", json={}).json()["detail"]
    loose = make_doc(me, ["一"])
    assert app_client.post(f"/documents/{loose.id}/wp/publish", json={}).status_code == 422
    ready.wp_series_slug = ""
    db.flush()
    doc = make_doc(me, ["一"], series=ready, order=2)
    r = app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert r.status_code == 422 and "slug" in r.json()["detail"]


def test_inline_images_and_cover_ride_along(app_client, me, ready, make_doc, wp_site, db):
    _, posted = wp_site
    doc = make_doc(me, ["一", "二"], series=ready, order=1)
    db.add_all([
        DocumentImage(document_id=doc.id, anchor_position=1, src_path="i/a.png", data=b"A"),
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="i/c.jpg", data=b"C", is_cover=True),
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="i/x.png", data=b"X", exclude_export=True),
    ])
    db.flush()
    app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    p = posted[0]
    assert [(i["position"], i["filename"]) for i in p["images"]] == [(1, "a.png")]
    assert p["cover"]["filename"] == "c.jpg"


def test_status_refresh_writes_status_but_not_dates(app_client, me, ready, make_doc, wp_site, db):
    answers, _ = wp_site
    answers[STATUS] = (200, {"status": "publish", "post_url": "u2"})
    doc = make_doc(me, ["一"], series=ready, order=1)
    doc.wp_status, doc.wp_published_at = "future", datetime(2026, 1, 1, tzinfo=UTC)
    db.flush()
    body = app_client.post(f"/documents/{doc.id}/wp/status").json()
    assert (body["cached_status"], body["status"], body["post_url"]) == ("future", "publish", "u2")
    db.refresh(doc)
    assert doc.wp_published_at == datetime(2026, 1, 1, tzinfo=UTC)
    answers[STATUS] = (200, {"status": "not_found", "post_url": None})
    assert app_client.post(f"/documents/{doc.id}/wp/status").json()["status"] == ""


def test_status_refresh_survives_an_unreachable_site(app_client, me, ready, make_doc, wp_site):
    answers, _ = wp_site
    answers[STATUS] = (503, {"error": "maintenance"})
    doc = make_doc(me, ["一"], series=ready, order=1)
    body = app_client.post(f"/documents/{doc.id}/wp/status").json()
    assert body["remote_error"] == "maintenance" and body["status"] == ""


def test_status_suggests_the_auto_slot_after_a_scheduled_previous_chapter(
        app_client, me, ready, make_doc, wp_site, db):
    app_client.put("/settings", json={"wp_chapters_per_day": 1, "wp_default_schedule_time": "20:00"})
    prev = make_doc(me, ["一"], series=ready, order=1)
    prev.wp_status = "future"
    prev.wp_published_at = datetime(2026, 11, 1, 11, tzinfo=UTC)  # 20:00 in Tokyo
    doc = make_doc(me, ["二"], series=ready, order=2)
    db.flush()
    body = app_client.post(f"/documents/{doc.id}/wp/status", params={"tz": "Asia/Tokyo"}).json()
    assert body["previous_scheduled"] is True
    assert datetime.fromisoformat(body["suggested_slot"]) == datetime(2026, 11, 2, 20, tzinfo=ZoneInfo("Asia/Tokyo"))


@pytest.mark.parametrize("tz", ["Mars/Base", "../../etc/passwd", "x" * 65])
def test_bad_time_zones_are_422(app_client, me, ready, make_doc, wp_site, tz):
    doc = make_doc(me, ["一"], series=ready, order=1)
    assert app_client.post(f"/documents/{doc.id}/wp/status", params={"tz": tz}).status_code == 422


def test_another_users_chapter_is_404(app_client, ready, make_user, make_doc, wp_site):
    theirs = make_doc(make_user(email="o@example.com"), ["一"])
    assert app_client.post(f"/documents/{theirs.id}/wp/publish", json={}).status_code == 404
    assert app_client.post(f"/documents/{theirs.id}/wp/status").status_code == 404


def test_batch_slots_fill_each_day_then_roll_over():
    tokyo = ZoneInfo("Asia/Tokyo")
    start = datetime(2026, 7, 20, 20, tzinfo=tokyo)
    slots = publish.batch_slots(start, 4, 2, "20:00", tokyo)
    assert [s.strftime("%d %H:%M") for s in slots] == ["20 20:00", "20 21:00", "21 20:00", "21 21:00"]
```

- [ ] **Step 2: Run them to verify they fail**
  - Run: `pytest tests/test_wp_publish.py -q`
  - Expected: FAIL (404 for the new routes, `AttributeError: batch_slots`).

- [ ] **Step 3: Append to `api/publish.py`**
  - Extend the imports: `from dataclasses import dataclass`, `from datetime import UTC, datetime, tzinfo`, `from api.core import wp`, `from api.core.images import shrink_image`, `from api.models import ApiCredential, Document, DocumentImage, Line, Series, Volume`, `from api.wp_prefs import WpPrefs`.

```python
LIVE = ("publish", "future")
_WP_DATE = "%Y-%m-%dT%H:%M:%SZ"


def wp_date(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime(_WP_DATE)


def check_series(series: Series) -> None:
    """The desktop ensure_series_wp_meta, as a refusal instead of a dialog."""
    if not (series.wp_series_slug and series.wp_series_title_short):
        raise NotReady(f'Set the WordPress slug and short title of "{series.title}" on its series page.')


def series_meta(series: Series) -> dict:
    return {"series_slug": series.wp_series_slug,
            "series_title_short": series.wp_series_title_short,
            "syosetu_url": series.syosetu_url}


def image_dict(im: DocumentImage) -> dict:
    """The desktop's in-place shrink: downscaled bytes get a .jpg name."""
    data = shrink_image(im.data)
    src = im.src_path if data is im.data else im.src_path.rsplit(".", 1)[0] + ".jpg"
    return {"id": im.id, "anchor_position": im.anchor_position, "src_path": src, "data": data}


@dataclass(frozen=True)
class Chapter:
    """The desktop PublishJob (renamed: a "job" is a jobs-table row here)."""

    doc_meta: dict
    series_meta: dict
    lines: list[dict]
    inline_images: list[dict]
    cover_image: dict | None
    password: str | None
    unlock_chapter_index: int | None
    prev_wp_chapter_index: int | None


def build_chapter(db: Session, doc: Document, prefs: WpPrefs) -> Chapter:
    """The desktop build_job."""
    series = doc.series
    if series is None:
        raise NotReady("Only a chapter in a series can be published.")
    check_series(series)
    password = unlock = None
    if wp.resolve_wp_password_enabled(series.wp_password_enabled, prefs.wp_password_enabled):
        unlock_after = (series.wp_unlock_after if series.wp_unlock_after is not None
                        else prefs.wp_unlock_after)
        password, unlock = wp.compute_password_fields(doc.series_order, unlock_after)
    lines = [{"prefix": p, "translated_text": t} for p, t in db.execute(
        select(Line.prefix, Line.translated_text)
        .where(Line.document_id == doc.id).order_by(Line.line_number))]
    if not any(ln["translated_text"].strip() for ln in lines):
        raise NotReady("No translated lines to publish.")
    images = db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc.id)
                        .order_by(DocumentImage.anchor_position, DocumentImage.id)).all()
    inline = [image_dict(im) for im in images if not im.is_cover and not im.exclude_export]
    cover = next((im for im in images if im.is_cover), None)
    volume = db.get(Volume, doc.volume_id) if doc.volume_id else None
    return Chapter(
        doc_meta={"series_title": series.title, "series_order": doc.series_order,
                  "chapter_title": doc.chapter_title or doc.title,  # ruling 11
                  "volume_title": volume.title if volume else ""},
        series_meta=series_meta(series), lines=lines, inline_images=inline,
        # build_payload sends the cover with chapter 1 only, so only that one is shrunk
        cover_image=image_dict(cover) if cover is not None and doc.series_order == 1 else None,
        password=password, unlock_chapter_index=unlock,
        prev_wp_chapter_index=doc.wp_chapter_index,
    )


def payload(ch: Chapter, api_key: str, *, scheduled: datetime | None, attribution: bool) -> dict:
    """The desktop job_to_payload."""
    return wp.build_payload(
        ch.doc_meta, ch.series_meta, ch.lines, api_key=api_key, password=ch.password,
        unlock_chapter_index=ch.unlock_chapter_index,
        scheduled_date=wp_date(scheduled) if scheduled else None, attribution=attribution,
        images=ch.inline_images, cover=ch.cover_image,
        previous_chapter_index=ch.prev_wp_chapter_index,
    )


def record(doc: Document, result: dict, scheduled: datetime | None) -> bool:
    """The desktop persist_publish_result (ruling 7). False when WordPress reported
    neither created nor updated (its 409 "already there")."""
    if not (result.get("created") or result.get("updated")):
        return False
    doc.wp_status = "future" if scheduled else "publish"
    doc.wp_post_url = str(result.get("post_url") or "")
    doc.wp_published_at = scheduled or datetime.now(UTC)
    doc.wp_scheduled_for = scheduled
    doc.wp_chapter_index = doc.series_order
    return True


def apply_remote_status(doc: Document, result: dict) -> None:
    """The desktop _on_status_ok without its date wipe (ruling 7)."""
    remote = result.get("status")
    if not isinstance(remote, str):
        return
    doc.wp_status = "" if remote == "not_found" else remote[:32]
    doc.wp_post_url = str(result.get("post_url") or "")


def wp_dates(db: Session, user_id: int, series_id: int | None) -> list[str]:
    """The desktop get_wp_dates: dates of published/scheduled chapters, one series or all."""
    q = select(Document.wp_published_at).where(
        Document.user_id == user_id, Document.wp_status.in_(LIVE),
        Document.wp_published_at.is_not(None))
    if series_id is not None:
        q = q.where(Document.series_id == series_id)
    return [wp_date(d) for d in db.scalars(q)]


def suggested_slot(db: Session, doc: Document, prefs: WpPrefs,
                   tz: tzinfo) -> tuple[bool, datetime | None]:
    """The confirm dialog's logic: (previous chapter still scheduled, the auto slot)."""
    if doc.series_id is None or doc.series_order <= 0:
        return False, None
    prev = db.scalar(select(Document).where(
        Document.user_id == doc.user_id, Document.series_id == doc.series_id,
        Document.series_order == doc.series_order - 1).order_by(Document.id).limit(1))
    if prev is None or prev.wp_status != "future":
        return False, None
    if prev.wp_published_at is None:
        return True, None
    scope = None if prefs.wp_schedule_scope_global else doc.series_id
    slot = wp.compute_auto_schedule(
        wp_date(prev.wp_published_at), wp_dates(db, doc.user_id, scope),
        prefs.wp_chapters_per_day, prefs.wp_default_schedule_time, tz=tz)
    return True, slot.replace(tzinfo=tz)


def batch_slots(start: datetime, n: int, per_day: int, default_time: str,
                tz: tzinfo) -> list[datetime]:
    """The desktop _on_publish_batch slot loop: the first at `start`, each next one
    after the previous by compute_auto_schedule over the slots assigned so far."""
    assigned: list[str] = []
    slots: list[datetime] = []
    for i in range(n):
        slot = start if i == 0 else wp.compute_auto_schedule(
            assigned[-1], assigned, per_day, default_time, tz=tz).replace(tzinfo=tz)
        assigned.append(wp_date(slot))
        slots.append(slot)
    return slots
```

- [ ] **Step 4: Append the schemas** to `api/schemas/wp.py` (add `from datetime import datetime` and `from pydantic import AwareDatetime`):

```python
class WpStatusOut(BaseModel):
    cached_status: str  # before the refresh
    status: str  # after it ("" = not on WordPress)
    post_url: str
    remote_error: str  # why WordPress could not be asked; "" when it answered
    previous_scheduled: bool
    suggested_slot: datetime | None


class PublishIn(BaseModel):
    scheduled_for: AwareDatetime | None = None
    confirm_republish: bool = False


class PublishOut(BaseModel):
    created: bool
    updated: bool
    page_url: str
    post_url: str
    password: str | None
    unlock_chapter_index: int | None
    scheduled_for: datetime | None
```

- [ ] **Step 5: Append the routes** to `api/routers/wp.py`
  - Extend the imports: `from zoneinfo import ZoneInfo`; `from api.deps import current_user, db_session, scoped, zone`; `from api.models import Document, Series, User`; `PublishIn, PublishOut, WpStatusOut` from `api.schemas.wp`.

```python
def _chapter_context(db: Session, document_id: int, user_id: int) -> tuple[Document, Series, str, str]:
    doc = scoped(db, Document, document_id, user_id)
    endpoint, key = _ready(publish.wp_config, db, user_id)
    if doc.series is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Only a chapter in a series can be published.")
    _ready(publish.check_series, doc.series)
    return doc, doc.series, endpoint, key


@router.post("/documents/{document_id}/wp/status", response_model=WpStatusOut)
def refresh_status(
    document_id: int, tz: ZoneInfo = Depends(zone),
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> WpStatusOut:
    """What the desktop confirm dialog showed: the cached and live status, and whether the
    previous chapter is still scheduled (with the auto slot after it)."""
    doc, series, endpoint, key = _chapter_context(db, document_id, user.id)
    cached, remote_error = doc.wp_status, ""
    try:
        with http_client() as c:
            publish.apply_remote_status(
                doc, wp_http.check_status(c, endpoint, key, series.wp_series_slug, doc.series_order))
    except WPPublishError as exc:
        remote_error = exc.message
    previous, slot = publish.suggested_slot(db, doc, wp_prefs.load(db, user.id), tz)
    db.flush()
    return WpStatusOut(cached_status=cached, status=doc.wp_status, post_url=doc.wp_post_url,
                       remote_error=remote_error, previous_scheduled=previous, suggested_slot=slot)


@router.post("/documents/{document_id}/wp/publish", response_model=PublishOut)
def publish_chapter(
    document_id: int, body: PublishIn,
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> PublishOut:
    """The desktop run_single_publish, with the re-publish safeguard enforced (ruling 6)."""
    doc, series, endpoint, key = _chapter_context(db, document_id, user.id)
    prefs = wp_prefs.load(db, user.id)
    ch = _ready(publish.build_chapter, db, doc, prefs)
    with http_client() as c:
        live = doc.wp_status in publish.LIVE
        try:
            remote = wp_http.check_status(c, endpoint, key, series.wp_series_slug, doc.series_order)
            live = live or remote.get("status") in publish.LIVE
        except WPPublishError:
            pass  # WordPress could not be asked: the cached status decides, as on the desktop
        if live and not body.confirm_republish:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f'"{doc.title}" is already published or scheduled on WordPress; '
                "publishing again overwrites it.")
        try:
            result = wp_http.publish(c, endpoint, publish.payload(
                ch, key, scheduled=body.scheduled_for, attribution=prefs.wp_attribution_enabled))
        except WPPublishError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    written = publish.record(doc, result, body.scheduled_for)
    db.flush()
    return PublishOut(
        created=bool(result.get("created")), updated=bool(result.get("updated")),
        page_url=str(result.get("page_url") or ""), post_url=str(result.get("post_url") or ""),
        password=ch.password if written else None,
        unlock_chapter_index=ch.unlock_chapter_index if written else None,
        scheduled_for=body.scheduled_for,
    )
```

- [ ] **Step 6: Run the tests to verify they pass**
  - Run: `pytest tests/test_wp_publish.py tests/test_wp_settings.py -q && ruff check . && wc -l api/publish.py api/routers/wp.py`
  - Expected: PASS; both modules under 400 lines.

- [ ] **Step 7: Commit**

```bash
git add api/publish.py api/schemas/wp.py api/routers/wp.py tests/test_wp_publish.py
git commit -m "feat(api): publish one chapter to WordPress with the re-publish safeguard"
```

---

### Task 5: Jobs hardening (phase 6a carry-over)

**Files:**
- Modify: `api/jobs.py` (`run_next`), `api/routers/jobs.py` (`_snapshot`, `job_events`)
- Test: `tests/test_jobs.py`, `tests/test_jobs_api.py`

**Interfaces:**
- Produces: `run_next()` returns `True` (no exception, no error log) when the job row is deleted while its handler runs; `_snapshot(job_id) -> dict | None`, and the SSE stream ends when it is `None`.

- [ ] **Step 1: Write the failing tests**
  - Append to `tests/test_jobs.py`:

```python
def test_a_job_deleted_while_running_ends_quietly(in_test_db, make_user, kind, caplog):
    from sqlalchemy import delete

    from api.models import Job
    user = make_user(email="j@example.com")

    def vanish(ctx):
        ctx.db.execute(delete(Job).where(Job.id == ctx.job.id))  # the user-delete cascade
        ctx.progress(1, 1)
        return {}

    kind("vanish", vanish)
    jobs.enqueue(in_test_db, user.id, "vanish", {})
    assert jobs.run_next() is True
    assert "failed" not in caplog.text
    assert jobs.run_next() is False
```

  - Append to `tests/test_jobs_api.py`:

```python
def test_events_end_when_the_job_row_disappears(app_client, db, me, same_db, monkeypatch):
    job = jobs.enqueue(db, me.id, "syosetu_fetch", {"series_id": 1})
    calls = {"n": 0}
    real = jobs_router._snapshot

    def snapshot(job_id):
        calls["n"] += 1
        return real(job_id) if calls["n"] == 1 else None

    monkeypatch.setattr(jobs_router, "_snapshot", snapshot)
    body = app_client.get(f"/jobs/{job.id}/events").text
    assert len(frames(body)) == 1
```

- [ ] **Step 2: Run them to verify they fail**
  - Run: `pytest tests/test_jobs.py tests/test_jobs_api.py -q`
  - Expected: the first FAILS with `StaleDataError` (or `ObjectDeletedError`) raised out of `run_next`; the second hangs on `None["state"]` → `TypeError`.

- [ ] **Step 3: Fix `run_next`** in `api/jobs.py`
  - Add `from sqlalchemy.orm.exc import ObjectDeletedError, StaleDataError`.
  - Replace the body of `run_next` with:

```python
def run_next() -> bool:
    """Run the oldest queued job to completion. False when there was none."""
    with SessionLocal() as db:
        job = _claim(db)
        if job is None:
            return False
        job_id, fn = job.id, HANDLERS.get(job.kind)
        try:
            if fn is None:
                raise JobError(f"unknown job kind {job.kind!r}")
            result = fn(JobContext(db, job))
            job.state, job.result_json = "done", result or {}
        except (StaleDataError, ObjectDeletedError):
            db.rollback()  # the row was deleted mid-run (its user was): nothing to record
            log.info("job %s was deleted while running", job_id)
            return True
        except Cancelled:
            db.rollback()
            job.state = "cancelled"
        except _Interrupted:
            db.rollback()
            job.state, job.message = "failed", INTERRUPTED
        except JobError as exc:
            db.rollback()
            job.state, job.message = "failed", str(exc)
        except Exception:
            log.exception("job %s (%s) failed", job_id, job.kind)
            db.rollback()
            job.state, job.message = "failed", f"{job.kind} failed"
        job.finished_at = _now()
        try:
            db.commit()
        except (StaleDataError, ObjectDeletedError):
            db.rollback()
            log.info("job %s was deleted while running", job_id)
        return True
```

- [ ] **Step 4: Fix the SSE** in `api/routers/jobs.py`:

```python
def _snapshot(job_id: int) -> dict | None:
    """None once the row is gone (its user was deleted mid-stream)."""
    with SessionLocal() as s:
        job = s.get(Job, job_id, populate_existing=True)
        return None if job is None else JobOut.model_validate(job).model_dump(mode="json")
```

  - In `frames()`, right after `snap = await run_in_threadpool(_snapshot, job_id)`, add `if snap is None: return`.

- [ ] **Step 5: Run the tests to verify they pass**
  - Run: `pytest tests/test_jobs.py tests/test_jobs_api.py tests/test_scrape_api.py -q && ruff check .`
  - Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/jobs.py api/routers/jobs.py tests/test_jobs.py tests/test_jobs_api.py
git commit -m "fix(api): jobs deleted mid-run end quietly; SSE ends when the row goes"
```

---

### Task 6: Batch publish and volume illustrations as jobs

**Files:**
- Create: `api/publish_job.py`, `tests/test_wp_jobs.py`
- Modify: `api/publish.py` (append `volume_images`), `api/schemas/wp.py` (append `BatchPublishIn`), `api/routers/wp.py` (append two routes)

**Interfaces:**
- Consumes: Tasks 1–5; `jobs.handler`, `JobContext`, `JobError`, `jobs.enqueue`; `owned_ref`, `scoped_volume`, `parse_zone`.
- Produces:
  - `publish.volume_images(db, volume_id) -> tuple[list[dict], dict | None]`
  - job kind `wp_publish`: params `{"chapters": [{"document_id": int, "scheduled_for": str | None}], "confirm_republish": bool}`; result `{"chapters": [row]}`, row = `{document_id, title, series_order, scheduled_for, ok, error?, created?, post_url?, password?, unlock_chapter_index?}`
  - job kind `wp_illustrations`: params `{"volume_id": int, "series_id": int}`; result `{"page_url": str, "created": bool, "batches": int, "images": int}`
  - `POST /wp/batch` (`BatchPublishIn`) → 202 `JobOut`; `POST /volumes/{volume_id}/wp/illustrations` → 202 `JobOut`
  - `publish_job.http_client` (the seam tests replace)

- [ ] **Step 1: Write the failing tests** in `tests/test_wp_jobs.py`:

```python
import json
from contextlib import contextmanager

import httpx
import pytest

from api import jobs, publish_job
from api.models import Document, DocumentImage, Volume

SITE = "https://blog.example.com"
PUBLISH = "/wp-json/ta-publisher/v1/publish"
ILLUS = "/wp-json/ta-publisher/v1/illustrations"


@pytest.fixture
def wp_site(monkeypatch, db):
    """Fake WordPress for the job handlers; route the worker's sessions to the test db."""
    state = {"fail": set(), "posted": []}

    def handle(request):
        body = json.loads(request.content)
        state["posted"].append((request.url.path, body))
        if body.get("chapter_index") in state["fail"]:
            return httpx.Response(500, json={"error": "renumber_conflict"})
        return httpx.Response(200, json={"created": True, "page_url": "pg", "post_url": "po"})

    monkeypatch.setattr(publish_job, "http_client",
                        lambda: publish_job.wp_http.client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr("api.publish.check_user_url", lambda url, allow, label: None)

    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    return state


@pytest.fixture
def ready(app_client, me, make_series, db):
    app_client.post("/credentials", json={"kind": "wordpress", "secret": "k" * 12, "endpoint_url": SITE})
    s = make_series(me, "Sword")
    s.wp_series_slug, s.wp_series_title_short = "sword", "SotW"
    db.flush()
    return s


def chapters(make_doc, user, series, n):
    return [make_doc(user, [f"行{i}"], series=series, order=i) for i in range(1, n + 1)]


def test_batch_schedules_in_order_and_records_each(app_client, me, ready, make_doc, wp_site, db):
    docs = chapters(make_doc, me, ready, 3)
    r = app_client.post("/wp/batch", json={
        "document_ids": [d.id for d in reversed(docs)], "schedule": True,
        "start": "2026-11-01T20:00:00+09:00", "chapters_per_day": 2, "tz": "Asia/Tokyo"})
    assert r.status_code == 202 and r.json()["kind"] == "wp_publish"
    assert jobs.run_next() is True
    job = app_client.get(f"/jobs/{r.json()['id']}").json()
    assert job["state"] == "done"
    rows = job["result"]["chapters"]
    assert [x["series_order"] for x in rows] == [1, 2, 3] and all(x["ok"] for x in rows)
    dates = [b["publish_date"] for _, b in wp_site["posted"]]
    assert dates == ["2026-11-01T11:00:00Z", "2026-11-01T12:00:00Z", "2026-11-02T11:00:00Z"]
    for d in docs:
        db.refresh(d)
    assert {d.wp_status for d in docs} == {"future"}


def test_batch_now_publishes_without_dates(app_client, me, ready, make_doc, wp_site):
    docs = chapters(make_doc, me, ready, 2)
    app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False})
    jobs.run_next()
    assert all("publish_date" not in b for _, b in wp_site["posted"])


def test_one_failing_chapter_does_not_stop_the_rest(app_client, me, ready, make_doc, wp_site):
    docs = chapters(make_doc, me, ready, 3)
    wp_site["fail"].add(2)
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    jobs.run_next()
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert [x["ok"] for x in rows] == [True, False, True]
    assert rows[1]["error"] == "renumber_conflict"


def test_live_chapters_are_skipped_unless_confirmed(app_client, me, ready, make_doc, wp_site, db):
    docs = chapters(make_doc, me, ready, 2)
    docs[0].wp_status = "publish"
    db.flush()
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    jobs.run_next()
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert [x["ok"] for x in rows] == [False, True] and "already" in rows[0]["error"]
    assert len(wp_site["posted"]) == 1


def test_a_chapter_deleted_after_enqueue_is_a_failed_row(app_client, me, ready, make_doc, wp_site, db):
    docs = chapters(make_doc, me, ready, 2)
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    db.delete(docs[0])
    db.flush()
    jobs.run_next()
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert rows[0] == {"document_id": docs[0].id, "ok": False, "error": "the chapter no longer exists"}
    assert rows[1]["ok"] is True


def test_cancel_stops_between_chapters_keeping_what_was_published(
        app_client, me, ready, make_doc, wp_site, db, monkeypatch):
    docs = chapters(make_doc, me, ready, 3)
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    original = jobs.JobContext.progress

    def cancel_after_first(self, done, total, message=""):
        if done == 1:
            self.job.cancel_requested = True
        original(self, done, total, message)
    monkeypatch.setattr(jobs.JobContext, "progress", cancel_after_first)
    jobs.run_next()
    assert app_client.get(f"/jobs/{jid}").json()["state"] == "cancelled"
    db.refresh(docs[0])
    assert docs[0].wp_status == "publish" and len(wp_site["posted"]) == 1


def test_batch_enqueue_checks(app_client, me, ready, make_doc, make_user, make_series, wp_site, db):
    mine = chapters(make_doc, me, ready, 1)[0]
    theirs = make_doc(make_user(email="o@example.com"), ["x"])
    r = app_client.post("/wp/batch", json={"document_ids": [mine.id, theirs.id], "schedule": False})
    assert r.status_code == 422 and "document_ids" in r.json()["detail"]
    bare = make_series(me, "Bare")
    loose = make_doc(me, ["x"], series=bare, order=1)
    r = app_client.post("/wp/batch", json={"document_ids": [loose.id], "schedule": False})
    assert r.status_code == 422 and "Bare" in r.json()["detail"]
    r = app_client.post("/wp/batch", json={"document_ids": [mine.id]})
    assert r.status_code == 422  # scheduling needs a start
    r = app_client.post("/wp/batch", json={"document_ids": [mine.id], "schedule": False, "tz": "Nope/Zone"})
    assert r.status_code == 422
    assert app_client.post("/wp/batch", json={"document_ids": [mine.id], "schedule": False}).status_code == 202
    assert app_client.post("/wp/batch", json={"document_ids": [mine.id], "schedule": False}).status_code == 409


def test_passwords_are_kept_in_the_job_result(app_client, me, ready, make_doc, wp_site):
    app_client.put("/settings", json={"wp_password_enabled": True, "wp_unlock_after": 1})
    docs = chapters(make_doc, me, ready, 2)
    jid = app_client.post("/wp/batch", json={"document_ids": [d.id for d in docs], "schedule": False}).json()["id"]
    jobs.run_next()
    rows = app_client.get(f"/jobs/{jid}").json()["result"]["chapters"]
    assert rows[0]["password"] is None and len(rows[1]["password"]) == 12
    assert "k" * 12 not in json.dumps(app_client.get(f"/jobs/{jid}").json())


def test_illustrations_upload_in_batches(app_client, me, ready, make_doc, wp_site, db, monkeypatch):
    monkeypatch.setattr("api.core.wp._ILLUS_BATCH_BYTES", 50)  # cover (4) + a (40) fit; b splits
    vol = Volume(series_id=ready.id, title="Vol 1")
    db.add(vol)
    db.flush()
    doc = make_doc(me, ["一"], series=ready, order=1, volume=vol)
    db.add_all([
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="a.png", data=b"A" * 30),
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="b.png", data=b"B" * 30),
        DocumentImage(document_id=doc.id, anchor_position=0, src_path="c.jpg", data=b"C", is_cover=True),
    ])
    db.flush()
    r = app_client.post(f"/volumes/{vol.id}/wp/illustrations")
    assert r.status_code == 202
    jobs.run_next()
    job = app_client.get(f"/jobs/{r.json()['id']}").json()
    assert job["state"] == "done" and job["result"]["batches"] == 2 and job["result"]["images"] == 3
    modes = [(p, b["mode"], "cover" in b) for p, b in wp_site["posted"]]
    assert modes == [(ILLUS, "replace", True), (ILLUS, "append", False)]


def test_illustrations_need_images_and_your_volume(app_client, me, ready, make_user, make_series, db, wp_site):
    vol = Volume(series_id=ready.id, title="Empty")
    db.add(vol)
    theirs = make_series(make_user(email="o@example.com"), "T")
    other = Volume(series_id=theirs.id, title="Theirs")
    db.add(other)
    db.flush()
    r = app_client.post(f"/volumes/{vol.id}/wp/illustrations")
    assert r.status_code == 422 and "no illustrations" in r.json()["detail"]
    assert app_client.post(f"/volumes/{other.id}/wp/illustrations").status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**
  - Run: `pytest tests/test_wp_jobs.py -q`
  - Expected: FAIL (`ImportError: cannot import name 'publish_job'`).

- [ ] **Step 3: `volume_images`** — append to `api/publish.py`:

```python
def volume_images(db: Session, volume_id: int) -> tuple[list[dict], dict | None]:
    """The desktop _on_publish_volume_illustrations gathering: every chapter's images in
    reading order, the first cover, the rest unless excluded from export; shrunk.
    ponytail: the volume's art is held in memory at once (bounded by the import budget)."""
    rows = db.scalars(
        select(DocumentImage).join(Document, Document.id == DocumentImage.document_id)
        .where(Document.volume_id == volume_id)
        .order_by(Document.series_order, Document.id, DocumentImage.anchor_position,
                  DocumentImage.id)).all()
    cover = next((im for im in rows if im.is_cover), None)
    inline = [image_dict(im) for im in rows if not im.is_cover and not im.exclude_export]
    return inline, image_dict(cover) if cover is not None else None
```

- [ ] **Step 4: The batch schema** — append to `api/schemas/wp.py` (add `Field`, `model_validator` to the pydantic import):

```python
class BatchPublishIn(BaseModel):
    document_ids: list[int] = Field(min_length=1, max_length=500)
    schedule: bool = True  # the desktop dialog's default
    start: AwareDatetime | None = None
    chapters_per_day: int = Field(default=1, ge=1, le=99)
    tz: str = Field(default="UTC", max_length=64)
    confirm_republish: bool = False

    @model_validator(mode="after")
    def _start_when_scheduling(self) -> "BatchPublishIn":
        if self.schedule and self.start is None:
            raise ValueError("start: required when scheduling")
        return self
```

- [ ] **Step 5: Write `api/publish_job.py`**

```python
"""The WordPress jobs (spec §9, §10): batch publish/schedule (desktop _BatchPublishWorker)
and volume illustrations (desktop _IllustrationsPublishWorker). Each re-reads the user's
config, so a credential change between enqueue and run is honoured."""

import logging
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from api import publish, wp_prefs
from api.core import wp, wp_http
from api.core.wp import WPPublishError
from api.jobs import JobContext, JobError, handler
from api.models import Document, Volume
from api.wp_prefs import WpPrefs

log = logging.getLogger(__name__)
http_client = wp_http.client  # the seam tests replace


def _config(ctx: JobContext) -> tuple[str, str]:
    try:
        return publish.wp_config(ctx.db, ctx.job.user_id)
    except publish.NotReady as exc:
        raise JobError(str(exc)) from exc


def _publish_one(db: Session, c: httpx.Client, user_id: int, item: dict, endpoint: str,
                 key: str, prefs: WpPrefs, confirm: bool) -> dict:
    doc = db.get(Document, item["document_id"])
    if doc is None or doc.user_id != user_id:
        return {"document_id": item["document_id"], "ok": False,
                "error": "the chapter no longer exists"}
    scheduled = datetime.fromisoformat(item["scheduled_for"]) if item["scheduled_for"] else None
    row = {"document_id": doc.id, "title": doc.title, "series_order": doc.series_order,
           "scheduled_for": item["scheduled_for"]}
    try:
        if doc.wp_status in publish.LIVE and not confirm:  # ruling 6
            raise publish.NotReady("already published or scheduled; tick Overwrite to publish it again")
        ch = publish.build_chapter(db, doc, prefs)
        result = wp_http.publish(c, endpoint, publish.payload(
            ch, key, scheduled=scheduled, attribution=prefs.wp_attribution_enabled))
    except (publish.NotReady, WPPublishError) as exc:
        return {**row, "ok": False, "error": str(exc)}
    except Exception:  # one bad chapter must not stop the rest
        log.exception("publishing document %s failed", doc.id)
        return {**row, "ok": False, "error": "publishing this chapter failed"}
    publish.record(doc, result, scheduled)
    return {**row, "ok": True, "created": bool(result.get("created")),
            "post_url": str(result.get("post_url") or ""),
            "password": ch.password, "unlock_chapter_index": ch.unlock_chapter_index}


@handler("wp_publish")
def publish_batch(ctx: JobContext) -> dict:
    endpoint, key = _config(ctx)
    prefs = wp_prefs.load(ctx.db, ctx.job.user_id)
    items = ctx.params["chapters"]
    rows: list[dict] = []
    ctx.progress(0, len(items), "Starting")
    with http_client() as c:
        for i, item in enumerate(items, start=1):
            rows.append(_publish_one(ctx.db, c, ctx.job.user_id, item, endpoint, key, prefs,
                                     ctx.params["confirm_republish"]))
            ctx.progress(i, len(items), f"Chapter {i} of {len(items)}")
    return {"chapters": rows}


@handler("wp_illustrations")
def publish_illustrations(ctx: JobContext) -> dict:
    volume = ctx.db.get(Volume, ctx.params["volume_id"])
    series = volume.series if volume is not None else None
    if series is None or series.user_id != ctx.job.user_id:
        raise JobError("the volume no longer exists")
    endpoint, key = _config(ctx)
    try:
        publish.check_series(series)
    except publish.NotReady as exc:
        raise JobError(str(exc)) from exc
    inline, cover = publish.volume_images(ctx.db, volume.id)
    if not inline and cover is None:
        raise JobError("This volume has no illustrations to publish.")
    payloads = wp.build_illustrations_payloads(
        {"series_title": series.title, "volume_title": volume.title},
        publish.series_meta(series), inline, api_key=key, cover=cover)
    ctx.progress(0, len(payloads), "Uploading")
    first: dict | None = None
    with http_client() as c:
        for i, p in enumerate(payloads, start=1):
            try:
                result = wp_http.publish_illustrations(c, endpoint, p)
            except WPPublishError as exc:
                raise JobError(f"batch {i}/{len(payloads)}: {exc.message}") from exc
            first = first or result  # the desktop reports the first ("replace") answer
            ctx.progress(i, len(payloads), f"Batch {i} of {len(payloads)}")
    return {"page_url": str(first.get("page_url") or ""), "created": bool(first.get("created")),
            "batches": len(payloads), "images": len(inline) + (cover is not None)}
```

- [ ] **Step 6: The routes** — append to `api/routers/wp.py`
  - Extend the imports: `import api.publish_job  # noqa: F401  registers the wp_* handlers`; `from sqlalchemy import or_, select`; `from api import jobs`; `owned_ref, parse_zone, scoped_volume` from `api.deps`; `DocumentImage, Job` from `api.models`; `BatchPublishIn` from `api.schemas.wp`; `from api.schemas.jobs import JobOut`.

```python
@router.post("/wp/batch", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def batch_publish(
    body: BatchPublishIn, user: User = Depends(current_user), db: Session = Depends(db_session),
) -> Job:
    """The desktop Publish / Schedule Chapters: checks up front, slots computed now
    (desktop loop), the publishing itself in a job."""
    tz = parse_zone(body.tz)
    _ready(publish.wp_config, db, user.id)
    docs = [owned_ref(db, Document, i, user.id, "document_ids")
            for i in dict.fromkeys(body.document_ids)]
    for series in {d.series_id: d.series for d in docs}.values():
        if series is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "Only chapters in a series can be published.")
        _ready(publish.check_series, series)
    if db.scalar(select(Job.id).where(
        Job.user_id == user.id, Job.kind == "wp_publish", Job.state.in_(("queued", "running")),
    ).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "a batch publish is already queued or running")
    docs.sort(key=lambda d: (d.series.title, d.series_order, d.id))
    prefs = wp_prefs.load(db, user.id)
    slots = (publish.batch_slots(body.start, len(docs), body.chapters_per_day,
                                 prefs.wp_default_schedule_time, tz)
             if body.schedule else [None] * len(docs))
    chapters = [{"document_id": d.id, "scheduled_for": s.isoformat() if s else None}
                for d, s in zip(docs, slots, strict=True)]
    return jobs.enqueue(db, user.id, "wp_publish",
                        {"chapters": chapters, "confirm_republish": body.confirm_republish},
                        total=len(chapters))


@router.post("/volumes/{volume_id}/wp/illustrations", response_model=JobOut,
             status_code=status.HTTP_202_ACCEPTED)
def publish_volume_illustrations(
    volume_id: int, user: User = Depends(current_user), db: Session = Depends(db_session),
) -> Job:
    volume = scoped_volume(db, volume_id, user.id)
    _ready(publish.wp_config, db, user.id)
    _ready(publish.check_series, volume.series)
    if not db.scalar(
        select(DocumentImage.id).join(Document, Document.id == DocumentImage.document_id)
        .where(Document.volume_id == volume.id,
               or_(DocumentImage.is_cover, DocumentImage.exclude_export.is_(False)))
        .limit(1)
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "This volume has no illustrations to publish.")
    return jobs.enqueue(db, user.id, "wp_illustrations",
                        {"volume_id": volume.id, "series_id": volume.series_id})
```

  - `series_id` in the params lets `GET /jobs?series_id=` find the job, as with syosetu fetches.

- [ ] **Step 7: Run the tests to verify they pass**
  - Run: `pytest tests/test_wp_jobs.py tests/test_wp_publish.py -q && ruff check . && wc -l api/routers/wp.py api/publish.py api/publish_job.py`
  - Expected: PASS; each module under 400 lines.

- [ ] **Step 8: Commit**

```bash
git add api/publish.py api/publish_job.py api/schemas/wp.py api/routers/wp.py tests/test_wp_jobs.py
git commit -m "feat(api): batch publish and volume illustrations as jobs"
```

---

### Task 7: Statistics API

**Files:**
- Create: `api/core/stats.py`, `api/schemas/stats.py`, `api/routers/stats.py`, `tests/test_core_stats.py`, `tests/test_stats_api.py`
- Modify: `api/main.py`

**Interfaces:**
- Consumes: `deps.zone` (Task 3).
- Produces:
  - `stats.METRICS = ("paragraphs", "chars", "en_words")`
  - `stats.compute_streaks(history, today=None) -> dict` and `stats.compute_period_comparisons(history, metric, today) -> dict` (verbatim)
  - `stats.summarize(history, today) -> dict[str, dict[str, int]]` (keys `today`, `week`, `month`, `alltime`)
  - `GET /stats?tz=` → `StatsOut` `{today: date, daily: [DayStats], summary: {period: Totals}, streaks: Streaks, comparisons: {metric: Comparison}, series: [SeriesStats]}`

- [ ] **Step 1: Port the desktop tests**
  - Copy the `compute_streaks` and `compute_period_comparisons` sections of `/home/pun/workspace/TranslationAssistant-PySide6-Port/tests/test_core.py` (from the `# compute_streaks` header comment at line 1018 to the end of `test_period_comparisons_*`, around line 1140) into `tests/test_core_stats.py`. Change `from translation_assistant.core import ...` to `from api.core.stats import ...`.
  - Append:

```python
from api.core.stats import summarize


def test_summarize_windows_end_today():
    today = date(2026, 10, 13)
    history = [
        {"date": "2026-10-13", "paragraphs": 1, "chars": 10, "en_words": 2},
        {"date": "2026-10-07", "paragraphs": 2, "chars": 20, "en_words": 4},  # 7th day back
        {"date": "2026-10-06", "paragraphs": 4, "chars": 40, "en_words": 8},
        {"date": "2026-09-01", "paragraphs": 8, "chars": 80, "en_words": 16},
    ]
    s = summarize(history, today)
    assert s["today"] == {"paragraphs": 1, "chars": 10, "en_words": 2}
    assert s["week"]["paragraphs"] == 3 and s["month"]["paragraphs"] == 7
    assert s["alltime"]["paragraphs"] == 15
```

- [ ] **Step 2: Write the failing API tests** in `tests/test_stats_api.py`:

```python
from datetime import UTC, datetime, timedelta

from api.models import Line


def stamp(db, doc, when, text=None):
    for line in db.query(Line).filter_by(document_id=doc.id):
        line.translated_at = when
        if text is not None:
            line.translated_text = text
    db.flush()


def test_days_bucket_in_the_viewers_zone(app_client, me, make_doc, db):
    doc = make_doc(me, ["一"])
    stamp(db, doc, datetime(2026, 1, 1, 23, 30, tzinfo=UTC))
    utc = app_client.get("/stats", params={"tz": "UTC"}).json()
    tokyo = app_client.get("/stats", params={"tz": "Asia/Tokyo"}).json()
    assert [d["date"] for d in utc["daily"]] == ["2026-01-01"]
    assert [d["date"] for d in tokyo["daily"]] == ["2026-01-02"]


def test_metrics_follow_the_desktop_sql(app_client, me, make_doc, db):
    doc = make_doc(me, ["一二三", "四五"])
    stamp(db, doc, datetime(2026, 1, 1, tzinfo=UTC), text="  two words  ")
    day = app_client.get("/stats").json()["daily"][0]
    assert day == {"date": "2026-01-01", "paragraphs": 2, "chars": 5, "en_words": 4}


def test_untranslated_and_other_users_lines_are_not_counted(app_client, me, make_doc, make_user, db):
    make_doc(me, ["一"])  # translated_at NULL
    theirs = make_doc(make_user(email="o@example.com"), ["一"])
    stamp(db, theirs, datetime(2026, 1, 1, tzinfo=UTC))
    body = app_client.get("/stats").json()
    assert body["daily"] == [] and body["series"] == []
    assert body["streaks"]["current_streak"] == 0


def test_today_streaks_summary_and_comparisons(app_client, me, make_doc, db):
    now = datetime.now(UTC)
    stamp(db, make_doc(me, ["一", "二"]), now)
    stamp(db, make_doc(me, ["三"]), now - timedelta(days=1))
    body = app_client.get("/stats").json()
    assert body["today"] == now.date().isoformat()
    assert body["streaks"]["current_streak"] == 2
    assert body["summary"]["today"]["paragraphs"] == 2 and body["summary"]["week"]["paragraphs"] == 3
    assert body["comparisons"]["paragraphs"]["periods"]["today"]["pct_change"] == 100.0
    assert set(body["comparisons"]) == {"paragraphs", "chars", "en_words"}


def test_series_breakdown_skips_unsorted_chapters(app_client, me, make_doc, make_series, db):
    s = make_series(me, "Sword")
    stamp(db, make_doc(me, ["一", "二"], series=s, order=1), datetime(2026, 1, 1, tzinfo=UTC))
    stamp(db, make_doc(me, ["三"], series=s, order=2), datetime(2026, 1, 2, tzinfo=UTC))
    stamp(db, make_doc(me, ["四"]), datetime(2026, 1, 2, tzinfo=UTC))
    assert app_client.get("/stats").json()["series"] == [{
        "series_id": s.id, "series": "Sword", "paragraphs": 3, "chars": 3, "en_words": 3, "chapters": 2}]


def test_bad_zone_is_422(app_client, me):
    assert app_client.get("/stats", params={"tz": "Mars/Base"}).status_code == 422
```

  - `make_doc` translations are `tr:<raw>` (one word each), hence `en_words` 3 in the series test.

- [ ] **Step 3: Run them to verify they fail**
  - Run: `pytest tests/test_core_stats.py tests/test_stats_api.py -q`
  - Expected: FAIL (`ModuleNotFoundError: api.core.stats`; 404 for `/stats`).

- [ ] **Step 4: Write `api/core/stats.py`**
  - Docstring: `"""Statistics helpers, from the desktop core.py (compute_streaks, compute_period_comparisons, verbatim) plus summarize, which replaces the desktop get_summary_stats's four queries."""`
  - `from datetime import date, timedelta`; `METRICS = ("paragraphs", "chars", "en_words")`.
  - Copy `compute_streaks` and `compute_period_comparisons` verbatim from `translation_assistant/core.py` (lines 638–725), with their docstrings.
  - Append:

```python
def summarize(history: list[dict], today: date) -> dict[str, dict[str, int]]:
    """The desktop get_summary_stats windows — today, the last 7 days, the last 30 days
    (each ending today), and all time — summed from the daily rows."""
    def total(days: int | None) -> dict[str, int]:
        start = "" if days is None else (today - timedelta(days=days - 1)).isoformat()
        rows = [r for r in history if start <= r["date"] <= today.isoformat()]
        return {m: sum(r[m] for r in rows) for m in METRICS}

    return {"today": total(1), "week": total(7), "month": total(30), "alltime": total(None)}
```

- [ ] **Step 5: Write `api/schemas/stats.py`**

```python
from datetime import date

from pydantic import BaseModel


class Totals(BaseModel):
    paragraphs: int
    chars: int
    en_words: int


class DayStats(Totals):
    date: str  # ISO date in the requested zone


class Streaks(BaseModel):
    current_streak: int
    longest_streak: int
    best_day_date: str
    best_day_paras: int


class PeriodChange(BaseModel):
    current: int
    previous: int
    pct_change: float | None


class Comparison(BaseModel):
    periods: dict[str, PeriodChange]  # today | week | month
    daily_avg_30: float


class SeriesStats(Totals):
    series_id: int
    series: str
    chapters: int


class StatsOut(BaseModel):
    today: date
    daily: list[DayStats]  # oldest first; days with no translations are absent
    summary: dict[str, Totals]  # today | week | month | alltime
    streaks: Streaks
    comparisons: dict[str, Comparison]  # per metric
    series: list[SeriesStats]
```

- [ ] **Step 6: Write `api/routers/stats.py`**

```python
"""Statistics (spec §10): the desktop StatsDialog's data, derived from lines.translated_at,
with days in the viewer's time zone (ruling 2)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy import Date, case, cast, func, select, text
from sqlalchemy.orm import Session

from api.core import stats
from api.deps import current_user, db_session, zone
from api.models import Document, Line, Series, User
from api.routing import api_router
from api.schemas.stats import StatsOut

router = api_router(tags=["stats"])


def _metrics():
    """paragraphs, source chars, and the desktop's _EN_WORDS (spaces + 1 per trimmed line)."""
    t = func.btrim(Line.translated_text)
    words = case((t != "", func.length(t) - func.length(func.replace(t, " ", "")) + 1), else_=0)
    return (func.count(Line.id), func.coalesce(func.sum(func.length(Line.raw_text)), 0),
            func.coalesce(func.sum(words), 0))


@router.get("/stats", response_model=StatsOut)
def get_stats(
    tz: ZoneInfo = Depends(zone), user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> StatsOut:
    # ponytail: a zone Python knows but Postgres doesn't would 500; both ship IANA data
    day = cast(func.timezone(tz.key, Line.translated_at), Date)
    mine = (Line.translated_at.is_not(None), Document.user_id == user.id)
    rows = db.execute(
        select(day, *_metrics()).join(Document, Document.id == Line.document_id)
        .where(*mine).group_by(text("1")).order_by(text("1"))  # positional: the zone is a bind
    ).all()
    history = [{"date": d.isoformat(), "paragraphs": p, "chars": c, "en_words": w}
               for d, p, c, w in rows]
    today = datetime.now(tz).date()
    by_series = db.execute(
        select(Series.id, Series.title, *_metrics(), func.count(func.distinct(Line.document_id)))
        .join(Document, Document.id == Line.document_id)
        .join(Series, Series.id == Document.series_id)
        .where(*mine).group_by(Series.id, Series.title).order_by(func.count(Line.id).desc())
    ).all()
    return StatsOut(
        today=today, daily=history, summary=stats.summarize(history, today),
        streaks=stats.compute_streaks(history, today),
        comparisons={m: stats.compute_period_comparisons(history, m, today) for m in stats.METRICS},
        series=[{"series_id": i, "series": t, "paragraphs": p, "chars": c, "en_words": w,
                 "chapters": n} for i, t, p, c, w, n in by_series],
    )
```

  - In `api/main.py`, import `stats` with the other routers and add `app.include_router(stats.router)` after `wp.router`.

- [ ] **Step 7: Run the tests to verify they pass**
  - Run: `pytest tests/test_core_stats.py tests/test_stats_api.py tests/test_commit_boundary.py -q && ruff check .`
  - Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add api/core/stats.py api/schemas/stats.py api/routers/stats.py api/main.py tests/test_core_stats.py tests/test_stats_api.py
git commit -m "feat(api): statistics in the viewer's time zone"
```

---

### Task 8: SPA — WordPress settings and series fields

**Files:**
- Create: `web/src/time.ts`, `web/src/time.test.ts`, `web/src/publish/wp.ts`, `web/src/publish/wp.test.ts`, `web/src/settings/WpSettingsPage.tsx`, `web/src/library/SeriesWp.tsx`
- Modify: `web/src/App.tsx`, `web/src/Shell.tsx`, `web/src/library/SeriesPage.tsx`, `web/src/api/schema.d.ts` (generated)

**Interfaces:**
- Consumes: `GET /wp/prefs`, `POST /wp/test`, `PUT /settings`, `/credentials`, `PATCH /series/{id}` (existing WP fields).
- Produces:
  - `time.ts`: `browserZone(): string`, `toLocalInput(d: Date): string`, `fromLocalInput(v: string): string` (ISO instant), `defaultSlot(defaultTime: string, now?: Date): Date`
  - `publish/wp.ts`: `slugify(text): string`, `tocUrl(endpoint, slug): string`
  - Route `/settings/wp`; `<SeriesWp series={SeriesOut} />` on the series page.

- [ ] **Step 1: Regenerate the API types**
  - Run: `cd web && npm run gen:api`

- [ ] **Step 2: Write the failing vitest tests**
  - `web/src/time.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { defaultSlot, fromLocalInput, toLocalInput } from "./time";

describe("schedule defaults (desktop PublishConfirmDialog)", () => {
  const now = new Date(2026, 9, 13, 21, 15, 30);
  it("uses today's default time when it is still ahead", () => {
    expect(defaultSlot("22:00", now)).toEqual(new Date(2026, 9, 13, 22, 0, 0));
  });
  it("rolls to tomorrow once the default time has passed", () => {
    expect(defaultSlot("20:00", now)).toEqual(new Date(2026, 9, 14, 20, 0, 0));
  });
  it("is an hour from now without a default time", () => {
    expect(defaultSlot("", now).getTime() - now.getTime()).toBe(3_600_000);
  });
});

describe("datetime-local round trip", () => {
  it("formats in local time and parses back to the same instant", () => {
    const d = new Date(2026, 0, 2, 3, 4);
    expect(toLocalInput(d)).toBe("2026-01-02T03:04");
    expect(fromLocalInput("2026-01-02T03:04")).toBe(d.toISOString());
  });
});
```

  - `web/src/publish/wp.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { slugify, tocUrl } from "./wp";

describe("slugify (desktop wp_publisher.slugify)", () => {
  it.each([
    ["Sword of the Wanderer", "sword-of-the-wanderer"],
    ["Hello, World!", "hello-world"],
    ["  --a  --  b--  ", "a-b"],
    ["剣の放浪者", ""],
  ])("%s", (input, out) => expect(slugify(input)).toBe(out));
});

describe("tocUrl (desktop toc_page_url)", () => {
  it("strips the publish path and trailing slashes", () => {
    expect(tocUrl("https://x.com/wp-json/ta-publisher/v1/publish/", "s")).toBe("https://x.com/s/");
    expect(tocUrl("https://x.com", "s")).toBe("https://x.com/s/");
  });
});
```

- [ ] **Step 3: Run them to verify they fail**
  - Run: `cd web && npx vitest run src/time.test.ts src/publish/wp.test.ts`
  - Expected: FAIL (modules not found).

- [ ] **Step 4: Write `web/src/time.ts`**

```ts
/** The browser's IANA zone, sent as ?tz= / tz so the server judges "today" and "same day" as the user does. */
export const browserZone = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone;

/** "YYYY-MM-DDTHH:MM" for <input type="datetime-local">, in local time. */
export function toLocalInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** A datetime-local value (local time, no offset) as an ISO instant the API accepts. */
export const fromLocalInput = (value: string): string => new Date(value).toISOString();

/** The desktop dialogs' default slot: today at the default time (tomorrow if passed), else an hour from now. */
export function defaultSlot(defaultTime: string, now: Date = new Date()): Date {
  const m = /^(\d{2}):(\d{2})$/.exec(defaultTime);
  if (!m) return new Date(now.getTime() + 3_600_000);
  const d = new Date(now);
  d.setHours(Number(m[1]), Number(m[2]), 0, 0);
  if (d <= now) d.setDate(d.getDate() + 1);
  return d;
}
```

- [ ] **Step 5: Write `web/src/publish/wp.ts`**

```ts
const ENDPOINT_PATH = "/wp-json/ta-publisher/v1/publish";

/** The desktop wp_publisher.slugify: lowercase ASCII words joined by dashes. */
export const slugify = (text: string): string =>
  text.toLowerCase().replace(/[^a-z0-9\s-]/g, "").replace(/[-\s]+/g, "-").replace(/^-+|-+$/g, "");

/** The series TOC page: the site root plus the slug (desktop toc_page_url). */
export function tocUrl(endpoint: string, slug: string): string {
  let base = endpoint.replace(/\/+$/, "");
  if (base.endsWith(ENDPOINT_PATH)) base = base.slice(0, -ENDPOINT_PATH.length);
  return `${base}/${slug}/`;
}
```

- [ ] **Step 6: Run the vitest tests to verify they pass**
  - Run: `cd web && npx vitest run src/time.test.ts src/publish/wp.test.ts`
  - Expected: PASS.

- [ ] **Step 7: Write `web/src/settings/WpSettingsPage.tsx`** (the desktop WPSettingsDialog):

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";

/** Settings → WordPress: endpoint and API key (a credential), publish defaults (user settings), a connection test. */
export default function WpSettingsPage() {
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey: ["wp", "prefs"], queryFn: () => call(api.GET("/wp/prefs")) });
  const creds = useQuery({ queryKey: ["wp", "credentials"], queryFn: () => call(api.GET("/credentials")) });
  const [note, setNote] = useState("");
  const cred = creds.data?.find((c) => c.kind === "wordpress" && c.name === "");
  const refresh = (msg: string) => { setNote(msg); return queryClient.invalidateQueries({ queryKey: ["wp"] }); };

  const saveCred = useMutation({
    mutationFn: (v: { endpoint_url: string; secret?: string }) => cred
      ? call(api.PATCH("/credentials/{credential_id}", { params: { path: { credential_id: cred.id } }, body: v }))
      : call(api.POST("/credentials", { body: { kind: "wordpress", name: "", secret: v.secret ?? "", endpoint_url: v.endpoint_url } })),
    onSuccess: () => refresh("Saved"),
  });
  const savePrefs = useMutation({
    mutationFn: (body: Schemas["WpPrefsOut"]) => call(api.PUT("/settings", { body })),
    onSuccess: () => refresh("Saved"),
  });
  const test = useMutation({ mutationFn: () => call(api.POST("/wp/test")) });

  const submitCred = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const secret = String(f.get("key") ?? "").trim();
    const el = e.currentTarget;
    saveCred.mutate({ endpoint_url: String(f.get("url") ?? "").trim(), ...(secret ? { secret } : {}) },
      { onSuccess: () => { (el.elements.namedItem("key") as HTMLInputElement).value = ""; } });
  };
  const submitPrefs = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    savePrefs.mutate({
      wp_password_enabled: f.get("pw") === "on",
      wp_unlock_after: Number(f.get("unlock")),
      wp_attribution_enabled: f.get("attr") === "on",
      wp_default_schedule_time: f.get("timed") === "on" ? String(f.get("time")) : "",
      wp_chapters_per_day: Number(f.get("perday")),
      wp_schedule_scope_global: f.get("global") === "on",
    });
  };
  const keyState = cred?.secret_unreadable ? "Saved key cannot be read; enter it again"
    : cred?.has_secret ? `Key saved ${cred.secret_hint}` : "No key saved";
  const error = prefs.error ?? creds.error ?? saveCred.error ?? savePrefs.error ?? test.error;
  const p = prefs.data;
  return (
    <main>
      <h1>WordPress</h1>
      {error && <p className="error" role="alert">{error.message}</p>}
      {note && <p role="status">{note}</p>}
      <form className="stack" key={cred?.endpoint_url ?? ""} onSubmit={submitCred}>
        <label>Endpoint URL <input name="url" aria-label="WordPress endpoint URL" required
          placeholder="https://yoursite.com/wp-json/ta-publisher/v1/publish" defaultValue={cred?.endpoint_url ?? ""} /></label>
        <label>API key <input name="key" type="password" aria-label="WordPress API key" autoComplete="off"
          required={!cred} placeholder="WP Admin → Settings → TA Publisher" /></label>
        <span className="muted">{keyState}</span>
        <div className="toolbar">
          <button type="submit" disabled={saveCred.isPending}>Save connection</button>
          <button type="button" disabled={!cred || test.isPending} onClick={() => test.mutate()}>Test connection</button>
        </div>
        {test.data && <p role="status" className={test.data.ok ? "" : "error"}>{test.data.message}</p>}
      </form>
      {p && (
        <form className="stack" key={JSON.stringify(p)} onSubmit={submitPrefs}>
          <h2>Defaults</h2>
          <label><input type="checkbox" name="pw" defaultChecked={p.wp_password_enabled} /> Enable password protection by default</label>
          <label>Keep N chapters locked <input type="number" name="unlock" min={1} max={99} defaultValue={p.wp_unlock_after} /></label>
          <label><input type="checkbox" name="attr" defaultChecked={p.wp_attribution_enabled} /> Add attribution footer to published chapters</label>
          <label><input type="checkbox" name="timed" defaultChecked={!!p.wp_default_schedule_time} /> Set default schedule time</label>
          <label>Time <input type="time" name="time" defaultValue={p.wp_default_schedule_time || "20:00"} /></label>
          <label>Chapters per day <input type="number" name="perday" min={1} max={99} defaultValue={p.wp_chapters_per_day} /></label>
          <label><input type="checkbox" name="global" defaultChecked={p.wp_schedule_scope_global} /> Count chapters/day across all series</label>
          <div className="toolbar"><button type="submit" disabled={savePrefs.isPending}>Save defaults</button></div>
        </form>
      )}
    </main>
  );
}
```

  - In `web/src/App.tsx` add `import WpSettingsPage from "./settings/WpSettingsPage";` and `<Route path="settings/wp" element={<WpSettingsPage />} />` after the `settings/mt` route.
  - In `web/src/Shell.tsx` add `<NavLink to="/settings/wp">WordPress</NavLink>` after the Machine translation link.

- [ ] **Step 8: Write `web/src/library/SeriesWp.tsx`** (the desktop Set WP Fields dialog and Open TOC):

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";
import { slugify, tocUrl } from "../publish/wp";
import { invalidateLibrary } from "./queries";

/** A series' WordPress fields: slug, short title, password override (inherit/on/off), unlock-after override. */
export default function SeriesWp({ series }: { series: Schemas["SeriesOut"] }) {
  const queryClient = useQueryClient();
  const creds = useQuery({ queryKey: ["wp", "credentials"], queryFn: () => call(api.GET("/credentials")) });
  const endpoint = creds.data?.find((c) => c.kind === "wordpress" && c.name === "")?.endpoint_url ?? "";
  const save = useMutation({
    mutationFn: (body: Schemas["SeriesUpdate"]) =>
      call(api.PATCH("/series/{series_id}", { params: { path: { series_id: series.id } }, body })),
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const pw = String(f.get("pw"));
    const unlock = String(f.get("unlock") ?? "").trim();
    save.mutate({
      wp_series_slug: String(f.get("slug") ?? "").trim(),
      wp_series_title_short: String(f.get("short") ?? "").trim(),
      wp_password_enabled: pw === "" ? null : pw === "on",
      wp_unlock_after: unlock === "" ? null : Number(unlock),
    });
  };
  const pwValue = series.wp_password_enabled === null ? "" : series.wp_password_enabled ? "on" : "off";
  return (
    <section>
      <h2>WordPress</h2>
      <form className="stack" key={`${series.id}-${series.wp_series_slug}-${series.wp_series_title_short}`} onSubmit={submit}>
        <label>Series slug <input name="slug" defaultValue={series.wp_series_slug || slugify(series.title)} /></label>
        <label>Short title <input name="short" defaultValue={series.wp_series_title_short} /></label>
        <label>Password protection{" "}
          <select name="pw" defaultValue={pwValue}>
            <option value="">Use my default</option>
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </label>
        <label>Keep N chapters locked <input name="unlock" type="number" min={0} placeholder="my default"
          defaultValue={series.wp_unlock_after ?? ""} /></label>
        <div className="toolbar">
          <button disabled={save.isPending}>Save WordPress fields</button>
          {endpoint && series.wp_series_slug && (
            <a href={tocUrl(endpoint, series.wp_series_slug)} target="_blank" rel="noreferrer">Open TOC page</a>
          )}
        </div>
        {save.error && <p className="error" role="alert">{save.error.message}</p>}
      </form>
    </section>
  );
}
```

  - In `web/src/library/SeriesPage.tsx` import `SeriesWp` and render `<SeriesWp series={series} />` after the series `<form>`.

- [ ] **Step 9: Type-check, test, build**
  - Run: `cd web && npm test && npm run build`
  - Expected: PASS, no type errors.

- [ ] **Step 10: Commit**

```bash
git add web/src/time.ts web/src/time.test.ts web/src/publish web/src/settings/WpSettingsPage.tsx web/src/library/SeriesWp.tsx web/src/library/SeriesPage.tsx web/src/App.tsx web/src/Shell.tsx web/src/api/schema.d.ts
git commit -m "feat(web): WordPress settings page and series WordPress fields"
```

---

### Task 9: SPA — publish, batch publish, illustrations

**Files:**
- Create: `web/src/publish/PublishDialog.tsx`, `web/src/publish/BatchPublish.tsx`, `web/src/publish/badge.ts`, `web/src/publish/badge.test.ts`
- Modify: `web/src/jobs/JobProgress.tsx`, `web/src/library/DocumentRow.tsx`, `web/src/library/Picker.tsx`, `web/src/library/Volumes.tsx`

**Interfaces:**
- Consumes: `POST /documents/{id}/wp/status`, `POST /documents/{id}/wp/publish`, `POST /wp/batch`, `POST /volumes/{id}/wp/illustrations`, `GET /wp/prefs`; `browserZone`, `toLocalInput`, `fromLocalInput`, `defaultSlot` (Task 8); `JobProgress`.
- Produces:
  - `JobProgress` gains an optional prop `outcome?: (job: Job) => ReactNode`, used for `done`/`cancelled` instead of the syosetu summary.
  - `badge.ts`: `wpBadge(doc: { wp_status: string; wp_published_at: string | null }): string` — `"pub 10/13 20:00"`, `"sched …"`, or `""` (desktop `_wp_cell`).
  - `<PublishDialog doc={Doc} onClose={() => void} />`, `<BatchPublish ids={number[]} onClose={() => void} />`.

- [ ] **Step 1: Write the failing badge test** `web/src/publish/badge.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { wpBadge } from "./badge";

describe("wpBadge (desktop picker WP column)", () => {
  const at = new Date(2026, 9, 13, 20, 5).toISOString();
  it("labels published and scheduled chapters with their date", () => {
    expect(wpBadge({ wp_status: "publish", wp_published_at: at })).toBe("pub 10/13 20:05");
    expect(wpBadge({ wp_status: "future", wp_published_at: at })).toBe("sched 10/13 20:05");
  });
  it("is the bare tag without a date and empty otherwise", () => {
    expect(wpBadge({ wp_status: "publish", wp_published_at: null })).toBe("pub");
    expect(wpBadge({ wp_status: "draft", wp_published_at: at })).toBe("");
    expect(wpBadge({ wp_status: "", wp_published_at: null })).toBe("");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**
  - Run: `cd web && npx vitest run src/publish/badge.test.ts`
  - Expected: FAIL (module not found).

- [ ] **Step 3: Write `web/src/publish/badge.ts`**

```ts
const TAGS: Record<string, string> = { publish: "pub", future: "sched" };

/** The picker's WordPress cell: tag plus local "MM/DD HH:MM" (desktop _fmt_wp_date). */
export function wpBadge(doc: { wp_status: string; wp_published_at: string | null }): string {
  const tag = TAGS[doc.wp_status] ?? "";
  if (!tag || !doc.wp_published_at) return tag;
  const d = new Date(doc.wp_published_at);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${tag} ${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
```

  - Run: `cd web && npx vitest run src/publish/badge.test.ts` — Expected: PASS.

- [ ] **Step 4: Generalize `JobProgress`** in `web/src/jobs/JobProgress.tsx`
  - Add `import type { ReactNode } from "react";` and change the signature to `({ jobId, onDone, outcome }: { jobId: number; onDone?: (job: Job) => void; outcome?: (job: Job) => ReactNode })`.
  - Right after the `if (job.state === "failed") return ...;` line, add `if (outcome) return <div role="status">{outcome(job)}</div>;`. The syosetu summary below stays the default.

- [ ] **Step 5: Write `web/src/publish/PublishDialog.tsx`** (desktop PublishConfirmDialog + show_publish_result):

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError, call, type Schemas } from "../api/client";
import type { Doc } from "../library/group";
import { invalidateLibrary } from "../library/queries";
import { browserZone, defaultSlot, fromLocalInput, toLocalInput } from "../time";

const LABEL: Record<string, string> = { publish: "Published", future: "Scheduled", draft: "Draft", "": "Not published" };

/** Publish one chapter: live status, the previous-chapter warning, optional schedule, then the result. */
export default function PublishDialog({ doc, onClose }: { doc: Doc; onClose: () => void }) {
  const queryClient = useQueryClient();
  const id = { params: { path: { document_id: doc.id } } };
  const status = useQuery({
    queryKey: ["wp", "status", doc.id], retry: false, gcTime: 0,
    queryFn: () => call(api.POST("/documents/{document_id}/wp/status", { ...id, params: { ...id.params, query: { tz: browserZone() } } })),
  });
  const prefs = useQuery({ queryKey: ["wp", "prefs"], queryFn: () => call(api.GET("/wp/prefs")) });
  const [schedule, setSchedule] = useState<boolean | null>(null); // null: follow the server's suggestion
  const [when, setWhen] = useState("");
  const [result, setResult] = useState<Schemas["PublishOut"] | null>(null);
  const suggested = status.data?.suggested_slot ? new Date(status.data.suggested_slot) : null;
  const scheduling = schedule ?? !!status.data?.previous_scheduled;
  const slot = when || toLocalInput(suggested ?? defaultSlot(prefs.data?.wp_default_schedule_time ?? ""));
  const run = useMutation({
    mutationFn: async () => {
      const body = { scheduled_for: scheduling ? fromLocalInput(slot) : null, confirm_republish: false };
      try {
        return await call(api.POST("/documents/{document_id}/wp/publish", { ...id, body }));
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 409 || !window.confirm(`${e.message}\n\nPublish anyway?`)) throw e;
        return call(api.POST("/documents/{document_id}/wp/publish", { ...id, body: { ...body, confirm_republish: true } }));
      }
    },
    onSuccess: (r) => { setResult(r); return invalidateLibrary(queryClient); },
  });
  const chapter = doc.series_order === 0 ? "Synopsis" : `Chapter ${doc.series_order}`;
  return (
    <dialog open aria-label="Publish to WordPress" className="stack">
      {result ? (
        <>
          <p role="status">{result.created || result.updated ? (result.scheduled_for ? "Scheduled!" : result.created ? "Published!" : "Updated!") : "Already published."}</p>
          {result.page_url && <p>Page: <a href={result.page_url} target="_blank" rel="noreferrer">{result.page_url}</a></p>}
          {result.post_url && <p>Post: <a href={result.post_url} target="_blank" rel="noreferrer">{result.post_url}</a></p>}
          {result.password && <label>Password (copy this) <input readOnly value={result.password} onFocus={(e) => e.currentTarget.select()} /></label>}
          {result.unlock_chapter_index !== null && <p>Chapter {result.unlock_chapter_index} is now unlocked.</p>}
        </>
      ) : (
        <>
          <p>WP status: {status.isPending ? "checking…" : status.data
            ? `${LABEL[status.data.status] ?? status.data.status}${status.data.remote_error ? ` (cached — ${status.data.remote_error})` : ""}` : "unknown"}</p>
          <p>Publish <b>{doc.chapter_title || doc.title}</b> ({chapter}) to WordPress?
            {status.data?.status === "publish" && " Republishing will overwrite the live chapter."}</p>
          {status.data?.previous_scheduled && (
            <p className="error">Warning: Chapter {doc.series_order - 1} is still scheduled and hasn't gone live yet.</p>
          )}
          <label><input type="checkbox" checked={scheduling} onChange={(e) => setSchedule(e.target.checked)} /> Schedule for later</label>
          <label>When <input type="datetime-local" disabled={!scheduling} value={slot} onChange={(e) => setWhen(e.target.value)} /></label>
        </>
      )}
      {(status.error ?? run.error) && <p className="error" role="alert">{(status.error ?? run.error)!.message}</p>}
      <div className="toolbar">
        {!result && <button disabled={run.isPending || status.isError} onClick={() => run.mutate()}>
          {status.data?.previous_scheduled ? "Publish anyway" : "Publish"}</button>}
        <button onClick={onClose}>{result ? "Close" : "Cancel"}</button>
      </div>
    </dialog>
  );
}
```

  - A 422 from the status call (WordPress not configured, series fields missing) shows as the alert, and Publish stays disabled.

- [ ] **Step 6: Write `web/src/publish/BatchPublish.tsx`** (desktop `_BatchPublishDialog` + `_show_batch_summary`):

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../api/client";
import JobProgress from "../jobs/JobProgress";
import type { Job } from "../jobs/follow";
import { invalidateLibrary } from "../library/queries";
import { browserZone, defaultSlot, fromLocalInput, toLocalInput } from "../time";

interface Row {
  document_id: number; title?: string; series_order?: number; scheduled_for?: string | null;
  ok: boolean; error?: string; password?: string | null; unlock_chapter_index?: number | null;
}

function Summary({ job }: { job: Job }) {
  const rows = ((job.result ?? {}) as { chapters?: Row[] }).chapters ?? [];
  const when = (r: Row) => (r.scheduled_for ? new Date(r.scheduled_for).toLocaleString() : "now");
  return (
    <>
      <p>{job.state === "cancelled" ? "Cancelled. " : ""}{rows.filter((r) => r.ok).length} / {rows.length} published.</p>
      <ul>
        {rows.map((r) => (
          <li key={r.document_id} className={r.ok ? "" : "error"}>
            {r.ok ? "✓" : "✗"} ch {r.series_order ?? "?"} {r.title ?? ""}: {r.ok ? when(r) : r.error}
            {r.password && <> — password <code>{r.password}</code></>}
            {r.unlock_chapter_index != null && <> — chapter {r.unlock_chapter_index} unlocked</>}
          </li>
        ))}
      </ul>
    </>
  );
}

/** Publish or schedule the selected chapters as one job. */
export default function BatchPublish({ ids, onClose }: { ids: number[]; onClose: () => void }) {
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey: ["wp", "prefs"], queryFn: () => call(api.GET("/wp/prefs")) });
  const [schedule, setSchedule] = useState(true);
  const [jobId, setJobId] = useState<number | null>(null);
  const start = useMutation({
    mutationFn: (f: FormData) => call(api.POST("/wp/batch", { body: {
      document_ids: ids, schedule, tz: browserZone(),
      start: schedule ? fromLocalInput(String(f.get("start"))) : null,
      chapters_per_day: schedule ? Number(f.get("perday")) : 1, confirm_republish: f.get("overwrite") === "on",
    } })),
    onSuccess: (job) => setJobId(job.id),
  });
  const submit = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); start.mutate(new FormData(e.currentTarget)); };
  const p = prefs.data;
  return (
    <dialog open aria-label="Publish / Schedule Chapters" className="stack">
      {jobId !== null ? (
        <JobProgress jobId={jobId} onDone={() => invalidateLibrary(queryClient)} outcome={(job) => <Summary job={job} />} />
      ) : p && (
        <form className="stack" onSubmit={submit}>
          <p>{ids.length} chapter(s) selected.</p>
          <label><input type="checkbox" checked={schedule} onChange={(e) => setSchedule(e.target.checked)} /> Schedule (unchecked = publish all now)</label>
          <label>Start <input type="datetime-local" name="start" disabled={!schedule} required={schedule}
            defaultValue={toLocalInput(defaultSlot(p.wp_default_schedule_time))} /></label>
          <label>Chapters per day <input type="number" name="perday" min={1} max={99} disabled={!schedule}
            defaultValue={p.wp_chapters_per_day} /></label>
          <label><input type="checkbox" name="overwrite" /> Overwrite chapters already published or scheduled</label>
          <div className="toolbar"><button disabled={start.isPending}>Start</button></div>
        </form>
      )}
      {(prefs.error ?? start.error) && <p className="error" role="alert">{(prefs.error ?? start.error)!.message}</p>}
      <div className="toolbar"><button onClick={onClose}>Close</button></div>
    </dialog>
  );
}
```

  - A disabled input is not submitted, hence `chapters_per_day: 1` when not scheduling (`Number(null)` would fail the API's `ge=1`).

- [ ] **Step 7: Wire the picker**
  - `web/src/library/DocumentRow.tsx`:
    - Import `useState` (already), `PublishDialog` and `wpBadge`.
    - Add `const [publishing, setPublishing] = useState(false);`.
    - Add a cell after the Edited cell: `<td className="muted">{wpBadge(doc)}</td>`.
    - In the export cell, after the Ruby MD link: `{doc.series_id !== null && <>{" "}<button type="button" onClick={() => setPublishing(true)}>Publish…</button></>}` and `{publishing && <PublishDialog doc={doc} onClose={() => setPublishing(false)} />}`.
  - `web/src/library/Picker.tsx`:
    - Import `BatchPublish`; add `const [batch, setBatch] = useState<number[] | null>(null);`.
    - Toolbar, after the Delete button: `<button disabled={!visible.length || busy} onClick={() => setBatch(visible)}>Publish {visible.length || ""}</button>`.
    - After `{creating && ...}`: `{batch && <BatchPublish ids={batch} onClose={() => setBatch(null)} />}`.
    - Add `<th>WordPress</th>` after `<th>Edited</th>`.
- [ ] **Step 8: Publish illustrations per volume** in `web/src/library/Volumes.tsx`
  - Import `JobProgress`.
  - In `VolumeEditor` add:

```tsx
  const [illusJob, setIllusJob] = useState<number | null>(null);
  const illus = useMutation({
    mutationFn: () => call(api.POST("/volumes/{volume_id}/wp/illustrations", { params: { path: { volume_id: volume.id } } })),
    onSuccess: (job) => setIllusJob(job.id),
  });
```

  - Add `illus.error` to the `error` chain.
  - In the EPUB toolbar, after the EPUB link:

```tsx
        <button type="button" disabled={illus.isPending || illusJob !== null} onClick={() => {
          if (window.confirm(`Publish the illustrations of "${volume.title}" to WordPress? An existing illustrations page for this volume will be overwritten.`)) illus.mutate();
        }}>Publish illustrations</button>
```

  - Below that toolbar: `{illusJob !== null && <JobProgress jobId={illusJob} outcome={(j) => { const r = (j.result ?? {}) as { page_url?: string; created?: boolean }; return <p>{j.state === "cancelled" ? "Cancelled" : `${r.created ? "Created" : "Updated"} the volume illustrations page`} {r.page_url && <a href={r.page_url} target="_blank" rel="noreferrer">{r.page_url}</a>}</p>; }} />}`

- [ ] **Step 9: Type-check, test, build, size check**
  - Run: `cd web && npm test && npm run build && wc -l src/publish/*.tsx src/library/Volumes.tsx src/library/DocumentRow.tsx`
  - Expected: PASS; every component file under 300 lines.

- [ ] **Step 10: Commit**

```bash
git add web/src/publish web/src/jobs/JobProgress.tsx web/src/library/DocumentRow.tsx web/src/library/Picker.tsx web/src/library/Volumes.tsx
git commit -m "feat(web): publish dialog, batch publish and volume illustrations"
```

---

### Task 10: SPA — Statistics page

**Files:**
- Create: `web/src/stats/heatmap.ts`, `web/src/stats/heatmap.test.ts`, `web/src/stats/Heatmap.tsx`, `web/src/stats/StatsPage.tsx`
- Modify: `web/src/App.tsx`, `web/src/Shell.tsx`, `web/src/api/schema.d.ts` (generated)

**Interfaces:**
- Consumes: `GET /stats?tz=`, `GET/PUT /settings` (`stats_metric`), `browserZone`.
- Produces:
  - `heatmap.ts`: `METRICS`, `type Metric`, `weeks(today: string): (string | null)[][]` (52 columns × 7 rows, Sunday first, `null` after today), `thresholds(values: number[]): number[]`, `intensity(value: number, th: number[]): number` (0–4), `COLORS: string[]`
  - Route `/stats`, nav link "Statistics".

- [ ] **Step 1: Regenerate the API types**
  - Run: `cd web && npm run gen:api`

- [ ] **Step 2: Write the failing test** `web/src/stats/heatmap.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { intensity, thresholds, weeks } from "./heatmap";

describe("weeks (desktop HeatmapWidget layout)", () => {
  const grid = weeks("2026-10-13"); // a Tuesday
  it("has 52 Sunday-first columns ending with today's week", () => {
    expect(grid).toHaveLength(52);
    expect(grid[51]).toEqual(["2026-10-11", "2026-10-12", "2026-10-13", null, null, null, null]);
    expect(grid[0][0]).toBe("2025-10-19");
  });
});

describe("intensity (desktop quartiles of the max)", () => {
  it("is 0 for no work and 1–4 by quartile", () => {
    const th = thresholds([0, 4, 8]);
    expect(th).toEqual([0, 2, 4, 6, 8]);
    expect([0, 1, 2, 5, 8].map((v) => intensity(v, th))).toEqual([0, 1, 1, 2, 4]);
  });
  it("uses fixed steps when there is no data", () => {
    expect(thresholds([])).toEqual([0, 1, 2, 3, 4]);
  });
});
```

- [ ] **Step 3: Run it to verify it fails**
  - Run: `cd web && npx vitest run src/stats/heatmap.test.ts` — Expected: FAIL (module not found).

- [ ] **Step 4: Write `web/src/stats/heatmap.ts`**

```ts
export const METRICS = ["paragraphs", "chars", "en_words"] as const;
export type Metric = (typeof METRICS)[number];
export const COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]; // desktop _COLORS

/** 52 week columns of 7 ISO dates (Sunday first) ending with the week of `today`; null after today. */
export function weeks(today: string): (string | null)[][] {
  const t = new Date(`${today}T00:00:00Z`);
  const start = new Date(t);
  start.setUTCDate(t.getUTCDate() - t.getUTCDay() - 51 * 7);
  return Array.from({ length: 52 }, (_, col) => Array.from({ length: 7 }, (_, row) => {
    const d = new Date(start);
    d.setUTCDate(start.getUTCDate() + col * 7 + row);
    const iso = d.toISOString().slice(0, 10);
    return iso > today ? null : iso;
  }));
}

/** The desktop's level boundaries: quarters of the all-time max. */
export function thresholds(values: number[]): number[] {
  const max = values.reduce((a, b) => Math.max(a, b), 0);
  if (max <= 0) return [0, 1, 2, 3, 4];
  const q = max / 4;
  return [0, q, 2 * q, 3 * q, max];
}

export function intensity(value: number, th: number[]): number {
  if (value === 0) return 0;
  for (let level = 4; level > 0; level--) if (value >= th[level]) return level;
  return 1;
}
```

  - Run: `cd web && npx vitest run src/stats/heatmap.test.ts` — Expected: PASS.

- [ ] **Step 5: Write `web/src/stats/Heatmap.tsx`**

```tsx
import type { Schemas } from "../api/client";
import { COLORS, intensity, thresholds, weeks, type Metric } from "./heatmap";

const CELL = 13, STEP = 15, LEFT = 30, TOP = 16;
const UNITS: Record<Metric, string> = { paragraphs: "paras", chars: "chars", en_words: "EN words" };
const longDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "long" });

/** The 52-week activity grid; the per-day table below the page carries the same data for screen readers. */
export default function Heatmap({ today, daily, metric, onPick }: {
  today: string; daily: Schemas["DayStats"][]; metric: Metric; onPick: (iso: string) => void;
}) {
  const byDate = new Map(daily.map((d) => [d.date, d]));
  const th = thresholds(daily.map((d) => d[metric]));
  const grid = weeks(today);
  const months = grid.map((col, i) => (i > 0 && col[0]!.slice(5, 7) !== grid[i - 1][0]!.slice(5, 7)
    ? new Date(`${col[0]}T00:00:00`).toLocaleDateString(undefined, { month: "short" }) : ""));
  return (
    <svg role="img" aria-label={`Activity heatmap of ${UNITS[metric]} over the last 52 weeks`}
      width={LEFT + 52 * STEP} height={TOP + 7 * STEP} style={{ maxWidth: "100%" }}>
      {[[1, "Mon"], [3, "Wed"], [5, "Fri"]].map(([row, name]) => (
        <text key={name} x={LEFT - 4} y={TOP + (row as number) * STEP + 10} textAnchor="end" fontSize="9" fill="#767676">{name}</text>
      ))}
      {months.map((m, i) => m && <text key={i} x={LEFT + i * STEP} y={TOP - 4} fontSize="9" fill="#767676">{m}</text>)}
      {grid.flatMap((col, c) => col.map((iso, r) => {
        if (!iso) return null;
        const d = byDate.get(iso);
        const tip = `${longDate(iso)}: ${d?.paragraphs ?? 0} paras · ${d?.chars ?? 0} chars · ${d?.en_words ?? 0} EN words`;
        return (
          <rect key={iso} x={LEFT + c * STEP} y={TOP + r * STEP} width={CELL} height={CELL}
            fill={COLORS[intensity(d?.[metric] ?? 0, th)]} onClick={() => onPick(iso)} style={{ cursor: "pointer" }}>
            <title>{tip}</title>
          </rect>
        );
      }))}
    </svg>
  );
}
```

- [ ] **Step 6: Write `web/src/stats/StatsPage.tsx`** (desktop StatsDialog: Overview + By Series):

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import { browserZone } from "../time";
import Heatmap from "./Heatmap";
import { COLORS, METRICS, type Metric } from "./heatmap";

const LABELS: Record<Metric, string> = { paragraphs: "Paragraphs", chars: "Source Chars", en_words: "EN Words" };
const UNITS: Record<Metric, string> = { paragraphs: "paragraphs", chars: "source chars", en_words: "EN words" };
const n = (v: number) => v.toLocaleString();
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(0)}%`);
const longDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "long" });

export default function StatsPage() {
  const queryClient = useQueryClient();
  const stats = useQuery({ queryKey: ["stats"], queryFn: () => call(api.GET("/stats", { params: { query: { tz: browserZone() } } })) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const saveMetric = useMutation({
    mutationFn: (m: Metric) => call(api.PUT("/settings", { body: { stats_metric: m } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const [days, setDays] = useState(30);
  const [picked, setPicked] = useState("");
  const stored = settings.data?.stats_metric;
  const metric: Metric = METRICS.includes(stored as Metric) ? (stored as Metric) : "paragraphs";
  if (stats.isPending) return <main><p className="muted">Loading…</p></main>;
  if (stats.isError) return <main><p className="error" role="alert">{stats.error.message}</p></main>;
  const s = stats.data;
  const comp = s.comparisons[metric];
  const best = s.daily.reduce<typeof s.daily[number] | null>((b, d) => (!b || d[metric] > b[metric] ? d : b), null);
  const cutoff = new Date(`${s.today}T00:00:00Z`);
  cutoff.setUTCDate(cutoff.getUTCDate() - (days - 1));
  const recent = s.daily.filter((d) => d.date >= cutoff.toISOString().slice(0, 10)).reverse();
  const periods = [[`Today (${longDate(s.today)})`, "today"], ["Last 7 days", "week"], ["Last 30 days", "month"], ["All time", "alltime"]] as const;
  const avg = comp.daily_avg_30;
  return (
    <main>
      <h1>Statistics</h1>
      <label>Metric{" "}
        <select value={metric} onChange={(e) => saveMetric.mutate(e.target.value as Metric)}>
          {METRICS.map((m) => <option key={m} value={m}>{LABELS[m]}</option>)}
        </select>
      </label>
      <Heatmap today={s.today} daily={s.daily} metric={metric} onPick={setPicked} />
      <p className="muted">Less {COLORS.map((c) => <span key={c} style={{ display: "inline-block", width: 13, height: 13, background: c }} />)} More</p>
      <table>
        <thead><tr><th>Period</th><th>Paragraphs</th><th>Source Chars</th><th>EN Words</th><th>vs prev</th></tr></thead>
        <tbody>
          {periods.map(([label, key]) => (
            <tr key={key}>
              <td>{label}</td><td>{n(s.summary[key].paragraphs)}</td><td>{n(s.summary[key].chars)}</td>
              <td>{n(s.summary[key].en_words)}</td><td>{key === "alltime" ? "—" : pct(comp.periods[key]?.pct_change)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>Current streak: {s.streaks.current_streak} days · Longest streak: {s.streaks.longest_streak} days
        {best && best[metric] > 0 && <> · Best day: {longDate(best.date)} ({n(best[metric])} {UNITS[metric]})</>}</p>
      <p>Daily avg (30d): {avg < 10 ? avg.toFixed(1) : n(Math.round(avg))} {UNITS[metric]}</p>
      <button onClick={() => setDays(days === 30 ? 7 : 30)}>{days === 30 ? "Show Last 7 Days" : "Show Last 30 Days"}</button>
      <table>
        <thead><tr><th>Date</th><th>Paragraphs</th><th>Source Chars</th><th>EN Words</th></tr></thead>
        <tbody>
          {recent.map((d) => (
            <tr key={d.date} aria-selected={d.date === picked} className={d.date === picked ? "selected" : ""}>
              <td>{longDate(d.date)}</td><td>{n(d.paragraphs)}</td><td>{n(d.chars)}</td><td>{n(d.en_words)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>By series</h2>
      {s.series.length ? (
        <table>
          <thead><tr><th>Series</th><th>Paragraphs</th><th>Source Chars</th><th>EN Words</th><th>Chapters</th></tr></thead>
          <tbody>
            {s.series.map((r) => (
              <tr key={r.series_id}><td>{r.series}</td><td>{n(r.paragraphs)}</td><td>{n(r.chars)}</td><td>{n(r.en_words)}</td><td>{r.chapters}</td></tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No series data yet.</p>}
      {saveMetric.error && <p className="error" role="alert">{saveMetric.error.message}</p>}
    </main>
  );
}
```

  - In `web/src/styles.css` add `tr.selected { background: var(--highlight, #fff3b0); }` (check the file for an existing highlight variable and reuse it if there is one).
  - In `web/src/App.tsx` add `import StatsPage from "./stats/StatsPage";` and `<Route path="stats" element={<StatsPage />} />`; in `web/src/Shell.tsx` add `<NavLink to="/stats">Statistics</NavLink>` after Library.

- [ ] **Step 7: Type-check, test, build**
  - Run: `cd web && npm test && npm run build`
  - Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add web/src/stats web/src/App.tsx web/src/Shell.tsx web/src/styles.css web/src/api/schema.d.ts
git commit -m "feat(web): statistics page with heatmap, streaks and per-series table"
```

---

### Task 11: E2E — publish and statistics

**Files:**
- Create: `web/e2e/publish.spec.ts`, `web/e2e/stats.spec.ts`
- Modify: `tools/e2e_seed.py`, `web/playwright.config.ts`

**Interfaces:**
- Consumes: the whole phase.
- Produces: seed rows "E2E publish series" (slug/short title set) with chapter "Publish one" (order 1, translated), and "E2E stats series" with chapter "Stats one" (translated, `translated_at` = now).

- [ ] **Step 1: Seed** — in `tools/e2e_seed.py`, before `db.commit()`:

```python
        # publish spec: its own series, with the WordPress fields already set
        pub = Series(user_id=user.id, title="E2E publish series",
                     wp_series_slug="e2e-publish", wp_series_title_short="E2EP")
        db.add(pub)
        db.flush()
        one = Document(user_id=user.id, title="Publish one", chapter_title="Publish one",
                       series_id=pub.id, series_order=1)
        db.add(one)
        db.flush()
        write_lines(db, one.id, [{"line_number": 0, "prefix": "%", "raw_text": "公開します。",
                                  "translated_text": "We publish."}])
        # stats spec: one translated line today, in its own series
        st = Series(user_id=user.id, title="E2E stats series")
        db.add(st)
        db.flush()
        stats_doc = Document(user_id=user.id, title="Stats one", series_id=st.id, series_order=1)
        db.add(stats_doc)
        db.flush()
        write_lines(db, stats_doc.id, [{"line_number": 0, "prefix": "%", "raw_text": "統計です。",
                                        "translated_text": "Stats."}])
        db.execute(update(Line).where(Line.document_id == stats_doc.id)
                   .values(translated_at=func.now()))
```

  - Extend the imports inside `main()`: `from sqlalchemy import func, update` and `from api.models import Document, Line, Series`.

- [ ] **Step 2: Allow the fake WordPress on localhost** — in `web/playwright.config.ts`, add `TA_WP_ALLOW_PRIVATE_URLS: "true",` to the API server's `env`.

- [ ] **Step 3: Write `web/e2e/publish.spec.ts`**

```ts
import { expect, test } from "@playwright/test";
import http from "node:http";
import type { AddressInfo } from "node:net";

const received: Record<string, unknown>[] = [];
let server: http.Server;
let site = "";

test.beforeAll(async () => {
  server = http.createServer((req, res) => {
    const reply = (body: unknown) => { res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify(body)); };
    if (req.url?.startsWith("/wp-json/ta-publisher/v1/status")) return reply({ status: "not_found", post_url: null });
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      received.push(JSON.parse(raw));
      reply({ created: true, updated: false, page_url: `${site}/e2e-publish/e2e-publish-c1/`, post_url: `${site}/post/1/` });
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  site = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
test.afterAll(() => new Promise<void>((resolve) => server.close(() => resolve())));

test("configure WordPress, publish a chapter, see the badge", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));

  await page.getByRole("link", { name: "WordPress" }).click();
  await page.getByLabel("WordPress endpoint URL").fill(site);
  await page.getByLabel("WordPress API key").fill("e2e-plugin-key");
  await page.getByRole("button", { name: "Save connection" }).click();
  await expect(page.getByText(/Key saved/)).toBeVisible();
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText("Connected; WordPress accepted the API key.")).toBeVisible();

  await page.getByRole("link", { name: "Library" }).click();
  const row = page.getByRole("row").filter({ hasText: "Publish one" });
  await row.getByRole("button", { name: "Publish…" }).click();
  const dialog = page.getByRole("dialog", { name: "Publish to WordPress" });
  await expect(dialog.getByText("WP status: Not published")).toBeVisible();
  await dialog.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(dialog.getByText("Published!")).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(row.getByText(/^pub /)).toBeVisible();
  expect(received.at(-1)).toMatchObject({ series_slug: "e2e-publish", chapter_title: "E2EP Publish one", chapter_index: 1 });
});
```

- [ ] **Step 4: Write `web/e2e/stats.spec.ts`**

```ts
import { expect, test } from "@playwright/test";

test("statistics show today's work and the series breakdown", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("e2e@example.com");
  await page.getByLabel("Password").fill("e2e-password-123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"));
  await page.getByRole("link", { name: "Statistics" }).click();
  await expect(page.getByRole("img", { name: /Activity heatmap/ })).toBeVisible();
  await expect(page.getByText(/Current streak: [1-9]\d* days/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "E2E stats series" })).toBeVisible();
});
```

- [ ] **Step 5: Run the whole e2e suite**
  - Run (venv active with the mecab extra, Postgres up): `cd web && npm run e2e`
  - Expected: all specs PASS, the existing ones included.

- [ ] **Step 6: Commit**

```bash
git add tools/e2e_seed.py web/playwright.config.ts web/e2e/publish.spec.ts web/e2e/stats.spec.ts
git commit -m "test(e2e): publish to a fake WordPress; statistics page"
```

---

### Task 12: Docs and the full gate

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/superpowers/specs/2026-10-10-web-app-port-design.md`, `api/models/content.py` (comment only)

- [ ] **Step 1: CLAUDE.md** — replace the sentence "Phase 6b (WordPress publish, scheduling, statistics) is next." with:

```markdown
Phase 6b: publishing and statistics. WordPress config is a `wordpress` credential plus `wp_*` user settings
(`api/wp_prefs.py`); `api/publish.py` builds chapters and records results; single publish is a request with a
server-enforced re-publish 409 (`confirm_republish`), batch publish and volume illustrations are jobs
(`api/publish_job.py`). Every WordPress call passes `check_user_url` unless `TA_WP_ALLOW_PRIVATE_URLS=true`, and the
client never follows redirects. `GET /stats?tz=` buckets `lines.translated_at` in the viewer's IANA zone.
```

  - Under Architecture rules, extend the MT backends bullet's last sentence: "WordPress calls take an injected `httpx.Client` the same way (`http_client` seams in `api/routers/wp.py` and `api/publish_job.py`)."

- [ ] **Step 2: README** — add a `## WordPress publishing` section after `## Machine translation`:

```markdown
## WordPress publishing

Install the Translation Assistant Publisher plugin on the WordPress site, then enter its endpoint
(site URL or `…/wp-json/ta-publisher/v1/publish`) and API key under Settings → WordPress, and each
series' slug and short title on its series page. Publish one chapter from its picker row, or select
chapters and choose Publish to publish or schedule them as a job. Volumes have a Publish
illustrations button.

The endpoint may not resolve to a private or local address unless `TA_WP_ALLOW_PRIVATE_URLS=true`
(for a WordPress on the same network). The server never follows a redirect from WordPress; save the
address it redirects to instead. Images are downscaled (Pillow) to keep each request under the
~1 MB body limit some hosts enforce.
```

  - In the Machine translation section, next to `TA_MT_ALLOW_PRIVATE_URLS`, note that the WordPress endpoint has its own flag.

- [ ] **Step 3: Spec notes** — under §10, append:

```markdown
> Note (2026-10-13, phase 6b): one-chapter publish is a request; batch publish and volume
> illustrations are jobs. The re-publish safeguard is a server 409 unless confirmed. Statistics
> bucket days in the viewer's time zone (the desktop used UTC). WordPress dates live in
> `wp_published_at` (the publish time or the scheduled slot); `wp_post_id` stays NULL because the
> plugin returns no post id. `work_sessions` is still not written.
```

  - Under §9's 6a note, append: `> Note (2026-10-13): 6b adds the wp_publish and wp_illustrations jobs.`

- [ ] **Step 4: Model comment** — in `api/models/content.py`, replace the `wp_post_id` comment with:

```python
    # Reserved: the WordPress plugin's response carries page/post URLs but no post id,
    # so phase 6b leaves this NULL (plan ruling 9). wp_post_url is what it records.
```

- [ ] **Step 5: The full gate**
  - Run: `ruff check . && pytest -q; echo exit=$?`
  - Run: `cd web && npm test && npm run build && npm run e2e`
  - Run: `wc -l api/*.py api/core/*.py api/routers/*.py | sort -n | tail -5` — nothing over ~400.
  - Expected: all green, `exit=0`.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md README.md docs/superpowers/specs/2026-10-10-web-app-port-design.md api/models/content.py
git commit -m "docs: phase 6b publishing and statistics"
```

- [ ] **Step 7: Carry-overs** — record what is still open in the auto-memory as `phase6b-carryover.md` (with a pointer line in `MEMORY.md`): at least the publish request holding a pool connection (ruling 3), the SELECT-only batch 409 (ruling 14), and any item from the phase 4/5/6a carry-overs this plan did not touch.
