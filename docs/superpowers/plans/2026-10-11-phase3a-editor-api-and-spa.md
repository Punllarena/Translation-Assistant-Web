# Phase 3a — Editor API and SPA Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the editor its server side (line read/write with glossary substitution, spellcheck with per-profile custom words, inline images), put the app behind Caddy with TLS and a body cap, and stand up the Vite + React SPA with login, invite acceptance, the document picker, and the series/volume manager — so the library is usable in a browser and phase 3b only has to build the editor screen.

**Architecture:** Three new routers (`lines`, `spell`, `images`) built with `api_router()`. `replace_and_parse` is ported verbatim into `api/core/text.py`; the enchant wiring from the desktop `spellcheck.py` becomes `api/core/spell.py` (no Qt, no DB). Caddy serves the built SPA and reverse-proxies `/api/*` to uvicorn with the prefix stripped, so the API's own paths do not change. The SPA uses a typed client generated from the API's OpenAPI schema (`openapi-typescript` + `openapi-fetch`) and TanStack Query for server state.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL 16, pyenchant (new) with system `libenchant-2-2` + `hunspell-en-us`; Caddy 2; Node 24, Vite, React 19, TypeScript 5.9, react-router, @tanstack/react-query 5, openapi-fetch, openapi-typescript, vitest.

**Spec:** `docs/superpowers/specs/2026-10-10-web-app-port-design.md`. This plan implements the server half of §5 (editor) and the SPA half of §6 (library) that phase 2 deferred (phase 2 plan, deviation 1), plus the phase 3 deployment gate from §13 and the README ("TLS and a reverse proxy arrive with the SPA in phase 3"). Phase 3b (separate plan) builds the editor screen on these endpoints. Desktop reference: `../TranslationAssistant-PySide6-Port` at commit `f1a96ce`.

## Global Constraints

- Everything in the phase 1 and phase 2 plans' Global Constraints still applies: SQLAlchemy 2.0 style, tests against real Postgres, cross-user access is **404, never 403**, a bad id in a request *body* is **422 with one message** for missing and foreign, no Python module over ~400 lines, Conventional Commits, every task ends on a commit.
- Build every router with `api_router()`; handlers `flush()`, never `commit()`. `tests/test_commit_boundary.py` enforces it.
- Key-addressed stores are idempotent 204 on PUT/DELETE (CLAUDE.md "Delete semantics"); custom words are key-addressed by `(profile, word)`.
- `api/core/` holds Qt-free ported code with no database imports. Port verbatim.
- Use `status.HTTP_422_UNPROCESSABLE_CONTENT` / `status.HTTP_413_CONTENT_TOO_LARGE`.
- A test reading rows after an API call on the shared `db` session calls `db.expire_all()` first.
- **No React component file over ~300 lines** (spec §2).
- **Frontend dependencies are only:** `react`, `react-dom`, `react-router`, `@tanstack/react-query`, `openapi-fetch`; dev: `vite`, `@vitejs/plugin-react`, `typescript@~5.9`, `@types/react`, `@types/react-dom`, `openapi-typescript`, `vitest`. No UI kit, no drag-and-drop library (native HTML5 drag events), no CSS framework. `package-lock.json` is committed and CI uses `npm ci`.
- **vitest covers pure TypeScript modules only** (environment `node`). Components are verified by `npm run build` (typecheck) and the manual smoke steps given in each task. Playwright arrives in phase 3b with the editor flows the spec names.
- The SPA talks to the API only through `web/src/api/client.ts` at base URL `/api`. In dev, Vite proxies `/api` to `http://127.0.0.1:8000` with the prefix stripped; in production, Caddy does the same.

**Deviations from the spec, decided here:**

1. **Caddy serves the SPA, not FastAPI** (§13 says "api … serving the built SPA as static files"). The API's paths (`/documents/{id}`) and the SPA's routes would collide on a browser refresh; putting the API under `/api` in the proxy fixes that without renaming any route or touching phases 1–2. FastAPI serves only the API.
2. **`translated_at` follows the spec, not the desktop.** The desktop `save_translation` restamped `translated_at` on every edit, which moves a line's history to its last edit day. Here a save stamps it only when the line goes from empty to non-empty, clears it when the translation is emptied, and leaves it alone on an edit of a non-empty line.
3. **Spell spans are UTF-16 offsets.** Python indexes code points; a browser string indexes UTF-16 code units. The server converts, so the client can slice its own string with the offsets as given.
4. **The editor's profile** is the document's series profile, else the user's default profile, else the user's oldest profile, else none (empty glossary, default parse characters). `?profile_id=` overrides it, for the editor's profile switcher. This mirrors the desktop (`get_series_profile`, then the `profile_used` setting); the web app's "profile used" is the `is_default` flag.
5. **Playwright is phase 3b.** All three spec smoke flows open the editor.

## Review Focus

1. **A save batch that names a line number the document no longer has** (the chapter was split in another tab). Expect 422 and nothing written — not a partial save that drops some lines silently. (Task 2)
2. **A translation containing emoji or Japanese before a misspelled word.** The span must underline the misspelled word in the browser, not a few characters to its left. (Task 3)
3. **An illustration imported from a desktop `ta.db` that is not PNG/JPEG/GIF/WebP** (e.g. an SVG). It must be served as `application/octet-stream` with `nosniff`, never as `image/svg+xml`, which would run script in the app's origin. (Task 4)
4. **Logging in through Caddy.** The login limiter must key on the real client address, not Caddy's container address; otherwise five bad passwords from anyone lock out everyone. (Task 5)
5. **A session that expires while the picker is open.** The next request's 401 must take the user to the login screen and bring them back to where they were, not leave a stuck error or spinner. A crafted `?next=//evil.example` must not redirect off-site. (Task 6)

---

## File Structure

| File | Responsibility |
|---|---|
| `api/core/text.py` (modify) | Append the verbatim port of `replace_and_parse` |
| `api/core/spell.py` | Enchant dictionary loading, misspelling scan with UTF-16 offsets, suggestions |
| `api/schemas/lines.py` | `LineOut`, `DocumentLines`, `LineEdit`, `LineBatch` |
| `api/schemas/spell.py` | `SpellRequest`, `Misspelling`, `SpellResult` |
| `api/schemas/images.py` | `ImageOut`, `ImageUpdate` |
| `api/routers/lines.py` | `GET/PATCH /documents/{id}/lines`, editor profile resolution |
| `api/routers/spell.py` | `POST /spell/check`, `/profiles/{id}/words` |
| `api/routers/images.py` | `GET /documents/{id}/images`, `GET /images/{id}`, `PATCH /images/{id}` |
| `api/main.py` (modify) | Register the three routers |
| `pyproject.toml`, `Dockerfile`, `.github/workflows/ci.yml` (modify) | pyenchant + system dictionaries; web CI job |
| `web/Caddyfile`, `web/Dockerfile` | Caddy image with the built SPA; `/api` reverse proxy; body cap |
| `docker-compose.yml` (modify) | `caddy` service; `api` no longer published; secure cookies |
| `tools/dump_openapi.py` | Print the app's OpenAPI JSON (input to the generated client) |
| `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html` | Toolchain |
| `web/src/main.tsx`, `web/src/App.tsx`, `web/src/styles.css` | Entry, routes, shell |
| `web/src/api/schema.d.ts` | Generated; never edited by hand |
| `web/src/api/client.ts` | Typed client, `call()`, `ApiError`, `errorMessage()` |
| `web/src/auth/*` | `useMe`, `RequireAuth`, `Login`, `AcceptInvite`, `safeNext` |
| `web/src/library/group.ts`, `order.ts` | Pure picker grouping/filtering and list reordering (vitest) |
| `web/src/library/Picker.tsx`, `DocumentRow.tsx`, `NewDocument.tsx` | Picker screen |
| `web/src/library/SeriesPage.tsx`, `Volumes.tsx` | Series and volume manager |
| `tests/test_lines.py`, `tests/test_spell.py`, `tests/test_images.py`, `tests/test_core_text.py` (modify) | API tests |
| `README.md`, `CLAUDE.md` (modify) | Phase 3a status, running the SPA, Caddy deployment |

**Endpoint map (new):**

```
GET    /documents/{id}/lines?profile_id=   lines with display text and sentences, plus the profile used
PATCH  /documents/{id}/lines               {lines: [{line_number, translated_text}]}   204 · 422 unknown line
POST   /spell/check                        {texts, profile_id?} → spans per text
GET    /profiles/{id}/words                custom words, sorted
PUT    /profiles/{id}/words/{word}         204, idempotent
DELETE /profiles/{id}/words/{word}         204, idempotent
GET    /documents/{id}/images              metadata, by anchor
GET    /images/{id}                        bytes
PATCH  /images/{id}                        {exclude_export}
```

---

### Task 1: Port `replace_and_parse`

**Files:**
- Modify: `api/core/text.py` (append), `tests/test_core_text.py` (append)

**Interfaces:**
- Produces: `api.core.text.replace_and_parse(text: str, glossary: list[tuple[str, str]], parse_chars: list[str]) -> tuple[str, list[str], bool]` and `api.core.text.split_parse_chars(setting: str) -> list[str]`.

- [ ] **Step 1: Append the desktop tests to `tests/test_core_text.py`**

Copy `class TestReplaceAndParse` from `../TranslationAssistant-PySide6-Port/tests/test_core.py` (the `# replace_and_parse` section, lines ~243–292 at `f1a96ce`) verbatim; only the import moves to `from api.core.text import replace_and_parse`. Then add these, which pin the web app's use of it (the Japanese parse split and the settings split):

```python
from api.core.text import replace_and_parse, split_parse_chars


def test_replace_and_parse_strips_markers_and_applies_glossary():
    display, sentences, replaced = replace_and_parse(
        "%太郎は、走った。", [("太郎", "Taro")], ["、", "。"]
    )
    assert (display, sentences, replaced) == ("Taroは、走った。", ["Taroは", "走った"], True)


def test_replace_and_parse_without_a_match_is_not_replaced():
    assert replace_and_parse("$走った", [("太郎", "Taro")], []) == ("走った", ["走った"], False)


def test_replace_and_parse_blank_line():
    assert replace_and_parse("", [], ["。"]) == ("", [], False)


def test_replace_and_parse_ignores_empty_phrase():
    assert replace_and_parse("abc", [("", "x")], [])[2] is False


def test_split_parse_chars_matches_the_desktop_setting_split():
    assert split_parse_chars("、 。 ？ ！ 「 」 …… ") == ["、", "。", "？", "！", "「", "」", "……"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/test_core_text.py -k "replace_and_parse or split_parse" -v`
Expected: FAIL with `ImportError: cannot import name 'replace_and_parse'`

- [ ] **Step 3: Append the port to `api/core/text.py`**

Copy `replace_and_parse` from `../TranslationAssistant-PySide6-Port/translation_assistant/core.py` (lines 269–301 at `f1a96ce`) verbatim, docstring included. Then add the setting split, which the desktop does inline in `main_widget.py::_update_parse_chars`:

```python
def split_parse_chars(setting: str) -> list[str]:
    """A profile's parse_chars setting as a list (desktop main_widget._update_parse_chars)."""
    return [c for c in setting.split(" ") if c]
```

Update the module docstring's second sentence to: `Only the functions phases 2-3 use are here; later phases append theirs.`

- [ ] **Step 4: Run them to see them pass**

Run: `pytest tests/test_core_text.py -v && ruff check api/core`
Expected: all PASS, ruff clean

- [ ] **Step 5: Commit**

```bash
git add api/core/text.py tests/test_core_text.py
git commit -m "feat(core): port replace_and_parse for the editor"
```

---

### Task 2: Line read and save

**Files:**
- Create: `api/schemas/lines.py`, `api/routers/lines.py`, `tests/test_lines.py`
- Modify: `api/main.py`

**Interfaces:**
- Consumes: `replace_and_parse`, `split_parse_chars` (Task 1); `scoped`, `owned_ref` (`api/deps.py`); `DocumentOut` (`api/schemas/documents.py`); `ProfileOut` (`api/schemas/profiles.py`); `DEFAULT_PARSE_CHARS` (`api/schemas/profiles.py`).
- Produces:
  - `GET /documents/{document_id}/lines?profile_id=` → `DocumentLines {document: DocumentOut, profile: ProfileOut | null, lines: LineOut[]}`; `LineOut {line_number, prefix, raw_text, display_text, sentences: str[], replaced: bool, translated_text}`.
  - `PATCH /documents/{document_id}/lines` with `LineBatch {lines: LineEdit[]}`, `LineEdit {line_number: int, translated_text: str}` → 204.
  - `api.routers.lines.editor_profile(db, user_id, doc, profile_id) -> Profile | None`.

- [ ] **Step 1: Write the failing tests in `tests/test_lines.py`**

```python
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from api.models import Document, GlossaryEntry, Line, Profile


@pytest.fixture
def doc(me, make_doc):
    return make_doc(me, ["太郎は、走った。", "", "次"], translated=False)


def _profile(db, user, name="p", *, is_default=False, parse_chars="、 。", glossary=()):
    profile = Profile(user_id=user.id, name=name, is_default=is_default, parse_chars=parse_chars)
    db.add(profile)
    db.flush()
    db.add_all(
        GlossaryEntry(profile_id=profile.id, phrase=p, translation=t, sort_order=i)
        for i, (p, t) in enumerate(glossary)
    )
    db.flush()
    return profile


def _line(db, doc, n):
    db.expire_all()
    return db.scalar(select(Line).where(Line.document_id == doc.id, Line.line_number == n))


def _save(client, doc, *edits):
    body = {"lines": [{"line_number": n, "translated_text": t} for n, t in edits]}
    return client.patch(f"/documents/{doc.id}/lines", json=body)


def test_lines_use_the_default_profile_glossary(app_client, db, me, doc):
    _profile(db, me, is_default=True, glossary=[("太郎", "Taro")])
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["profile"]["name"] == "p"
    first = body["lines"][0]
    assert first["raw_text"] == "太郎は、走った。"
    assert (first["display_text"], first["sentences"], first["replaced"]) == (
        "Taroは、走った。", ["Taroは", "走った"], True
    )
    assert [line["line_number"] for line in body["lines"]] == [0, 1, 2]


def test_series_profile_wins_over_default(app_client, db, me, make_series, make_doc):
    _profile(db, me, "default", is_default=True, glossary=[("次", "Default")])
    series_profile = _profile(db, me, "series", glossary=[("次", "Series")])
    series = make_series(me)
    series.profile_id = series_profile.id
    doc = make_doc(me, ["次"], series=series)
    assert app_client.get(f"/documents/{doc.id}/lines").json()["lines"][0]["display_text"] == "Series"


def test_profile_id_query_overrides(app_client, db, me, doc):
    _profile(db, me, "default", is_default=True)
    other = _profile(db, me, "other", glossary=[("次", "Next")])
    body = app_client.get(f"/documents/{doc.id}/lines", params={"profile_id": other.id}).json()
    assert (body["profile"]["id"], body["lines"][2]["display_text"]) == (other.id, "Next")


def test_foreign_profile_id_query_is_422(app_client, db, me, make_user, doc):
    theirs = _profile(db, make_user(email="other@example.com"))
    r = app_client.get(f"/documents/{doc.id}/lines", params={"profile_id": theirs.id})
    assert (r.status_code, r.json()["detail"]) == (422, "profile_id: no such item")


def test_no_profile_uses_default_parse_chars(app_client, doc):
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["profile"] is None
    assert body["lines"][0]["sentences"] == ["太郎は", "走った"]


def test_save_stamps_translated_at_only_from_empty(app_client, db, doc):
    assert _save(app_client, doc, (0, "Taro ran.")).status_code == 204
    first = _line(db, doc, 0).translated_at
    assert first is not None and _line(db, doc, 0).translated_text == "Taro ran."
    assert _save(app_client, doc, (0, "Taro ran off.")).status_code == 204
    assert _line(db, doc, 0).translated_at == first  # an edit keeps the history


def test_clearing_a_translation_clears_translated_at(app_client, db, doc):
    _save(app_client, doc, (0, "Taro ran."))
    _save(app_client, doc, (0, ""))
    assert (_line(db, doc, 0).translated_text, _line(db, doc, 0).translated_at) == ("", None)


def test_save_bumps_document_updated_at(app_client, db, doc):
    doc.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
    db.flush()
    _save(app_client, doc, (2, "Next"))
    db.expire_all()
    assert db.get(Document, doc.id).updated_at.year > 2000


def test_unknown_line_number_is_422_and_writes_nothing(app_client, db, doc):
    r = _save(app_client, doc, (0, "Taro ran."), (99, "ghost"))
    assert (r.status_code, r.json()["detail"]) == (422, "line_number: no such line (99)")
    assert _line(db, doc, 0).translated_text == ""


def test_duplicate_line_number_in_batch_is_422(app_client, doc):
    assert _save(app_client, doc, (0, "a"), (0, "b")).status_code == 422


def test_empty_batch_is_422(app_client, doc):
    assert app_client.patch(f"/documents/{doc.id}/lines", json={"lines": []}).status_code == 422


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [("get", {}), ("patch", {"json": {"lines": [{"line_number": 0, "translated_text": "x"}]}})],
)
def test_another_users_lines_are_404(app_client, me, make_user, make_doc, method, kwargs):
    theirs = make_doc(make_user(email="other@example.com"), ["x"])
    r = getattr(app_client, method)(f"/documents/{theirs.id}/lines", **kwargs)
    assert r.status_code == 404
```

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/test_lines.py -v`
Expected: FAIL (404 for every request — no route)

- [ ] **Step 3: Write `api/schemas/lines.py`**

```python
from pydantic import BaseModel, Field

from api.schemas.documents import DocumentOut
from api.schemas.profiles import ProfileOut

# A pasted translation for one paragraph; generous, but bounded.
MAX_TRANSLATION_CHARS = 100_000


class LineOut(BaseModel):
    line_number: int
    prefix: str
    raw_text: str
    display_text: str  # raw_text with markers stripped and the glossary applied
    sentences: list[str]  # display_text split on the profile's parse characters
    replaced: bool  # whether the glossary changed anything
    translated_text: str


class DocumentLines(BaseModel):
    document: DocumentOut
    profile: ProfileOut | None
    lines: list[LineOut]


class LineEdit(BaseModel):
    line_number: int = Field(ge=0, le=2**31 - 1)
    translated_text: str = Field(max_length=MAX_TRANSLATION_CHARS)


class LineBatch(BaseModel):
    # The client flushes its dirty set; a few thousand covers any real chapter.
    lines: list[LineEdit] = Field(min_length=1, max_length=5000)
```

- [ ] **Step 4: Write `api/routers/lines.py`**

```python
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from api.core.text import replace_and_parse, split_parse_chars
from api.deps import current_user, db_session, owned_ref, scoped
from api.models import Document, GlossaryEntry, Line, Profile, Series, User
from api.routing import api_router
from api.schemas.lines import DocumentLines, LineBatch, LineOut
from api.schemas.profiles import DEFAULT_PARSE_CHARS

router = api_router(tags=["lines"])


def editor_profile(
    db: Session, user_id: int, doc: Document, profile_id: int | None
) -> Profile | None:
    """The profile whose glossary and parse characters the editor uses: an explicit
    choice, else the series' profile, else the default, else the oldest, else none."""
    if profile_id is not None:
        return owned_ref(db, Profile, profile_id, user_id, "profile_id")
    if doc.series_id is not None:
        series = db.get(Series, doc.series_id)
        if series.profile_id is not None:
            return db.get(Profile, series.profile_id)
    return db.scalar(
        select(Profile)
        .where(Profile.user_id == user_id)
        .order_by(Profile.is_default.desc(), Profile.id)
        .limit(1)
    )


@router.get("/documents/{document_id}/lines", response_model=DocumentLines)
def get_lines(
    document_id: int,
    profile_id: int | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> DocumentLines:
    doc = scoped(db, Document, document_id, user.id)
    profile = editor_profile(db, user.id, doc, profile_id)
    glossary: list[tuple[str, str]] = []
    if profile is not None:
        glossary = [
            tuple(row)
            for row in db.execute(
                select(GlossaryEntry.phrase, GlossaryEntry.translation)
                .where(GlossaryEntry.profile_id == profile.id)
                .order_by(GlossaryEntry.sort_order, GlossaryEntry.id)
            )
        ]
    parse_chars = split_parse_chars(profile.parse_chars if profile else DEFAULT_PARSE_CHARS)
    lines = []
    for line in db.scalars(
        select(Line).where(Line.document_id == doc.id).order_by(Line.line_number)
    ):
        display, sentences, replaced = replace_and_parse(line.raw_text, glossary, parse_chars)
        lines.append(
            LineOut(
                line_number=line.line_number,
                prefix=line.prefix,
                raw_text=line.raw_text,
                display_text=display,
                sentences=sentences,
                replaced=replaced,
                translated_text=line.translated_text,
            )
        )
    return DocumentLines(document=doc, profile=profile, lines=lines)


@router.patch("/documents/{document_id}/lines", status_code=status.HTTP_204_NO_CONTENT)
def save_lines(
    document_id: int,
    body: LineBatch,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> None:
    """Write the client's dirty lines in one statement. translated_at is stamped when a
    line goes from empty to translated, cleared when it is emptied, and kept on an edit,
    so the statistics heatmap counts the day a line was first translated."""
    doc = scoped(db, Document, document_id, user.id)
    edits = {edit.line_number: edit.translated_text for edit in body.lines}
    if len(edits) != len(body.lines):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "line_number: listed more than once"
        )
    current = {
        number: (line_id, old)
        for number, line_id, old in db.execute(
            select(Line.line_number, Line.id, Line.translated_text).where(
                Line.document_id == doc.id, Line.line_number.in_(edits)
            )
        )
    }
    missing = sorted(set(edits) - set(current))
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"line_number: no such line ({', '.join(map(str, missing))})",
        )
    now = datetime.now(UTC)
    rows = []
    for number, text in edits.items():
        line_id, old = current[number]
        row = {"id": line_id, "translated_text": text}
        if not text:
            row["translated_at"] = None
        elif not old:
            row["translated_at"] = now
        rows.append(row)
    # Rows differ in which columns they set, so group them: one executemany per shape.
    for keys in {tuple(sorted(r)) for r in rows}:
        db.execute(update(Line), [r for r in rows if tuple(sorted(r)) == keys])
    doc.updated_at = func.now()
    db.flush()
```

- [ ] **Step 5: Register the router in `api/main.py`**

Add `lines` to the `from api.routers import (...)` list (alphabetical) and, after `app.include_router(volumes.router)`:

```python
    app.include_router(lines.router)
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_lines.py tests/test_commit_boundary.py -v && ruff check .`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add api/schemas/lines.py api/routers/lines.py api/main.py tests/test_lines.py
git commit -m "feat(lines): editor line read with glossary display and batched save"
```

---

### Task 3: Spellcheck and custom words

**Files:**
- Create: `api/core/spell.py`, `api/schemas/spell.py`, `api/routers/spell.py`, `tests/test_spell.py`
- Modify: `api/main.py`, `pyproject.toml`, `Dockerfile`, `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `owned_ref`, `scoped`; `CustomWord`, `Profile` models.
- Produces:
  - `api.core.spell.dictionary() -> object | None` (cached; `check(word) -> bool`, `suggest(word) -> list[str]`), `misspellings(text, custom, d) -> list[tuple[int, int, str]]` (UTF-16 offsets), `suggest(d, word) -> list[str]`.
  - `POST /spell/check` `SpellRequest {texts: str[], profile_id?: int}` → `SpellResult {available: bool, results: Misspelling[][]}`, `Misspelling {start, end, word, suggestions}`.
  - `GET /profiles/{id}/words` → `str[]`; `PUT|DELETE /profiles/{id}/words/{word}` → 204.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml` `dependencies`, add `"pyenchant>=3.2",`. Install: `pip install -e ".[dev]"`. For a local real dictionary (optional; tests do not need one): `sudo apt-get install -y libenchant-2-2 hunspell-en-us`.

In `Dockerfile`, before `WORKDIR /app`:

```dockerfile
# Spellcheck: enchant with the hunspell en_US dictionary (spec §5).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libenchant-2-2 hunspell-en-us \
 && rm -rf /var/lib/apt/lists/*
```

In `.github/workflows/ci.yml`, before `- run: pip install -e ".[dev]"`:

```yaml
      - run: sudo apt-get update && sudo apt-get install -y libenchant-2-2 hunspell-en-us
```

- [ ] **Step 2: Write the failing tests in `tests/test_spell.py`**

```python
import pytest

from api.core import spell
from api.models import CustomWord, Profile


class FakeDict:
    WORDS = {"the", "cat", "sat"}

    def check(self, word):
        return word.lower() in self.WORDS

    def suggest(self, word):
        return ["the", "then", "they", "them", "theme", "there"] if word == "teh" else []


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(spell, "dictionary", lambda: FakeDict())


@pytest.fixture
def profile(db, me):
    p = Profile(user_id=me.id, name="p")
    db.add(p)
    db.flush()
    return p


def check(client, *texts, profile_id=None):
    return client.post("/spell/check", json={"texts": list(texts), "profile_id": profile_id})


def test_misspellings_are_utf16_offsets():
    # 😀 is two UTF-16 code units, 日本 two; "teh" starts at 2 + 1 + 2 + 1 = 6 in JS.
    text = "😀 日本 teh cat"
    assert spell.misspellings(text, set(), FakeDict()) == [(6, 9, "teh")]
    assert text.encode("utf-16-le")[12:18].decode("utf-16-le") == "teh"


def test_check_returns_spans_and_capped_suggestions(app_client, me, fake):
    body = check(app_client, "teh cat", "the cat sat").json()
    assert body["available"] is True
    assert body["results"] == [
        [{"start": 0, "end": 3, "word": "teh",
          "suggestions": ["the", "then", "they", "them", "theme"]}],
        [],
    ]


def test_custom_words_are_not_flagged(app_client, db, me, fake, profile):
    db.add(CustomWord(profile_id=profile.id, word="Taro"))
    db.flush()
    body = check(app_client, "Taro sat", profile_id=profile.id).json()
    assert body["results"] == [[]]


def test_unavailable_dictionary_flags_nothing(app_client, me, monkeypatch):
    monkeypatch.setattr(spell, "dictionary", lambda: None)
    assert check(app_client, "teh").json() == {"available": False, "results": [[]]}


def test_foreign_profile_is_422(app_client, db, me, make_user, fake):
    theirs = Profile(user_id=make_user(email="other@example.com").id, name="x")
    db.add(theirs)
    db.flush()
    r = check(app_client, "teh", profile_id=theirs.id)
    assert (r.status_code, r.json()["detail"]) == (422, "profile_id: no such item")


def test_text_count_is_capped(app_client, me, fake):
    assert check(app_client, *(["x"] * 201)).status_code == 422


def test_words_put_is_idempotent_and_case_insensitive(app_client, profile):
    url = f"/profiles/{profile.id}/words"
    assert app_client.put(f"{url}/Taro").status_code == 204
    assert app_client.put(f"{url}/taro").status_code == 204
    assert app_client.get(url).json() == ["Taro"]


def test_words_delete_is_idempotent(app_client, profile):
    url = f"/profiles/{profile.id}/words"
    app_client.put(f"{url}/Taro")
    assert app_client.delete(f"{url}/Taro").status_code == 204
    assert app_client.delete(f"{url}/Taro").status_code == 204
    assert app_client.get(url).json() == []


def test_word_with_whitespace_is_422(app_client, profile):
    assert app_client.put(f"/profiles/{profile.id}/words/two%20words").status_code == 422


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_another_users_profile_words_are_404(app_client, db, me, make_user, method):
    theirs = Profile(user_id=make_user(email="other@example.com").id, name="x")
    db.add(theirs)
    db.flush()
    url = f"/profiles/{theirs.id}/words" + ("" if method == "get" else "/Taro")
    assert getattr(app_client, method)(url).status_code == 404


def test_real_enchant_when_installed():
    d = spell.dictionary()
    if d is None:
        pytest.skip("enchant or an English dictionary is not installed")
    assert spell.misspellings("the cat sta", set(), d) == [(8, 11, "sta")]
```

- [ ] **Step 3: Run them to see them fail**

Run: `pytest tests/test_spell.py -v`
Expected: FAIL with `ImportError: cannot import name 'spell' from 'api.core'`

- [ ] **Step 4: Write `api/core/spell.py`**

```python
"""Server-side spellcheck: the desktop SpellHighlighter's enchant wiring
(translation_assistant/spellcheck.py at f1a96ce) without Qt. No database imports;
the caller passes the profile's custom words."""

import re
from functools import cache

_WORD_RE = re.compile(r"\b[A-Za-z']{2,}\b")
MAX_SUGGESTIONS = 5


@cache
def dictionary(lang: str = "en_US"):
    """An enchant dictionary, or None when enchant or every English dictionary is
    missing — spellcheck then degrades to flagging nothing, as on the desktop."""
    try:
        import enchant
    except (ImportError, OSError):
        return None
    for candidate in (lang, "en_US", "en_GB", "en_CA", "en"):
        try:
            return enchant.Dict(candidate)
        except Exception:
            continue
    return None


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def misspellings(text: str, custom: set[str], d) -> list[tuple[int, int, str]]:
    """(start, end, word) for each misspelled word, in UTF-16 code units — the offsets a
    browser string uses, so the client can slice with them as given."""
    found = []
    offset, prev = 0, 0
    for m in _WORD_RE.finditer(text):
        offset += _utf16_len(text[prev : m.start()])
        prev = m.start()
        word = m.group()
        if word in custom:
            continue
        try:
            ok = bool(d.check(word))
        except Exception:
            ok = True  # the desktop treats a dictionary error as "spelled correctly"
        if not ok:
            found.append((offset, offset + len(word), word))  # the word is ASCII
    return found


def suggest(d, word: str) -> list[str]:
    try:
        return list(d.suggest(word))[:MAX_SUGGESTIONS]
    except Exception:
        return []
```

- [ ] **Step 5: Write `api/schemas/spell.py`**

```python
from typing import Annotated

from pydantic import BaseModel, Field

# The client batches the visible cards; 200 covers a tall screen with room to spare.
MAX_TEXTS = 200
MAX_TEXT_CHARS = 100_000


class SpellRequest(BaseModel):
    texts: list[Annotated[str, Field(max_length=MAX_TEXT_CHARS)]] = Field(max_length=MAX_TEXTS)
    profile_id: int | None = None


class Misspelling(BaseModel):
    start: int  # UTF-16 code units
    end: int
    word: str
    suggestions: list[str]


class SpellResult(BaseModel):
    available: bool
    results: list[list[Misspelling]]
```

- [ ] **Step 6: Write `api/routers/spell.py`**

```python
from typing import Annotated

from fastapi import Depends, Path, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.core import spell
from api.deps import current_user, db_session, owned_ref, scoped
from api.models import CustomWord, Profile, User
from api.routing import api_router
from api.schemas.spell import Misspelling, SpellRequest, SpellResult

router = api_router(tags=["spell"])

# A dictionary word: no whitespace or slash, at most the column width.
Word = Annotated[str, Path(min_length=1, max_length=120, pattern=r"^[^\s/]+$")]


@router.post("/spell/check", response_model=SpellResult)
def check(
    body: SpellRequest, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> SpellResult:
    custom: set[str] = set()
    if body.profile_id is not None:
        profile = owned_ref(db, Profile, body.profile_id, user.id, "profile_id")
        custom = set(db.scalars(select(CustomWord.word).where(CustomWord.profile_id == profile.id)))
    d = spell.dictionary()
    if d is None:
        return SpellResult(available=False, results=[[] for _ in body.texts])
    suggestions: dict[str, list[str]] = {}  # suggest() is the slow call; once per word
    results = []
    for text in body.texts:
        spans = []
        for start, end, word in spell.misspellings(text, custom, d):
            if word not in suggestions:
                suggestions[word] = spell.suggest(d, word)
            spans.append(Misspelling(start=start, end=end, word=word, suggestions=suggestions[word]))
        results.append(spans)
    return SpellResult(available=True, results=results)


@router.get("/profiles/{profile_id}/words", response_model=list[str])
def list_words(
    profile_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[str]:
    profile = scoped(db, Profile, profile_id, user.id)
    return list(
        db.scalars(
            select(CustomWord.word)
            .where(CustomWord.profile_id == profile.id)
            .order_by(func.lower(CustomWord.word))
        )
    )


@router.put("/profiles/{profile_id}/words/{word}", status_code=status.HTTP_204_NO_CONTENT)
def add_word(
    profile_id: int,
    word: Word,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> None:
    """Idempotent: a word already present in any letter case is left as it is."""
    profile = scoped(db, Profile, profile_id, user.id)
    db.execute(
        insert(CustomWord).values(profile_id=profile.id, word=word).on_conflict_do_nothing()
    )


@router.delete("/profiles/{profile_id}/words/{word}", status_code=status.HTTP_204_NO_CONTENT)
def remove_word(
    profile_id: int,
    word: Word,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> None:
    profile = scoped(db, Profile, profile_id, user.id)
    db.execute(
        delete(CustomWord).where(
            CustomWord.profile_id == profile.id, func.lower(CustomWord.word) == word.lower()
        )
    )
```

Register in `api/main.py`: add `spell` to the import list and `app.include_router(spell.router)` after `lines`.

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_spell.py tests/test_commit_boundary.py -v && ruff check .`
Expected: all PASS (`test_real_enchant_when_installed` SKIPPED where enchant is absent; it runs in CI)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml Dockerfile .github/workflows/ci.yml api/core/spell.py \
  api/schemas/spell.py api/routers/spell.py api/main.py tests/test_spell.py
git commit -m "feat(spell): server spellcheck with UTF-16 spans and per-profile custom words"
```

---

### Task 4: Inline images

**Files:**
- Create: `api/schemas/images.py`, `api/routers/images.py`, `tests/test_images.py`
- Modify: `api/main.py`

**Interfaces:**
- Consumes: `scoped`; `sniff_image` (`api/uploads.py`); `Patch` (`api/schemas/common.py`).
- Produces: `GET /documents/{id}/images` → `ImageOut[]` (`{id, document_id, anchor_position, is_cover, exclude_export, src_path}`), `GET /images/{id}` → bytes, `PATCH /images/{id}` `ImageUpdate {exclude_export: bool}` → `ImageOut`.

- [ ] **Step 1: Write the failing tests in `tests/test_images.py`**

```python
import pytest

from api.models import DocumentImage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.fixture
def doc(me, make_doc):
    return make_doc(me, ["a", "b"])


def _image(db, doc, data=PNG, anchor=0, **kw):
    image = DocumentImage(
        document_id=doc.id, anchor_position=anchor, src_path="i.png", data=data, **kw
    )
    db.add(image)
    db.flush()
    return image


def test_list_is_ordered_by_anchor_without_bytes(app_client, db, doc):
    late, early = _image(db, doc, anchor=2), _image(db, doc, anchor=1)
    body = app_client.get(f"/documents/{doc.id}/images").json()
    assert [i["id"] for i in body] == [early.id, late.id]
    assert "data" not in body[0]


def test_get_serves_bytes_with_sniffed_type(app_client, db, doc):
    r = app_client.get(f"/images/{_image(db, doc).id}")
    assert (r.status_code, r.content, r.headers["content-type"]) == (200, PNG, "image/png")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "private" in r.headers["cache-control"]


def test_unrecognised_image_is_never_served_as_svg(app_client, db, doc):
    r = app_client.get(f"/images/{_image(db, doc, data=SVG).id}")
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_patch_exclude_export(app_client, db, doc):
    image = _image(db, doc)
    r = app_client.patch(f"/images/{image.id}", json={"exclude_export": True})
    assert (r.status_code, r.json()["exclude_export"]) == (200, True)


def test_patch_null_is_422(app_client, db, doc):
    image = _image(db, doc)
    assert app_client.patch(f"/images/{image.id}", json={"exclude_export": None}).status_code == 422


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/documents/{doc}/images", {}),
        ("get", "/images/{image}", {}),
        ("patch", "/images/{image}", {"json": {"exclude_export": True}}),
    ],
)
def test_another_users_images_are_404(
    app_client, db, me, make_user, make_doc, method, path, kwargs
):
    theirs = make_doc(make_user(email="other@example.com"), ["x"])
    image = _image(db, theirs)
    url = path.format(doc=theirs.id, image=image.id)
    assert getattr(app_client, method)(url, **kwargs).status_code == 404
```

- [ ] **Step 2: Run them to see them fail**

Run: `pytest tests/test_images.py -v`
Expected: FAIL (404 — no routes)

- [ ] **Step 3: Write `api/schemas/images.py`**

```python
from pydantic import BaseModel, ConfigDict

from api.schemas.common import Patch


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    anchor_position: int
    is_cover: bool
    exclude_export: bool
    src_path: str


class ImageUpdate(Patch):
    exclude_export: bool | None = None
```

- [ ] **Step 4: Write `api/routers/images.py`**

```python
from fastapi import Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, scoped
from api.models import Document, DocumentImage, User
from api.routing import api_router
from api.schemas.images import ImageOut, ImageUpdate
from api.uploads import sniff_image

router = api_router(tags=["images"])

MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


def scoped_image(db: Session, image_id: int, user_id: int) -> DocumentImage:
    """An image is owned through its document; 404 for missing and foreign alike."""
    image = db.scalar(
        select(DocumentImage)
        .join(Document)
        .where(DocumentImage.id == image_id, Document.user_id == user_id)
    )
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return image


@router.get("/documents/{document_id}/images", response_model=list[ImageOut])
def list_images(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[DocumentImage]:
    doc = scoped(db, Document, document_id, user.id)
    return list(
        db.scalars(
            select(DocumentImage)
            .where(DocumentImage.document_id == doc.id)
            .order_by(DocumentImage.anchor_position, DocumentImage.id)
        )
    )


@router.get("/images/{image_id}", response_class=Response)
def get_image(
    image_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Response:
    """The image bytes. The type comes from the bytes, and anything that is not a known
    raster format is served as an opaque download, so an imported SVG can never run
    script in the app's origin. An image row's bytes never change (a new cover is a new
    row), so the browser may cache it for good."""
    image = scoped_image(db, image_id, user.id)
    return Response(
        content=image.data,
        media_type=MEDIA_TYPES.get(sniff_image(image.data), "application/octet-stream"),
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/images/{image_id}", response_model=ImageOut)
def update_image(
    image_id: int,
    body: ImageUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> DocumentImage:
    image = scoped_image(db, image_id, user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(image, field, value)
    db.flush()
    return image
```

Register in `api/main.py`: add `images` to the import list and `app.include_router(images.router)` after `spell`.

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_images.py tests/test_commit_boundary.py -v && ruff check .`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add api/schemas/images.py api/routers/images.py api/main.py tests/test_images.py
git commit -m "feat(images): list, serve, and exclude-from-export for chapter images"
```

---

### Task 5: SPA scaffold, generated client, and Caddy

**Files:**
- Create: `tools/dump_openapi.py`, `web/package.json`, `web/package-lock.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/styles.css`, `web/src/api/schema.d.ts` (generated), `web/src/api/client.ts`, `web/Caddyfile`, `web/Dockerfile`, `web/.dockerignore`
- Modify: `docker-compose.yml`, `.gitignore`, `.github/workflows/ci.yml`, `README.md`

**Interfaces:**
- Consumes: the whole API's OpenAPI schema.
- Produces:
  - `web/src/api/client.ts`: `api` (an `openapi-fetch` client typed by `paths`), `call<T>(p) -> Promise<T>`, `class ApiError extends Error { status: number }`, `errorMessage(body: unknown) -> string`, and the type re-export `Schemas = components["schemas"]`.
  - `web/src/App.tsx`: the route table later tasks add to.
  - npm scripts: `dev`, `build` (typecheck + bundle), `test` (vitest), `gen:api`.

- [ ] **Step 1: Write `tools/dump_openapi.py`**

```python
"""Print the API's OpenAPI schema; web/ generates its typed client from it.

    python -m tools.dump_openapi > web/openapi.json
"""

import json

from api.main import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=2, sort_keys=True))
```

- [ ] **Step 2: Create the web package**

```bash
mkdir -p web/src/api && cd web
npm init -y
npm install react react-dom react-router @tanstack/react-query openapi-fetch
npm install -D vite @vitejs/plugin-react typescript@~5.9 @types/react @types/react-dom \
  openapi-typescript vitest
```

Then replace the `scripts` block of `web/package.json` (and set `"private": true`, `"type": "module"`, delete `main`):

```json
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "gen:api": "cd .. && python -m tools.dump_openapi > web/openapi.json && cd web && openapi-typescript openapi.json -o src/api/schema.d.ts"
  },
```

- [ ] **Step 3: Write `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`**

```ts
// web/vite.config.ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Same shape as Caddy in production: /api/* reaches uvicorn without the prefix.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: { environment: "node" },
});
```

If `tsc` rejects the `test` key, add `/// <reference types="vitest/config" />` as the first line.

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src", "vite.config.ts"]
}
```

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Translation Assistant</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Generate the client types**

With the venv active and `TA_SECRET_KEY` exported: `cd web && npm run gen:api`. Expected: `web/src/api/schema.d.ts` exists and contains `"/documents/{document_id}/lines"`. Add to `.gitignore`:

```
node_modules/
web/openapi.json
```

(`dist/` is already ignored.)

- [ ] **Step 5: Write `web/src/api/client.ts`**

```ts
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export const api = createClient<paths>({ baseUrl: "/api" });

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI's error body as one readable line: a string detail, or its validation list. */
export function errorMessage(body: unknown): string {
  const detail = (body as { detail?: unknown } | null | undefined)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const where = (d.loc ?? []).slice(1).join(".");
        return where ? `${where}: ${d.msg}` : String(d.msg);
      })
      .join("; ");
  }
  return "request failed";
}

/** Await an openapi-fetch call: its data, or an ApiError carrying the status. */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok) throw new ApiError(response.status, errorMessage(error));
  return data as T;
}
```

- [ ] **Step 6: Write `web/src/main.tsx`, `web/src/App.tsx`, `web/src/styles.css`**

```tsx
// web/src/main.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
```

```tsx
// web/src/App.tsx
import { Route, Routes } from "react-router";

export default function App() {
  return (
    <Routes>
      <Route path="*" element={<p>Translation Assistant</p>} />
    </Routes>
  );
}
```

```css
/* web/src/styles.css */
:root {
  color-scheme: light dark;
  font-family: system-ui, sans-serif;
  line-height: 1.5;
}
body { margin: 0; }
main { max-width: 72rem; margin: 0 auto; padding: 1rem; }
header.app { display: flex; gap: 1rem; align-items: center; padding: 0.5rem 1rem;
  border-bottom: 1px solid color-mix(in srgb, currentColor 20%, transparent); }
header.app nav { display: flex; gap: 1rem; flex: 1; }
table { border-collapse: collapse; width: 100%; }
td, th { padding: 0.25rem 0.5rem; text-align: left; }
.error { color: #c62828; }
.muted { opacity: 0.7; }
.toolbar { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; margin: 0.5rem 0; }
form.stack { display: grid; gap: 0.5rem; max-width: 24rem; }
```

- [ ] **Step 7: Build it**

Run: `cd web && npm run build`
Expected: `tsc` passes, `dist/` produced.

- [ ] **Step 8: Write the Caddy image**

```
# web/Caddyfile
{$TA_SITE_ADDRESS:localhost} {
	encode zstd gzip

	# Uploads are capped again in the API (10 MiB images, 5 MiB text) after the body
	# is received; this stops a larger body before it reaches uvicorn at all.
	request_body {
		max_size 12MB
	}

	handle_path /api/* {
		reverse_proxy api:8000
	}

	handle {
		root * /srv
		try_files {path} /index.html
		file_server
	}
}
```

```dockerfile
# web/Dockerfile
FROM node:24-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv
```

```
# web/.dockerignore
node_modules
dist
```

The generated `src/api/schema.d.ts` is committed, so the image build needs no Python.

- [ ] **Step 9: Put Caddy in front in `docker-compose.yml`**

Replace the `api` service's `environment` and `ports`, and add `caddy`:

```yaml
  api:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      TA_SECRET_KEY: ${TA_SECRET_KEY:?set TA_SECRET_KEY in .env}
      TA_DATABASE_URL: postgresql+psycopg://ta:ta@postgres:5432/ta
    # Not published: only Caddy reaches it, which is what makes trusting
    # X-Forwarded-For (--forwarded-allow-ips in the Dockerfile) safe.
    expose: ["8000"]

  caddy:
    build: ./web
    depends_on: [api]
    environment:
      TA_SITE_ADDRESS: ${TA_SITE_ADDRESS:-localhost}
    ports: ["80:80", "443:443"]
    volumes: ["caddy_data:/data"]
```

and under `volumes:` add `caddy_data:`. `TA_COOKIE_SECURE` is no longer set, so it takes its default, `true`: everything now arrives over HTTPS.

In the root `Dockerfile`, change the uvicorn command so it trusts the forwarded client address from Caddy (Caddy is a different container, so the default trusted address, 127.0.0.1, never matches and every login would be keyed to Caddy's address):

```dockerfile
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
```

and replace the comment above it with:

```dockerfile
# --proxy-headers --forwarded-allow-ips='*': the login limiter keys on the real client
# address from Caddy's X-Forwarded-For. Safe only because compose does not publish
# this port; Caddy is the only client.
```

- [ ] **Step 10: Add the web CI job to `.github/workflows/ci.yml`**

Append a second job, and in the existing `test` job add after `- run: pytest -q`:

```yaml
      - name: Generated client is current
        run: |
          python -m tools.dump_openapi > web/openapi.json
          cd web && npx --yes openapi-typescript@7 openapi.json -o src/api/schema.d.ts
          git diff --exit-code src/api/schema.d.ts
```

```yaml
  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - run: npm test -- --passWithNoTests
      - run: npm run build
      - run: docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2 caddy validate --config /etc/caddy/Caddyfile
```

Replace the `npx --yes openapi-typescript@7` with the exact version in `web/package-lock.json` so CI and local generation agree.

- [ ] **Step 11: Smoke the stack**

```bash
docker compose up -d --build
curl -sk https://localhost/api/healthz          # {"status":"ok"}
curl -sk -o /dev/null -w '%{http_code}\n' https://localhost/library   # 200 (index.html)
head -c 13000000 /dev/zero | curl -sk -o /dev/null -w '%{http_code}\n' \
  -X POST --data-binary @- https://localhost/api/documents/import/txt   # 413 from Caddy
curl -sk -o /dev/null https://localhost/api/healthz
docker compose logs api | tail -3
docker compose exec caddy hostname -i
```

Expected: health OK; a deep link answers with the SPA; the 13 MB body is a 413 without reaching the API. The client address in uvicorn's access log is the host's address on the compose network (the `.1` gateway, e.g. `172.18.0.1`), **not** the address `hostname -i` prints for the Caddy container — that is what proves the limiter keys on clients. Then `docker compose down`.

- [ ] **Step 12: Update `README.md`**

Replace the "Container" section with:

````markdown
## Container

```bash
docker compose up --build        # needs TA_SECRET_KEY in .env or the environment
```

Caddy serves the SPA and proxies `/api/*` to the API (prefix stripped) at
`https://$TA_SITE_ADDRESS` (default `localhost`, with Caddy's internal CA). Set
`TA_SITE_ADDRESS` to a public hostname and Caddy obtains a certificate for it. Caddy caps
request bodies at 12 MB. The API container is not published; uvicorn trusts the
forwarded client address because Caddy is its only client.

## Web app (development)

```bash
uvicorn api.main:app --reload                 # API on 127.0.0.1:8000 (TA_COOKIE_SECURE=false)
cd web && npm install && npm run dev          # SPA on http://localhost:5173, /api proxied
npm run gen:api                               # after any API schema change; commit the result
npm test                                      # vitest
```
````

Add to "Design decisions":

```markdown
- **Caddy serves the SPA and fronts the API under `/api`.** The API's paths and the SPA's
  routes would otherwise collide on a refresh; the proxy strips the prefix, so the API itself
  is unchanged. The interactive docs are at `http://127.0.0.1:8000/docs` in development only.
```

Also remove the now-false sentences "TLS and a reverse proxy arrive with the SPA in phase 3 …" and "— a phase 3 gate" (the body cap now exists), and change the `api/uploads.py` comment `# ponytail: the proxy should cap request bodies too; that arrives with Caddy in phase 3` to `# Caddy caps request bodies at 12 MB before they reach uvicorn (web/Caddyfile).`

- [ ] **Step 13: Commit**

```bash
git add tools/dump_openapi.py web .gitignore docker-compose.yml Dockerfile \
  .github/workflows/ci.yml README.md api/uploads.py
git commit -m "feat(web): scaffold the SPA with a generated client, behind Caddy with TLS"
```

---

### Task 6: Sign-in, invite acceptance, and the session guard

**Files:**
- Create: `web/src/auth/next.ts`, `web/src/auth/next.test.ts`, `web/src/api/client.test.ts`, `web/src/auth/session.tsx`, `web/src/auth/Login.tsx`, `web/src/auth/AcceptInvite.tsx`, `web/src/Shell.tsx`
- Modify: `web/src/main.tsx`, `web/src/App.tsx`

**Interfaces:**
- Consumes: `api`, `call`, `ApiError`, `errorMessage` (Task 5).
- Produces:
  - `safeNext(next: string | null) -> string` — an in-app path, `"/"` otherwise.
  - `useMe()` — TanStack query `["me"]`, data `Schemas["UserOut"] | null` (null = signed out).
  - `<RequireAuth>` — renders children when signed in, else navigates to `/login?next=<here>`.
  - `<Shell>` — header (Library link, email, Sign out) around an `<Outlet/>`.
  - Any query or mutation failing with `ApiError` status 401 sets `["me"]` to `null`, so `RequireAuth` sends the user to log in.

- [ ] **Step 1: Write the failing tests**

```ts
// web/src/auth/next.test.ts
import { describe, expect, it } from "vitest";
import { safeNext } from "./next";

describe("safeNext", () => {
  it("keeps an in-app path with its query", () => {
    expect(safeNext("/series/3?tab=volumes")).toBe("/series/3?tab=volumes");
  });
  it.each([null, "", "https://evil.example", "//evil.example", "/\\evil.example", "series"])(
    "falls back to / for %s",
    (next) => expect(safeNext(next)).toBe("/"),
  );
});
```

```ts
// web/src/api/client.test.ts
import { describe, expect, it } from "vitest";
import { ApiError, call, errorMessage } from "./client";

describe("errorMessage", () => {
  it("reads a string detail", () => {
    expect(errorMessage({ detail: "not found" })).toBe("not found");
  });
  it("joins validation errors without the body/query prefix", () => {
    expect(
      errorMessage({ detail: [{ loc: ["body", "title"], msg: "too short" }, { loc: [], msg: "bad" }] }),
    ).toBe("title: too short; bad");
  });
  it("falls back when there is no detail", () => {
    expect(errorMessage(undefined)).toBe("request failed");
  });
});

describe("call", () => {
  it("throws ApiError with the status", async () => {
    const failed = Promise.resolve({ error: { detail: "nope" }, response: new Response(null, { status: 401 }) });
    await expect(call(failed)).rejects.toMatchObject({ status: 401, message: "nope" });
    await expect(call(failed)).rejects.toBeInstanceOf(ApiError);
  });
  it("returns data on success", async () => {
    const ok = Promise.resolve({ data: { id: 1 }, response: new Response(null, { status: 200 }) });
    await expect(call(ok)).resolves.toEqual({ id: 1 });
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd web && npm test`
Expected: `next.test.ts` FAILS (cannot resolve `./next`); `client.test.ts` passes (Task 5 wrote `client.ts`).

- [ ] **Step 3: Write `web/src/auth/next.ts`**

```ts
/** Where to go after signing in: an in-app path only, so ?next= cannot send anyone off-site. */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  return next;
}
```

Run: `npm test` — Expected: all PASS.

- [ ] **Step 4: Write `web/src/auth/session.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { api, ApiError, call, type Schemas } from "../api/client";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<Schemas["UserOut"] | null> => {
      try {
        return await call(api.GET("/auth/me"));
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: Infinity,
  });
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const me = useMe();
  const here = useLocation();
  if (me.isPending) return <p className="muted">Loading…</p>;
  if (me.isError) return <p className="error">{me.error.message}</p>;
  if (!me.data) {
    const next = encodeURIComponent(here.pathname + here.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return children;
}
```

- [ ] **Step 5: Send every 401 to sign-in, in `web/src/main.tsx`**

Replace the `queryClient` construction with:

```tsx
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "./api/client";

// An expired session surfaces as a 401 on whatever request comes next. Marking the user
// signed out makes RequireAuth redirect to /login?next=<this page>.
function signedOutOn401(error: Error) {
  if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(["me"], null);
}

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError: signedOutOn401 }),
  mutationCache: new MutationCache({ onError: signedOutOn401 }),
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});
```

(Merge the import line with the existing `@tanstack/react-query` import.)

- [ ] **Step 6: Write `web/src/auth/Login.tsx`**

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { api, call } from "../api/client";
import { safeNext } from "./next";
import { useMe } from "./session";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useMe();
  const login = useMutation({
    mutationFn: () => call(api.POST("/auth/login", { body: { email, password } })),
    onSuccess: (user) => {
      queryClient.setQueryData(["me"], user);
      navigate(next, { replace: true });
    },
  });
  if (me.data) return <Navigate to={next} replace />;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };
  return (
    <main>
      <h1>Sign in</h1>
      <form className="stack" onSubmit={submit}>
        <label>
          Email <input type="email" autoComplete="username" required value={email}
            onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password <input type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button disabled={login.isPending}>Sign in</button>
        {login.isError && <p className="error" role="alert">{login.error.message}</p>}
      </form>
    </main>
  );
}
```

- [ ] **Step 7: Write `web/src/auth/AcceptInvite.tsx`**

```tsx
import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { api, call } from "../api/client";

/** /invite?token=… — the link an admin hands out. Creates the account; the user then signs in. */
export default function AcceptInvite() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const accept = useMutation({
    mutationFn: () =>
      call(api.POST("/auth/accept-invite", { body: { token, email, password } })),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    accept.mutate();
  };
  if (accept.isSuccess) {
    return (
      <main>
        <p>Account created. <Link to="/login">Sign in</Link>.</p>
      </main>
    );
  }
  return (
    <main>
      <h1>Create your account</h1>
      {!token && <p className="error">This link has no invite token.</p>}
      <form className="stack" onSubmit={submit}>
        <label>
          Email <input type="email" autoComplete="username" required value={email}
            onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password <input type="password" autoComplete="new-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button disabled={!token || accept.isPending}>Create account</button>
        {accept.isError && <p className="error" role="alert">{accept.error.message}</p>}
      </form>
    </main>
  );
}
```

The body matches `AcceptInvite` in `api/schemas/invites.py` (`token`, `email`, `password` with `min_length=12`). Add `minLength={12}` to the password input so the browser says so before the API does.

- [ ] **Step 8: Write `web/src/Shell.tsx` and the routes**

```tsx
// web/src/Shell.tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";
import { api, call } from "./api/client";
import { useMe } from "./auth/session";

export default function Shell() {
  const me = useMe();
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: () => call(api.POST("/auth/logout")),
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(["me"], null);
    },
  });
  return (
    <>
      <header className="app">
        <nav>
          <NavLink to="/">Library</NavLink>
        </nav>
        <span className="muted">{me.data?.email}</span>
        <button onClick={() => logout.mutate()}>Sign out</button>
      </header>
      <Outlet />
    </>
  );
}
```

```tsx
// web/src/App.tsx
import { Route, Routes } from "react-router";
import AcceptInvite from "./auth/AcceptInvite";
import Login from "./auth/Login";
import { RequireAuth } from "./auth/session";
import Shell from "./Shell";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/invite" element={<AcceptInvite />} />
      <Route element={<RequireAuth><Shell /></RequireAuth>}>
        <Route index element={<main><p>Library</p></main>} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 9: Build and smoke**

Run: `cd web && npm test && npm run build`. Expected: PASS.

Smoke (API running with `TA_COOKIE_SECURE=false`, a user from `python -m tools.seed_admin`), at `http://localhost:5173`:
1. `/series/1` while signed out → lands on `/login?next=%2Fseries%2F1`.
2. Wrong password → the API's message under the form. Right password → back at `/series/1` (blank for now; Task 8 fills it).
3. Expire the session server-side (`docker compose exec postgres psql -U ta -d ta -c 'delete from sessions'`), then on `/series/1` click Library → the documents request answers 401 and the app lands on `/login?next=%2F`.
4. `/login?next=//evil.example` → after sign-in, stays on the app's `/`.
5. Sign out → login screen.

- [ ] **Step 10: Commit**

```bash
git add web/src
git commit -m "feat(web): sign-in, invite acceptance, and a session guard that follows 401s"
```

---

### Task 7: The document picker

**Files:**
- Create: `web/src/library/group.ts`, `web/src/library/group.test.ts`, `web/src/library/queries.ts`, `web/src/library/Picker.tsx`, `web/src/library/DocumentRow.tsx`, `web/src/library/NewDocument.tsx`
- Modify: `web/src/App.tsx`

**Interfaces:**
- Consumes: `api`, `call`, `Schemas` (Task 5); `Shell` route (Task 6). Endpoints: `GET /documents`, `GET /series`, `POST /series`, `POST /documents`, `PATCH /documents/{id}`, `DELETE /documents/{id}`, `POST /documents/merge`, `POST /documents/import/txt`, `GET /documents/{id}/export`.
- Produces:
  - `groupDocuments(docs: Doc[], series: SeriesRow[], filter: string) -> Group[]`, `Group = { series: SeriesRow | null; docs: Doc[] }`, `Doc = Schemas["DocumentListItem"]`, `SeriesRow = Schemas["SeriesOut"]`.
  - `useDocuments()`, `useSeriesList()`, `invalidateLibrary(queryClient)` in `queries.ts` (query keys `["documents"]`, `["series"]`).
  - Route `/` → `<Picker/>`.

- [ ] **Step 1: Write the failing test `web/src/library/group.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import { groupDocuments, type Doc, type SeriesRow } from "./group";

const series = (id: number, title: string) => ({ id, title }) as SeriesRow;
const doc = (id: number, title: string, series_id: number | null, series_order = 0, updated_at = "2026-01-01T00:00:00Z") =>
  ({ id, title, chapter_title: "", series_id, series_order, updated_at }) as Doc;

const S = [series(2, "Volume 10"), series(1, "Volume 9")];
const D = [
  doc(1, "Ch 2", 1, 2),
  doc(2, "Ch 1", 1, 1),
  doc(3, "Loose old", null, 0, "2026-01-01T00:00:00Z"),
  doc(4, "Loose new", null, 0, "2026-02-01T00:00:00Z"),
  doc(5, "Ch 1", 2, 1),
];

describe("groupDocuments", () => {
  it("orders series naturally, chapters by series_order, unsorted last by recency", () => {
    const groups = groupDocuments(D, S, "");
    expect(groups.map((g) => g.series?.title ?? null)).toEqual(["Volume 9", "Volume 10", null]);
    expect(groups[0].docs.map((d) => d.id)).toEqual([2, 1]);
    expect(groups[2].docs.map((d) => d.id)).toEqual([4, 3]);
  });

  it("keeps empty series when not filtering", () => {
    expect(groupDocuments([], [series(1, "Empty")], "").map((g) => g.docs.length)).toEqual([0]);
  });

  it("filters case-insensitively on title and drops empty groups", () => {
    const groups = groupDocuments(D, S, "LOOSE");
    expect(groups).toHaveLength(1);
    expect(groups[0].docs.map((d) => d.id)).toEqual([4, 3]);
  });

  it("a series title match shows the whole series", () => {
    const groups = groupDocuments(D, S, "volume 10");
    expect(groups.map((g) => g.series?.id)).toEqual([2]);
    expect(groups[0].docs.map((d) => d.id)).toEqual([5]);
  });

  it("matches Japanese titles", () => {
    expect(groupDocuments([doc(9, "第一話", null)], [], "一話")[0].docs[0].id).toBe(9);
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd web && npm test`
Expected: FAIL — cannot resolve `./group`

- [ ] **Step 3: Write `web/src/library/group.ts`**

```ts
import type { Schemas } from "../api/client";

export type Doc = Schemas["DocumentListItem"];
export type SeriesRow = Schemas["SeriesOut"];
export interface Group {
  series: SeriesRow | null;
  docs: Doc[];
}

const natural = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

/** The picker's groups: series in natural title order, each with its chapters in reading
 *  order, then unsorted documents, most recently edited first. A filter matches a document
 *  title, a chapter title, or a series title (which shows the whole series). */
export function groupDocuments(docs: Doc[], series: SeriesRow[], filter: string): Group[] {
  const q = filter.trim().toLocaleLowerCase();
  const has = (s: string) => s.toLocaleLowerCase().includes(q);
  const bySeries = new Map<number | null, Doc[]>();
  for (const d of docs) {
    const list = bySeries.get(d.series_id) ?? [];
    list.push(d);
    bySeries.set(d.series_id, list);
  }
  const groups: Group[] = [...series]
    .sort((a, b) => natural.compare(a.title, b.title))
    .map((s) => ({
      series: s,
      docs: (bySeries.get(s.id) ?? []).sort((a, b) => a.series_order - b.series_order || a.id - b.id),
    }));
  groups.push({
    series: null,
    docs: (bySeries.get(null) ?? []).sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
  });
  if (!q) return groups.filter((g) => g.series || g.docs.length);
  return groups
    .map((g) =>
      g.series && has(g.series.title)
        ? g
        : { ...g, docs: g.docs.filter((d) => has(d.title) || has(d.chapter_title)) },
    )
    .filter((g) => g.docs.length);
}
```

Run: `npm test` — Expected: PASS.

- [ ] **Step 4: Write `web/src/library/queries.ts`**

```ts
import { useQuery, type QueryClient } from "@tanstack/react-query";
import { api, call } from "../api/client";

export const useDocuments = () =>
  useQuery({ queryKey: ["documents"], queryFn: () => call(api.GET("/documents")) });

export const useSeriesList = () =>
  useQuery({ queryKey: ["series"], queryFn: () => call(api.GET("/series")) });

/** After any library write: the picker's documents and series lists refetch. */
export function invalidateLibrary(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ["documents"] }),
    queryClient.invalidateQueries({ queryKey: ["series"] }),
  ]);
}
```

- [ ] **Step 5: Write `web/src/library/DocumentRow.tsx`**

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import type { Doc, SeriesRow } from "./group";
import { invalidateLibrary } from "./queries";

interface Props {
  doc: Doc;
  series: SeriesRow[];
  selected: boolean;
  onSelect: (checked: boolean) => void;
}

/** One picker row: select, rename in place (double-click), move to a series, export. */
export default function DocumentRow({ doc, series, selected, onSelect }: Props) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const update = useMutation({
    mutationFn: (body: { title?: string; series_id?: number | null }) =>
      call(api.PATCH("/documents/{document_id}", { params: { path: { document_id: doc.id } }, body })),
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const rename = (title: string) => {
    setEditing(false);
    if (title.trim() && title !== doc.title) update.mutate({ title });
  };
  const exportUrl = (format: string) => `/api/documents/${doc.id}/export?format=${format}`;
  return (
    <tr>
      <td>
        <input type="checkbox" aria-label={`Select ${doc.title}`} checked={selected}
          onChange={(e) => onSelect(e.target.checked)} />
      </td>
      <td onDoubleClick={() => setEditing(true)}>
        {editing ? (
          <input autoFocus defaultValue={doc.title} aria-label="Title"
            onBlur={(e) => rename(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") rename(e.currentTarget.value);
              if (e.key === "Escape") setEditing(false);
            }} />
        ) : (
          doc.title
        )}
        {update.isError && <span className="error"> {update.error.message}</span>}
      </td>
      <td>{doc.progress}%</td>
      <td className="muted">{new Date(doc.updated_at).toLocaleString()}</td>
      <td>
        <select aria-label="Series" value={doc.series_id ?? ""}
          onChange={(e) => update.mutate({ series_id: e.target.value ? Number(e.target.value) : null })}>
          <option value="">Unsorted</option>
          {series.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
        </select>
      </td>
      <td>
        <a href={exportUrl("txt")} download>TXT</a>{" "}
        <a href={exportUrl("md")} download>MD</a>{" "}
        <a href={exportUrl("md-ruby")} download>Ruby MD</a>
      </td>
    </tr>
  );
}
```

- [ ] **Step 6: Write `web/src/library/NewDocument.tsx`**

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, ApiError, call, errorMessage } from "../api/client";
import type { SeriesRow } from "./group";
import { invalidateLibrary } from "./queries";

/** New document from pasted text, or import a desktop ---SEPERATOR--- TXT file. */
export default function NewDocument({ series, onDone }: { series: SeriesRow[]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [seriesId, setSeriesId] = useState("");
  const [rawText, setRawText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const create = useMutation({
    mutationFn: async () => {
      const series_id = seriesId ? Number(seriesId) : null;
      if (!file) {
        return call(api.POST("/documents", { body: { title, series_id, raw_text: rawText } }));
      }
      // Multipart: built by hand, since the generated client types JSON bodies.
      const form = new FormData();
      form.append("file", file);
      if (title.trim()) form.append("title", title);
      if (series_id !== null) form.append("series_id", String(series_id));
      const response = await fetch("/api/documents/import/txt", { method: "POST", body: form });
      if (!response.ok) {
        throw new ApiError(response.status, errorMessage(await response.json().catch(() => null)));
      }
      return response.json();
    },
    onSuccess: async () => {
      await invalidateLibrary(queryClient);
      onDone();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };
  return (
    <form className="stack" onSubmit={submit}>
      <label>
        Title <input value={title} required={!file} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        Series{" "}
        <select value={seriesId} onChange={(e) => setSeriesId(e.target.value)}>
          <option value="">Unsorted</option>
          {series.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
        </select>
      </label>
      <label>
        Source text <textarea rows={8} value={rawText} disabled={!!file}
          onChange={(e) => setRawText(e.target.value)} />
      </label>
      <label>
        …or import a TXT file <input type="file" accept=".txt,text/plain"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <div className="toolbar">
        <button disabled={create.isPending}>{file ? "Import" : "Create"}</button>
        <button type="button" onClick={onDone}>Cancel</button>
      </div>
      {create.isError && <p className="error" role="alert">{create.error.message}</p>}
    </form>
  );
}
```

`fetch` sends the session cookie on a same-origin request by default. A 401 from it is not seen by the global handler unless it is thrown as `ApiError` — which it is, from inside the mutation, so `MutationCache.onError` handles it.

- [ ] **Step 7: Write `web/src/library/Picker.tsx`**

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import DocumentRow from "./DocumentRow";
import { groupDocuments } from "./group";
import NewDocument from "./NewDocument";
import { invalidateLibrary, useDocuments, useSeriesList } from "./queries";

export default function Picker() {
  const queryClient = useQueryClient();
  const docs = useDocuments();
  const series = useSeriesList();
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);
  const done = () => {
    setSelected(new Set());
    return invalidateLibrary(queryClient);
  };
  const remove = useMutation({
    mutationFn: (ids: number[]) =>
      Promise.all(ids.map((id) =>
        call(api.DELETE("/documents/{document_id}", { params: { path: { document_id: id } } })))),
    onSettled: done,
  });
  const merge = useMutation({
    mutationFn: (title: string) =>
      call(api.POST("/documents/merge", { body: { document_ids: [...selected], title } })),
    onSuccess: done,
  });
  const newSeries = useMutation({
    mutationFn: (title: string) => call(api.POST("/series", { body: { title } })),
    onSuccess: done,
  });
  if (docs.isPending || series.isPending) return <main><p className="muted">Loading…</p></main>;
  if (docs.isError || series.isError) {
    return <main><p className="error">{(docs.error ?? series.error)?.message}</p></main>;
  }
  const groups = groupDocuments(docs.data, series.data, filter);
  const toggle = (id: number, on: boolean) => {
    const next = new Set(selected);
    if (on) next.add(id);
    else next.delete(id);
    setSelected(next);
  };
  const error = remove.error ?? merge.error ?? newSeries.error;
  return (
    <main>
      <div className="toolbar">
        <input type="search" placeholder="Filter" aria-label="Filter" value={filter}
          onChange={(e) => setFilter(e.target.value)} />
        <button onClick={() => setCreating(true)}>New document</button>
        <button onClick={() => {
          const title = window.prompt("Series title");
          if (title?.trim()) newSeries.mutate(title);
        }}>New series</button>
        <button disabled={selected.size < 2} onClick={() => {
          const title = window.prompt("Title of the merged chapter");
          if (title?.trim()) merge.mutate(title);
        }}>Merge {selected.size || ""}</button>
        <button disabled={!selected.size} onClick={() => {
          if (window.confirm(`Delete ${selected.size} document(s)? This cannot be undone.`)) {
            remove.mutate([...selected]);
          }
        }}>Delete {selected.size || ""}</button>
      </div>
      {error && <p className="error" role="alert">{error.message}</p>}
      {creating && <NewDocument series={series.data} onDone={() => setCreating(false)} />}
      {groups.map((g) => (
        <section key={g.series?.id ?? "unsorted"}>
          <h2>
            {g.series ? <Link to={`/series/${g.series.id}`}>{g.series.title}</Link> : "Unsorted"}
          </h2>
          {g.docs.length ? (
            <table>
              <tbody>
                {g.docs.map((d) => (
                  <DocumentRow key={d.id} doc={d} series={series.data}
                    selected={selected.has(d.id)} onSelect={(on) => toggle(d.id, on)} />
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">No chapters yet.</p>
          )}
        </section>
      ))}
    </main>
  );
}
```

In `App.tsx`, replace the index route's element with `<Picker />` (import it).

- [ ] **Step 8: Build and smoke**

Run: `cd web && npm test && npm run build`. Expected: PASS.

Smoke at `http://localhost:5173` (signed in):
1. New series "Test", New document with pasted Japanese text in "Test" → appears under "Test" with 0%.
2. Import a desktop TXT (`---SEPERATOR---` format) → appears; import a Shift-JIS file → the API's 422 message shows.
3. Filter "test" → only the "Test" group; filter a Japanese fragment of a title → that row.
4. Double-click a title, rename, Enter → renamed; Escape cancels.
5. Select two chapters → Merge → one chapter; Delete with confirm → gone.
6. Each export link downloads a file with the chapter's name.

- [ ] **Step 9: Commit**

```bash
git add web/src
git commit -m "feat(web): document picker with grouping, filter, create, import, merge, delete"
```

---

### Task 8: Series and volume manager

**Files:**
- Create: `web/src/library/order.ts`, `web/src/library/order.test.ts`, `web/src/library/SeriesPage.tsx`, `web/src/library/Chapters.tsx`, `web/src/library/Volumes.tsx`
- Modify: `web/src/App.tsx`

**Interfaces:**
- Consumes: `useDocuments`, `useSeriesList`, `invalidateLibrary` (Task 7); `Doc` (Task 7). Endpoints: `GET/PATCH/DELETE /series/{id}`, `PUT /series/{id}/order`, `POST /series/{id}/renumber`, `GET /series/{id}/export/markdown`, `GET /profiles`, `GET/POST /series/{id}/volumes`, `PATCH/DELETE /volumes/{id}`, `POST /volumes/{id}/documents`, `PUT/DELETE /documents/{id}/cover`.
- Produces: `moveItem<T>(items: T[], from: number, to: number) -> T[]`; route `/series/:id` → `<SeriesPage/>`.

- [ ] **Step 1: Write the failing test `web/src/library/order.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import { moveItem } from "./order";

describe("moveItem", () => {
  it("moves down", () => expect(moveItem(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "c", "a", "d"]));
  it("moves up", () => expect(moveItem(["a", "b", "c", "d"], 3, 1)).toEqual(["a", "d", "b", "c"]));
  it("same place is a copy", () => {
    const items = ["a", "b"];
    const moved = moveItem(items, 1, 1);
    expect(moved).toEqual(items);
    expect(moved).not.toBe(items);
  });
  it("does not mutate its input", () => {
    const items = ["a", "b", "c"];
    moveItem(items, 0, 2);
    expect(items).toEqual(["a", "b", "c"]);
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd web && npm test` — Expected: FAIL, cannot resolve `./order`.

- [ ] **Step 3: Write `web/src/library/order.ts`**

```ts
/** A copy of `items` with the element at `from` moved to index `to`. */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}
```

Run: `npm test` — Expected: PASS.

- [ ] **Step 4: Write `web/src/library/Chapters.tsx`**

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError, call, errorMessage } from "../api/client";
import type { Doc } from "./group";
import { moveItem } from "./order";
import { invalidateLibrary } from "./queries";

/** A series' chapters in reading order: drag to reorder (native drag events), renumber by
 *  title, and set or clear each chapter's cover. */
export default function Chapters({ seriesId, docs }: { seriesId: number; docs: Doc[] }) {
  const queryClient = useQueryClient();
  const [dragging, setDragging] = useState<number | null>(null);
  const [order, setOrder] = useState<Doc[] | null>(null); // optimistic order while saving
  const shown = order ?? docs;
  const settle = async () => {
    await invalidateLibrary(queryClient);
    setOrder(null);
  };
  const reorder = useMutation({
    mutationFn: (ids: number[]) =>
      call(api.PUT("/series/{series_id}/order", {
        params: { path: { series_id: seriesId } }, body: { document_ids: ids },
      })),
    onSettled: settle,
  });
  const renumber = useMutation({
    mutationFn: () =>
      call(api.POST("/series/{series_id}/renumber", { params: { path: { series_id: seriesId } } })),
    onSettled: settle,
  });
  const cover = useMutation({
    mutationFn: async ({ id, file }: { id: number; file: File | null }) => {
      if (!file) {
        return call(api.DELETE("/documents/{document_id}/cover", { params: { path: { document_id: id } } }));
      }
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(`/api/documents/${id}/cover`, { method: "PUT", body: form });
      if (!response.ok) {
        throw new ApiError(response.status, errorMessage(await response.json().catch(() => null)));
      }
    },
    onSettled: settle,
  });
  const drop = (to: number) => {
    if (dragging === null || dragging === to) return;
    const next = moveItem(shown, dragging, to);
    setOrder(next);
    setDragging(null);
    reorder.mutate(next.map((d) => d.id));
  };
  const error = reorder.error ?? renumber.error ?? cover.error;
  return (
    <section>
      <div className="toolbar">
        <h2>Chapters</h2>
        <button onClick={() => renumber.mutate()} disabled={renumber.isPending}>Renumber by title</button>
      </div>
      {error && <p className="error" role="alert">{error.message}</p>}
      <table>
        <tbody>
          {shown.map((d, i) => (
            <tr key={d.id} draggable onDragStart={() => setDragging(i)}
              onDragOver={(e) => e.preventDefault()} onDrop={() => drop(i)}>
              <td aria-hidden>⠿</td>
              <td>{d.title}</td>
              <td>{d.progress}%</td>
              <td>
                {d.has_cover ? "Cover set " : ""}
                <label>
                  {d.has_cover ? "Replace" : "Set cover"}{" "}
                  <input type="file" accept="image/png,image/jpeg,image/gif,image/webp"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) cover.mutate({ id: d.id, file });
                    }} />
                </label>
                {d.has_cover && <button onClick={() => cover.mutate({ id: d.id, file: null })}>Clear</button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
```

Keyboard users cannot drag rows; "Renumber by title" is the keyboard path for ordering. Note this in the component's doc comment.

- [ ] **Step 5: Write `web/src/library/Volumes.tsx`**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";
import type { Doc } from "./group";
import { invalidateLibrary } from "./queries";

type Volume = Schemas["VolumeOut"];
const EPUB_FIELDS = [
  ["epub_title", "EPUB title"], ["epub_author", "Author"], ["epub_language", "Language"],
  ["epub_illustrator", "Illustrator"], ["epub_publisher", "Publisher"],
  ["epub_identifier", "Identifier"], ["epub_description", "Description"],
] as const;

function VolumeEditor({ volume, docs, onChanged }: { volume: Volume; docs: Doc[]; onChanged: () => void }) {
  const [assign, setAssign] = useState<number[]>([]);
  const save = useMutation({
    mutationFn: (body: Partial<Volume>) =>
      call(api.PATCH("/volumes/{volume_id}", { params: { path: { volume_id: volume.id } }, body })),
    onSuccess: onChanged,
  });
  const remove = useMutation({
    mutationFn: () => call(api.DELETE("/volumes/{volume_id}", { params: { path: { volume_id: volume.id } } })),
    onSuccess: onChanged,
  });
  const add = useMutation({
    mutationFn: () =>
      call(api.POST("/volumes/{volume_id}/documents", {
        params: { path: { volume_id: volume.id } }, body: { document_ids: assign },
      })),
    onSuccess: () => {
      setAssign([]);
      onChanged();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    save.mutate(Object.fromEntries(new FormData(e.currentTarget)) as Partial<Volume>);
  };
  const error = save.error ?? remove.error ?? add.error;
  return (
    <details>
      <summary>{volume.title} <span className="muted">({docs.filter((d) => d.volume_id === volume.id).length} chapters)</span></summary>
      <form className="stack" onSubmit={submit}>
        <label>Title <input name="title" defaultValue={volume.title} required /></label>
        {EPUB_FIELDS.map(([name, label]) => (
          <label key={name}>{label} <input name={name} defaultValue={volume[name]} /></label>
        ))}
        <div className="toolbar">
          <button disabled={save.isPending}>Save</button>
          <button type="button" onClick={() => {
            if (window.confirm(`Delete volume "${volume.title}"? Its chapters are kept.`)) remove.mutate();
          }}>Delete volume</button>
        </div>
      </form>
      <div className="toolbar">
        <select multiple aria-label="Chapters to assign" value={assign.map(String)}
          onChange={(e) => setAssign([...e.target.selectedOptions].map((o) => Number(o.value)))}>
          {docs.filter((d) => d.volume_id !== volume.id).map((d) => (
            <option key={d.id} value={d.id}>{d.title}</option>
          ))}
        </select>
        <button disabled={!assign.length || add.isPending} onClick={() => add.mutate()}>Assign to volume</button>
      </div>
      {error && <p className="error" role="alert">{error.message}</p>}
    </details>
  );
}

export default function Volumes({ seriesId, docs }: { seriesId: number; docs: Doc[] }) {
  const queryClient = useQueryClient();
  const key = ["series", seriesId, "volumes"];
  const volumes = useQuery({
    queryKey: key,
    queryFn: () => call(api.GET("/series/{series_id}/volumes", { params: { path: { series_id: seriesId } } })),
  });
  // ["series"] is a prefix of `key`, so this refetches the volumes too.
  const changed = () => invalidateLibrary(queryClient);
  const create = useMutation({
    mutationFn: (title: string) =>
      call(api.POST("/series/{series_id}/volumes", { params: { path: { series_id: seriesId } }, body: { title } })),
    onSuccess: changed,
  });
  if (volumes.isPending) return <p className="muted">Loading volumes…</p>;
  if (volumes.isError) return <p className="error">{volumes.error.message}</p>;
  return (
    <section>
      <div className="toolbar">
        <h2>Volumes</h2>
        <button onClick={() => {
          const title = window.prompt("Volume title");
          if (title?.trim()) create.mutate(title);
        }}>New volume</button>
      </div>
      {create.isError && <p className="error" role="alert">{create.error.message}</p>}
      {volumes.data.map((v) => <VolumeEditor key={v.id} volume={v} docs={docs} onChanged={changed} />)}
    </section>
  );
}
```

- [ ] **Step 6: Write `web/src/library/SeriesPage.tsx`**

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, call } from "../api/client";
import Chapters from "./Chapters";
import { invalidateLibrary, useDocuments, useSeriesList } from "./queries";
import Volumes from "./Volumes";

export default function SeriesPage() {
  const seriesId = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const all = useSeriesList();
  const docs = useDocuments();
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => call(api.GET("/profiles")) });
  const save = useMutation({
    mutationFn: (body: { title: string; syosetu_url: string; profile_id: number | null }) =>
      call(api.PATCH("/series/{series_id}", { params: { path: { series_id: seriesId } }, body })),
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const remove = useMutation({
    mutationFn: () => call(api.DELETE("/series/{series_id}", { params: { path: { series_id: seriesId } } })),
    onSuccess: async () => {
      await invalidateLibrary(queryClient);
      navigate("/");
    },
  });
  if (all.isPending || docs.isPending || profiles.isPending) return <main><p className="muted">Loading…</p></main>;
  const series = all.data?.find((s) => s.id === seriesId);
  if (!series) return <main><p>No such series. <Link to="/">Back to the library</Link></p></main>;
  const chapters = (docs.data ?? [])
    .filter((d) => d.series_id === seriesId)
    .sort((a, b) => a.series_order - b.series_order || a.id - b.id);
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const profile = String(form.get("profile_id") ?? "");
    save.mutate({
      title: String(form.get("title")),
      syosetu_url: String(form.get("syosetu_url")),
      profile_id: profile ? Number(profile) : null,
    });
  };
  return (
    <main>
      <p><Link to="/">← Library</Link></p>
      <form className="stack" onSubmit={submit} key={series.id}>
        <label>Title <input name="title" defaultValue={series.title} required /></label>
        <label>Series URL <input name="syosetu_url" type="url" defaultValue={series.syosetu_url} /></label>
        <label>
          Profile{" "}
          <select name="profile_id" defaultValue={series.profile_id ?? ""}>
            <option value="">Default profile</option>
            {(profiles.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <div className="toolbar">
          <button disabled={save.isPending}>Save</button>
          <a href={`/api/series/${seriesId}/export/markdown?variant=plain`} download>Markdown ZIP</a>
          <a href={`/api/series/${seriesId}/export/markdown?variant=ruby`} download>Ruby Markdown ZIP</a>
          <button type="button" onClick={() => {
            if (window.confirm(`Delete series "${series.title}"? Its chapters are kept, unsorted.`)) remove.mutate();
          }}>Delete series</button>
        </div>
        {(save.error ?? remove.error) && <p className="error" role="alert">{(save.error ?? remove.error)!.message}</p>}
      </form>
      <Chapters seriesId={seriesId} docs={chapters} />
      <Volumes seriesId={seriesId} docs={chapters} />
    </main>
  );
}
```

Check `GET /series/{id}` exists: the page could use it instead of finding the row in `GET /series`. Using the list keeps the picker cache warm and needs no extra query key; keep it.

In `App.tsx`, inside the `Shell` route, add `<Route path="series/:id" element={<SeriesPage />} />`.

- [ ] **Step 7: Build and smoke**

Run: `cd web && npm test && npm run build`. Expected: PASS.

Smoke (signed in, a series with three chapters titled "第3話", "第1話", "第2話"):
1. From the picker, click the series name → series page.
2. Rename, set the URL, pick a profile, Save → the picker shows the new name.
3. Drag the last chapter to the top → the order holds after a reload.
4. Renumber by title → 第1話, 第2話, 第3話.
5. Set a cover with a PNG → "Cover set"; a `.txt` renamed `.png` → the API's 415 message; Clear → gone.
6. New volume "V1", fill Author, Save; assign two chapters → "(2 chapters)"; Delete volume → chapters remain.
7. Both ZIP links download. Delete series → back to the picker, its chapters under "Unsorted".
8. `/series/999999` → "No such series".

- [ ] **Step 8: Commit**

```bash
git add web/src
git commit -m "feat(web): series manager with drag reorder, renumber, covers, and volumes"
```

---

### Task 9: Docs

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: Update status lines**

`README.md` first paragraph: phases 1–2 → "phases 1–2 and 3a"; add `- Phase 3a plan: [docs/superpowers/plans/2026-10-11-phase3a-editor-api-and-spa.md](…)`. Add to "Design decisions":

```markdown
- **`translated_at` is the day a line was first translated.** A save stamps it when a line goes
  from empty to non-empty, clears it when the line is emptied, and keeps it on an edit (the
  desktop restamped every edit).
- **Spellcheck spans are UTF-16 offsets**, the units of a browser string; enchant runs
  server-side with each profile's custom words. Without enchant or an English dictionary the
  endpoint answers `available: false` and flags nothing.
- **Images are served by sniffed type only** (PNG/JPEG/GIF/WebP); anything else is
  `application/octet-stream` with `nosniff`.
```

`CLAUDE.md` "What this is": add "Phase 3a: editor API (lines, spell, images), Caddy, and the SPA under `web/` (login, picker, series manager). Phase 3b (editor screen) is next." Add to Commands:

```bash
cd web && npm run dev                  # SPA on :5173, /api proxied to :8000
npm run gen:api                        # regenerate web/src/api/schema.d.ts after API changes
npm test                               # vitest (pure modules only)
```

- [ ] **Step 2: Final gate**

Run: `ruff check . && pytest -q && (cd web && npm test && npm run build)`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: phase 3a status, web development, and design decisions"
```

---

## Self-Review Notes

- **Spec coverage (§5 server half, §6 SPA half, §13):**
  - Line load with raw + substituted text: Task 2. Debounced dirty-line PATCH endpoint with `translated_at` rule: Task 2 (the client store is 3b).
  - Parse navigation input (`sentences`, profile `parse_chars`): Task 2.
  - `POST /spell/check` with profile custom words, suggestions, add-to-dictionary: Task 3.
  - Inline images with exclude-from-export and cover marker: Task 4 (API; rendering in cards is 3b).
  - Picker: grouped by series, progress, last edited, live filter, multi-select, in-place editing: Task 7.
  - Series manager: rename, URL, profile, delete, drag reorder, renumber; volumes: assign, rename, EPUB metadata, cover: Task 8.
  - Caddy with TLS, body cap, real client address: Task 5.
  - CI runs both suites: Task 5.
- **Left for 3b (editor plan):** line-card list, dirty-lines store and save indicator, keymap and the shortcut rebinding screen, parse navigation, find bar, CodeMirror spell decorations and suggestion menu, Japanese highlighting, client progress, inline image cards, split markers UI, opening a document and "restore last opened", Playwright smoke flows.
- **Not built, by the spec's phasing:** glossary editing and CSV import (phase 4), profile management screen (phase 4, with the glossary).
- **Names used across tasks:** `replace_and_parse`, `split_parse_chars` (`api/core/text.py`); `editor_profile` (`api/routers/lines.py`); `spell.dictionary`, `spell.misspellings`, `spell.suggest` (`api/core/spell.py`); `scoped_image` (`api/routers/images.py`); `api`, `call`, `ApiError`, `errorMessage`, `Schemas` (`web/src/api/client.ts`); `safeNext`, `useMe`, `RequireAuth`; `groupDocuments`, `Doc`, `SeriesRow`, `Group`; `useDocuments`, `useSeriesList`, `invalidateLibrary`; `moveItem`.
