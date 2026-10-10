# Phase 2 — Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the API a working library: series, volumes, and documents with full CRUD, a picker listing with per-chapter progress, chapter reorder and natural-sort renumber, merge and split, cover images, TXT import, and TXT / Markdown / ruby-Markdown / per-series-Markdown export.

**Architecture:** Three new resource routers (`series`, `volumes`, `documents`) plus a `transfer` router for uploads and downloads, all built with `api_router()` so writes commit in the request path. The desktop's pure text functions are ported verbatim into `api/core/text.py` (no DB imports). Shared queries go in `api/library.py`. Merge and split live in `api/restructure.py` and work by **moving** line and image rows (UPDATE `document_id` / `line_number`) rather than re-inserting them, so every line keeps its `translated_at`.

**Tech Stack:** Python 3.12, FastAPI 0.143, Starlette 1.7, SQLAlchemy 2.0, pydantic 2, PostgreSQL 16, pytest + Starlette `TestClient`. No new dependencies: `zipfile`, `io`, `urllib.parse`, and `python-multipart` (already installed) cover uploads and downloads.

**Spec:** `docs/superpowers/specs/2026-10-10-web-app-port-design.md`. This plan implements §15 phase 2 ("Library"), using §3 (data model and tenancy), §6 (library), and §12 (testing). The desktop reference is the sibling checkout `../TranslationAssistant-PySide6-Port` at commit `f1a96ce`.

## Global Constraints

- Everything in the Phase 1 plan's Global Constraints still applies. In particular: SQLAlchemy 2.0 style only, tests against real Postgres, cross-user access is **404, never 403**, no module over ~400 lines, Conventional Commits, and every task ends on a commit.
- Build every router with `api_router()` from `api/routing.py`. Handlers `flush()` and never `commit()`. `tests/test_commit_boundary.py` fails the build otherwise.
- Unique violations go through a savepoint plus `api.errors.conflict()` → 409, as in `api/routers/profiles.py`.
- Delete semantics follow the addressing (README "Design decisions"). An id-addressed resource that is not the caller's answers 404.
- **An id named in a request *body*** (`series_id`, `profile_id`, `volume_id`, `document_ids`) that is missing or someone else's answers **422 with one message for both cases**, so existence is still not disclosed. The URL names the resource; a bad body reference is invalid input, not a missing resource.
- Uploads are size-capped and content-sniffed (spec §6). Text uploads: at most 5 MiB, UTF-8 (a BOM is allowed and stripped), no NUL bytes. Image uploads: at most 10 MiB, PNG, JPEG, GIF, or WebP, identified by magic bytes rather than by the client's content type.
- `api/core/` holds Qt-free ported code with **no database imports** (spec §2). Port it verbatim. The only edits allowed are ones the linter forces, and each is listed in Task 1.
- Use `status.HTTP_422_UNPROCESSABLE_CONTENT` and `status.HTTP_413_CONTENT_TOO_LARGE`. Starlette 1.7 deprecates the older `..._ENTITY` names.
- A test that reads rows after an API call on the shared `db` session calls `db.expire_all()` first. The request ran in that same session, and database-side `ON DELETE SET NULL` changes are not reflected in loaded objects.

**Deviations from the spec, decided here:**

1. **No SPA in this phase.** §15 lists "the picker screen" under phase 2, but the README already places the SPA (and Caddy/TLS) in phase 3. Phase 2 ships the picker's *API*: `GET /documents` with progress, `GET /series`, and `GET /series/{id}/volumes`. Phase 3 scaffolds `web/` and builds the picker and the editor together, so the frontend toolchain arrives once.
2. **"Markdown import" is not built.** The desktop never imported Markdown; it only exported it. Phase 2 does TXT import plus Markdown export. EPUB import and batch-file import are phase 6, per §15.
3. **Deleting a series keeps its chapters.** They become unsorted documents (`series_id` and `volume_id` set to NULL), which matches the foreign keys from phase 1. Deleting chapters is a separate, explicit action.
4. **"Restore the last opened document on login"** needs no endpoint. The client stores `last_document_id` through the existing `PUT /settings`, and a stale id simply answers 404 from `GET /documents/{id}`.
5. **Merge and split move rows instead of rewriting them.** The desktop's `save_lines` re-keys `translated_at` by line number, so a merge or split silently moved or dropped translation timestamps, and with them the stats heatmap. Moving rows keeps each line's timestamp. In split, an image anchored after the last line goes to the **last** segment. The desktop left it stranded, out of range, on segment 0.

## Review Focus

1. **A body id naming another user's series, profile, volume, or document.** It must be refused (422), with the same response as a nonexistent id, and must never attach my chapter to their series. (Tasks 2, 3, 4, 5)
2. **Merging or splitting chapters that already have translation history.** Every moved line must keep its `translated_at`, or the phase 6 heatmap and streaks lose history. (Task 6)
3. **Splitting a chapter whose closing illustration is anchored after the last line.** The image must land in the last segment, not stay attached out of range to the first. (Task 6)
4. **Downloading a chapter or series with a Japanese title.** The download must produce a valid `Content-Disposition` header that keeps the real name (RFC 5987 `filename*`), not a 500 from a non-latin-1 header. (Task 7)
5. **Uploading a TXT file saved by Windows Notepad.** A UTF-8 BOM and CRLF line endings must import cleanly. A Shift-JIS or binary file must be a 422 with a reason, not a 500 or mojibake. (Task 7)

---

## File Structure

| File | Responsibility |
|---|---|
| `api/core/__init__.py` | Package marker |
| `api/core/text.py` | Verbatim port of the desktop text functions: SEPERATOR file format, sentence split, progress, Markdown builders, `natural_key`, `sanitize_filename` |
| `api/library.py` | Shared queries: `next_series_order`, `write_lines`, `line_arrays`, `chapters`, `renumber` |
| `api/restructure.py` | `merge_documents`, `split_document`, `RestructureError`, `NotOwned` |
| `api/uploads.py` | `read_capped`, `sniff_image` |
| `api/deps.py` (modify) | Add `owned_ref` and `scoped_volume` |
| `api/schemas/common.py` | `Title` type and the `Patch` base (null-rejecting PATCH bodies) |
| `api/schemas/series.py` | Series request and response models |
| `api/schemas/volumes.py` | Volume and cover models |
| `api/schemas/documents.py` | Document, picker row, id list, merge and split models |
| `api/routers/series.py` | `/series` CRUD, chapter reorder, renumber by title |
| `api/routers/volumes.py` | `/series/{id}/volumes`, `/volumes/{id}`, chapter assignment, document cover |
| `api/routers/documents.py` | `/documents` picker list, CRUD, merge, split |
| `api/routers/transfer.py` | TXT import, document export, series Markdown ZIP |
| `api/main.py` (modify) | Register the four routers |
| `tests/conftest.py` (modify) | `me`, `make_series`, `make_doc` fixtures |
| `tests/test_core_text.py` | Desktop `test_core.py` tests for the ported functions |
| `tests/test_series.py`, `tests/test_documents.py`, `tests/test_volumes.py`, `tests/test_restructure.py`, `tests/test_transfer.py` | One module per router; merge and split get their own (spec §12) |
| `README.md` (modify) | Phase 2 status, library decisions, `pg_dump` backup |

**Endpoint map** (everything requires a session; all paths are user-scoped):

```
GET    /series                         list mine, by title
POST   /series                         create                       201 · 409 title taken · 422 bad profile_id
GET    /series/{id}
PATCH  /series/{id}                    rename, profile, URL, wp_* fields
DELETE /series/{id}                    chapters kept, unsorted       204
PUT    /series/{id}/order              {document_ids}: full new order
POST   /series/{id}/renumber           1..N by natural title sort
GET    /series/{id}/volumes
POST   /series/{id}/volumes            201 · 409
PATCH  /volumes/{id}                   title, order, EPUB metadata
DELETE /volumes/{id}                   chapters kept, unassigned     204
POST   /volumes/{id}/documents         {document_ids}: assign chapters
PUT    /documents/{id}/cover           multipart image, replaces any cover
DELETE /documents/{id}/cover           204, idempotent
GET    /documents                      picker rows with progress
POST   /documents                      create, optional raw_text      201
GET    /documents/{id}
PATCH  /documents/{id}                 title, chapter_title, series_id, volume_id, source_*, last_position
DELETE /documents/{id}                 204
POST   /documents/merge                {document_ids, title}
POST   /documents/{id}/split           {cuts: [{start, title}]}
POST   /documents/import/txt           multipart file (+ title, series_id) 201
GET    /documents/{id}/export?format=txt|md|md-ruby
GET    /series/{id}/export/markdown?variant=plain|ruby   ZIP
```

---

### Task 1: Port the desktop text functions

**Files:**
- Create: `api/core/__init__.py`, `api/core/text.py`
- Test: `tests/test_core_text.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. The source is the desktop repository at `f1a96ce`.
- Produces (in `api.core.text`): `SEPARATOR: str`; `parse_file_content(text) -> (raw_lines, translated_lines, raw_section)`, which raises `ValueError` without the separator; `build_new_file(raw_input) -> str`; `lines_to_db_rows(raw_lines, translated_lines) -> list[dict]` with keys `line_number, prefix, raw_text, translated_text` (a blank line gets `prefix ""`); `db_rows_to_arrays(rows) -> (raw_lines, translated_lines)`; `line_has_content(raw) -> bool`; `calculate_progress(raw_lines, translated_lines) -> (percent, word_count)`; `build_markdown_translation(raw_lines, translated_lines, title="") -> str`; `build_markdown_ruby(raw_lines, translated_lines, title="") -> str`; `natural_key(s) -> list`; `sanitize_filename(name) -> str`.

Porting verbatim is the point (spec §1), so the module and its tests are *generated* from the pinned desktop commit rather than retyped. The script below was dry-run against `f1a96ce`. It produces a 251-line module that passes all 55 ported tests and `ruff check`. The only edit beyond the copy is `zip(..., strict=False)` in `calculate_progress`, which ruff's B905 requires; `strict=False` is the old behaviour. The tests get one rename (`l` → `ln`, for E741) and an added `import pytest`.

- [ ] **Step 1: Generate the failing test module**

Run from the repository root. `DESKTOP` defaults to the sibling checkout.

```bash
DESKTOP=${DESKTOP:-../TranslationAssistant-PySide6-Port}
git -C "$DESKTOP" cat-file -e f1a96ce || { echo "desktop repo missing commit f1a96ce"; exit 1; }
{
  cat <<'EOF'
"""Desktop tests/test_core.py (commit f1a96ce), ported with the functions they cover."""
import pytest

from api.core.text import (
    SEPARATOR,
    build_markdown_ruby,
    build_markdown_translation,
    build_new_file,
    calculate_progress,
    db_rows_to_arrays,
    lines_to_db_rows,
    natural_key,
    parse_file_content,
)
EOF
  git -C "$DESKTOP" show f1a96ce:tests/test_core.py \
    | sed -n '28,40p;46,176p;396,463p;501,577p;622,694p;1172,1186p' \
    | sed 's/\[l for l in result/[ln for ln in result/; s/if l\.strip()\]/if ln.strip()]/'
} > tests/test_core_text.py
```

These ranges cover the `make_file` helper, `TestParseFileContent`, `TestBuildNewFile`, `TestCalculateProgress`, `TestBuildMarkdownTranslation`, `TestBuildMarkdownRuby`, `TestLinesToDbRows`, `TestDbRowsToArrays`, and the three `natural_key` tests. File-system tests (`save_file`, `import_txt`, `export_txt`) are not ported, because the web app has no file paths.

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_core_text.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'api.core'`

- [ ] **Step 3: Generate `api/core/text.py`**

```bash
DESKTOP=${DESKTOP:-../TranslationAssistant-PySide6-Port}
core() { git -C "$DESKTOP" show f1a96ce:translation_assistant/core.py; }
mkdir -p api/core
: > api/core/__init__.py
{
  cat <<'EOF'
"""Qt-free text logic ported verbatim from the desktop ``translation_assistant/core.py``
(commit f1a96ce). Only the functions phase 2 uses are here; later phases append theirs.
No database imports: callers convert rows at the edge (see api/library.py)."""

import re

EOF
  core | sed -n '9p'; printf '\n\n'
  core | sed -n '16,108p;122,154p;384,411p;451,485p;539,580p;730,732p'
  cat <<'EOF'


def sanitize_filename(name: str) -> str:
    """From the desktop ``ui/main_widget._sanitize_filename``: safe as one path component."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")
EOF
} > api/core/text.py
python3 - <<'EOF'
from pathlib import Path
p = Path("api/core/text.py")
old = "    done = sum(1 for r, t in zip(raw_lines, translated_lines) if line_has_content(r) and t)\n"
new = ("    done = sum(\n"
       "        1 for r, t in zip(raw_lines, translated_lines, strict=False)\n"
       "        if line_has_content(r) and t\n"
       "    )\n")
s = p.read_text()
assert s.count(old) == 1, "desktop source drifted from f1a96ce"
p.write_text(s.replace(old, new))
EOF
```

The line ranges are, in order: `SEPARATOR`; `parse_file_content` + `build_new_file`; `lines_to_db_rows` + `db_rows_to_arrays`; `line_has_content` + `calculate_progress`; `build_markdown_translation`; `build_markdown_ruby`; `natural_key`.

- [ ] **Step 4: Read the generated module, then run the tests and lint**

Open `api/core/text.py` and confirm it starts with the docstring, `import re`, and `SEPARATOR = "---SEPERATOR---"`, and ends with `sanitize_filename`. It should be about 250 lines.

Run: `pytest tests/test_core_text.py -q && ruff check api/core tests/test_core_text.py`
Expected: `55 passed`, `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add api/core tests/test_core_text.py
git commit -m "feat(core): port the desktop text functions the library needs"
```

---

### Task 2: Series CRUD and body-reference scoping

**Files:**
- Modify: `api/deps.py` (add `owned_ref`), `api/main.py`, `tests/conftest.py`
- Create: `api/schemas/common.py`, `api/schemas/series.py`, `api/routers/series.py`
- Test: `tests/test_series.py`

**Interfaces:**
- Consumes: `scoped`, `current_user`, `db_session` (`api/deps.py`); `api_router` (`api/routing.py`); `conflict` (`api/errors.py`); models `Series`, `Profile`, `Volume`, `Document`, `Line`.
- Produces:
  - `api.deps.owned_ref(db, model, obj_id, user_id, field) -> T`: raises 422 `"{field}: no such item"` for missing or foreign.
  - `api.schemas.common.Title`: stripped, 1–300 chars.
  - `api.schemas.common.Patch`: a base model with a class attribute `NULLABLE: ClassVar[frozenset[str]]`.
  - `api.schemas.series.SeriesCreate`, `SeriesUpdate`, `SeriesOut`.
  - `api.routers.series.router` (prefix `/series`).
  - Test fixtures `me` (a signed-in `User`), `make_series(user, title="S") -> Series`, and `make_doc(user, raws=(), *, series=None, order=0, title="Ch", volume=None, translated=True) -> Document`.

- [ ] **Step 1: Add the shared fixtures to `tests/conftest.py`**

Append:

```python
@pytest.fixture
def me(app_client, make_user, login):
    """A signed-in user: the client carries their session."""
    user = make_user(email="me@example.com")
    login(app_client, "me@example.com")
    return user


@pytest.fixture
def make_series(db):
    from api.models import Series

    def _make(user, title="S"):
        series = Series(user_id=user.id, title=title)
        db.add(series)
        db.flush()
        return series

    return _make


@pytest.fixture
def make_doc(db):
    """make_doc(user, raws, ...) -> Document whose lines are `raws`, all '%'-prefixed.

    With translated=True each line's translation is 'tr:<raw>'; otherwise empty.
    chapter_title is set to `title`, as the desktop does for chapters."""
    from api.models import Document, Line

    def _make(user, raws=(), *, series=None, order=0, title="Ch", volume=None, translated=True):
        doc = Document(
            user_id=user.id,
            title=title,
            chapter_title=title,
            series_id=series.id if series else None,
            volume_id=volume.id if volume else None,
            series_order=order,
        )
        db.add(doc)
        db.flush()
        db.add_all(
            Line(
                document_id=doc.id,
                line_number=i,
                prefix="%",
                raw_text=raw,
                translated_text=f"tr:{raw}" if translated else "",
            )
            for i, raw in enumerate(raws)
        )
        db.flush()
        return doc

    return _make
```

- [ ] **Step 2: Write the failing tests in `tests/test_series.py`**

```python
import pytest

from api.models import Document, Profile, Volume


def test_series_require_authentication(app_client):
    assert app_client.get("/series").status_code == 401


def test_create_and_list_only_mine(app_client, me, make_user, make_series):
    make_series(make_user(email="other@example.com"), "Theirs")
    r = app_client.post("/series", json={"title": "  Mine  "})
    assert r.status_code == 201
    assert r.json()["title"] == "Mine"
    assert [s["title"] for s in app_client.get("/series").json()] == ["Mine"]


def test_blank_title_is_422(app_client, me):
    assert app_client.post("/series", json={"title": "   "}).status_code == 422


def test_duplicate_title_is_409(app_client, me):
    app_client.post("/series", json={"title": "S"})
    assert app_client.post("/series", json={"title": "S"}).status_code == 409


def test_foreign_profile_reads_exactly_like_a_missing_one(app_client, db, me, make_user):
    theirs = Profile(user_id=make_user(email="other@example.com").id, name="p")
    db.add(theirs)
    db.flush()
    foreign = app_client.post("/series", json={"title": "S", "profile_id": theirs.id})
    missing = app_client.post("/series", json={"title": "S", "profile_id": 999999})
    assert foreign.status_code == missing.status_code == 422
    assert foreign.json() == missing.json()


def test_patch_renames_and_clears_profile(app_client, db, me):
    profile = Profile(user_id=me.id, name="p")
    db.add(profile)
    db.flush()
    sid = app_client.post("/series", json={"title": "S", "profile_id": profile.id}).json()["id"]
    r = app_client.patch(f"/series/{sid}", json={"title": "S2", "profile_id": None})
    assert r.status_code == 200
    assert (r.json()["title"], r.json()["profile_id"]) == ("S2", None)


def test_patch_foreign_profile_is_422(app_client, db, me, make_user, make_series):
    theirs = Profile(user_id=make_user(email="other@example.com").id, name="p")
    db.add(theirs)
    db.flush()
    series = make_series(me)
    r = app_client.patch(f"/series/{series.id}", json={"profile_id": theirs.id})
    assert r.status_code == 422


def test_patch_null_title_is_422(app_client, me, make_series):
    series = make_series(me)
    assert app_client.patch(f"/series/{series.id}", json={"title": None}).status_code == 422


def test_rename_onto_existing_title_is_409(app_client, me, make_series):
    make_series(me, "A")
    b = make_series(me, "B")
    assert app_client.patch(f"/series/{b.id}", json={"title": "A"}).status_code == 409


def test_delete_keeps_chapters_unsorted(app_client, db, me, make_series, make_doc):
    series = make_series(me)
    volume = Volume(series_id=series.id, title="V1")
    db.add(volume)
    db.flush()
    doc = make_doc(me, ["a"], series=series, order=1, volume=volume)
    assert app_client.delete(f"/series/{series.id}").status_code == 204
    db.expire_all()
    kept = db.get(Document, doc.id)
    assert kept is not None
    assert (kept.series_id, kept.volume_id) == (None, None)


@pytest.mark.parametrize(
    ("method", "kwargs"), [("get", {}), ("patch", {"json": {"title": "x"}}), ("delete", {})]
)
def test_another_users_series_is_404(app_client, me, make_user, make_series, method, kwargs):
    theirs = make_series(make_user(email="other@example.com"), "Theirs")
    assert getattr(app_client, method)(f"/series/{theirs.id}", **kwargs).status_code == 404
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest tests/test_series.py -q`
Expected: FAIL. Every test gets 404 because `/series` is not routed.

- [ ] **Step 4: Add `owned_ref` to `api/deps.py`**

Append below `scoped`:

```python
def owned_ref[T: UserOwned](
    db: Session, model: type[T], obj_id: int, user_id: int, field: str
) -> T:
    """``scoped()`` for an id named in a request *body* (series_id, profile_id, ...).

    The URL names the resource, so a bad reference in the body is a 422, not a 404,
    and "missing" and "someone else's" get one message, so existence stays undisclosed.
    """
    try:
        return scoped(db, model, obj_id, user_id)
    except HTTPException:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field}: no such item"
        ) from None
```

- [ ] **Step 5: Write `api/schemas/common.py`**

```python
from typing import Annotated, ClassVar, Self

from pydantic import BaseModel, StringConstraints, model_validator

# A name a person reads in a list: surrounding whitespace dropped, never empty.
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class Patch(BaseModel):
    """A PATCH body. Omitted fields are left alone (handlers dump with exclude_unset);
    an explicit null is a client error, except for fields in NULLABLE, where null means
    "clear it"."""

    NULLABLE: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _no_explicit_null(self) -> Self:
        for field in self.model_fields_set - self.NULLABLE:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self
```

- [ ] **Step 6: Write `api/schemas/series.py`**

```python
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import Patch, Title


class SeriesCreate(BaseModel):
    title: Title
    profile_id: int | None = None
    syosetu_url: str = ""


class SeriesUpdate(Patch):
    NULLABLE: ClassVar[frozenset[str]] = frozenset(
        {"profile_id", "wp_password_enabled", "wp_unlock_after"}
    )

    title: Title | None = None
    profile_id: int | None = None
    syosetu_url: str | None = None
    wp_series_slug: str | None = None
    wp_series_title_short: str | None = None
    wp_password_enabled: bool | None = None
    wp_unlock_after: int | None = Field(default=None, ge=0)


class SeriesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    profile_id: int | None
    syosetu_url: str
    wp_series_slug: str
    wp_series_title_short: str
    wp_password_enabled: bool | None
    wp_unlock_after: int | None
    created_at: datetime
```

- [ ] **Step 7: Write `api/routers/series.py`**

```python
from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, owned_ref, scoped
from api.errors import conflict
from api.models import Profile, Series, User
from api.routing import api_router
from api.schemas.series import SeriesCreate, SeriesOut, SeriesUpdate

router = api_router(prefix="/series", tags=["series"])

TITLE_TAKEN = "a series with that title exists"


@router.get("", response_model=list[SeriesOut])
def list_series(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[Series]:
    return list(
        db.scalars(select(Series).where(Series.user_id == user.id).order_by(Series.title))
    )


@router.get("/{series_id}", response_model=SeriesOut)
def get_series(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Series:
    return scoped(db, Series, series_id, user.id)


@router.post("", response_model=SeriesOut, status_code=status.HTTP_201_CREATED)
def create_series(
    body: SeriesCreate, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Series:
    if body.profile_id is not None:
        owned_ref(db, Profile, body.profile_id, user.id, "profile_id")
    series = Series(user_id=user.id, **body.model_dump())
    try:
        with db.begin_nested():
            db.add(series)
    except IntegrityError as exc:
        raise conflict(exc, TITLE_TAKEN) from exc
    return series


@router.patch("/{series_id}", response_model=SeriesOut)
def update_series(
    series_id: int,
    body: SeriesUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Series:
    series = scoped(db, Series, series_id, user.id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("profile_id") is not None:
        owned_ref(db, Profile, changes["profile_id"], user.id, "profile_id")
    try:
        with db.begin_nested():
            for field, value in changes.items():
                setattr(series, field, value)
    except IntegrityError as exc:
        raise conflict(exc, TITLE_TAKEN) from exc
    return series


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_series(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    """Chapters survive: the ORM nulls their series_id, and the database's
    ON DELETE SET NULL clears volume_id as the series' volumes are deleted."""
    db.delete(scoped(db, Series, series_id, user.id))
    db.flush()
```

- [ ] **Step 8: Register the router in `api/main.py`**

Change the import to `from api.routers import auth, credentials, invites, profiles, series, settings` and add `app.include_router(series.router)` after the profiles line.

- [ ] **Step 9: Run the tests and lint**

Run: `pytest tests/test_series.py tests/test_commit_boundary.py -q && ruff check .`
Expected: all pass

- [ ] **Step 10: Commit**

```bash
git add api/deps.py api/main.py api/schemas/common.py api/schemas/series.py api/routers/series.py tests/conftest.py tests/test_series.py
git commit -m "feat(series): series CRUD with body references scoped to the caller"
```

---

### Task 3: Documents CRUD and the picker listing

**Files:**
- Create: `api/library.py`, `api/schemas/documents.py`, `api/routers/documents.py`
- Modify: `api/main.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Consumes: `owned_ref`, `scoped`; `Title`, `Patch`; `build_new_file`, `parse_file_content`, `lines_to_db_rows`, `db_rows_to_arrays` from `api.core.text`; fixtures `me`, `make_series`, `make_doc`.
- Produces:
  - `api.library.next_series_order(db, series_id: int | None) -> int`: `max + 1`, or 0 outside a series.
  - `api.library.write_lines(db, document_id, rows: list[dict]) -> None`: takes `lines_to_db_rows()` output and stores a blank line's prefix as `"%"`.
  - `api.library.line_arrays(db, document_id) -> (raw_lines, translated_lines)`: a blank line comes back as `""`.
  - `api.schemas.documents.DocumentCreate`, `DocumentUpdate`, `DocumentOut`, `DocumentListItem`.
  - `api.routers.documents.router` (prefix `/documents`) and `check_placement(db, user_id, series_id, volume_id) -> None`.

- [ ] **Step 1: Write the failing tests in `tests/test_documents.py`**

```python
import pytest
from sqlalchemy import select

from api.models import DocumentImage, Line, Volume


def _lines(db, doc_id):
    db.expire_all()
    rows = db.scalars(select(Line).where(Line.document_id == doc_id).order_by(Line.line_number))
    return [(ln.prefix, ln.raw_text) for ln in rows]


def test_documents_require_authentication(app_client):
    assert app_client.get("/documents").status_code == 401


def test_create_empty_document(app_client, me):
    r = app_client.post("/documents", json={"title": "Notes"})
    assert r.status_code == 201
    assert (r.json()["series_id"], r.json()["series_order"]) == (None, 0)


def test_create_from_raw_text_splits_sentences(app_client, db, me):
    r = app_client.post("/documents", json={"title": "Ch1", "raw_text": "一文目。二文目。\n\n次"})
    assert _lines(db, r.json()["id"]) == [
        ("%", "一文目。"), ("$", "二文目。"), ("%", ""), ("%", "次"),
    ]


def test_create_in_series_appends(app_client, me, make_series, make_doc):
    series = make_series(me)
    make_doc(me, series=series, order=3)
    r = app_client.post("/documents", json={"title": "Next", "series_id": series.id})
    assert r.json()["series_order"] == 4


def test_volume_must_belong_to_the_named_series(app_client, db, me, make_series):
    a, b = make_series(me, "A"), make_series(me, "B")
    vol = Volume(series_id=b.id, title="V")
    db.add(vol)
    db.flush()
    wrong = app_client.post(
        "/documents", json={"title": "x", "series_id": a.id, "volume_id": vol.id}
    )
    no_series = app_client.post("/documents", json={"title": "x", "volume_id": vol.id})
    assert wrong.status_code == no_series.status_code == 422


def test_foreign_series_reads_exactly_like_a_missing_one(app_client, me, make_user, make_series):
    theirs = make_series(make_user(email="other@example.com"))
    foreign = app_client.post("/documents", json={"title": "x", "series_id": theirs.id})
    missing = app_client.post("/documents", json={"title": "x", "series_id": 999999})
    assert foreign.status_code == missing.status_code == 422
    assert foreign.json() == missing.json()


def test_list_reports_progress_and_only_mine(app_client, db, me, make_user, make_doc):
    half = make_doc(me, ["a", "b"], title="Half", translated=False)
    half.lines[0].translated_text = "A"
    make_doc(me, ["a", "", "b"], title="Blanks ignored")
    pictures = make_doc(me, [], title="Pictures")
    db.add(DocumentImage(document_id=pictures.id, src_path="p.png", data=b"x", is_cover=True))
    make_doc(make_user(email="other@example.com"), ["z"], title="Theirs")
    db.flush()
    rows = {d["title"]: d for d in app_client.get("/documents").json()}
    assert set(rows) == {"Half", "Blanks ignored", "Pictures"}
    assert (rows["Half"]["progress"], rows["Half"]["line_count"]) == (50, 2)
    assert rows["Blanks ignored"]["progress"] == 100
    assert (rows["Pictures"]["progress"], rows["Pictures"]["has_cover"]) == (100, True)


def test_moving_series_appends_and_leaves_volume(app_client, db, me, make_series, make_doc):
    a, b = make_series(me, "A"), make_series(me, "B")
    vol = Volume(series_id=a.id, title="V")
    db.add(vol)
    db.flush()
    make_doc(me, series=b, order=7)
    doc = make_doc(me, series=a, order=1, volume=vol)
    body = app_client.patch(f"/documents/{doc.id}", json={"series_id": b.id}).json()
    assert (body["series_id"], body["series_order"], body["volume_id"]) == (b.id, 8, None)


def test_patch_volume_of_another_series_is_422(app_client, db, me, make_series, make_doc):
    a, b = make_series(me, "A"), make_series(me, "B")
    vol = Volume(series_id=b.id, title="V")
    db.add(vol)
    db.flush()
    doc = make_doc(me, series=a)
    assert app_client.patch(f"/documents/{doc.id}", json={"volume_id": vol.id}).status_code == 422


def test_patch_null_title_is_422(app_client, me, make_doc):
    doc = make_doc(me)
    assert app_client.patch(f"/documents/{doc.id}", json={"title": None}).status_code == 422


def test_delete_removes_document_and_lines(app_client, db, me, make_doc):
    doc = make_doc(me, ["a"])
    assert app_client.delete(f"/documents/{doc.id}").status_code == 204
    assert app_client.get(f"/documents/{doc.id}").status_code == 404
    assert _lines(db, doc.id) == []


@pytest.mark.parametrize(
    ("method", "kwargs"), [("get", {}), ("patch", {"json": {"title": "x"}}), ("delete", {})]
)
def test_another_users_document_is_404(app_client, me, make_user, make_doc, method, kwargs):
    theirs = make_doc(make_user(email="other@example.com"), ["x"])
    assert getattr(app_client, method)(f"/documents/{theirs.id}", **kwargs).status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_documents.py -q`
Expected: FAIL. `/documents` is not routed (404s), and the unauthenticated test gets 404 rather than 401.

- [ ] **Step 3: Write `api/library.py`**

```python
"""Queries shared by the documents, series, restructure, and transfer code."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.core.text import db_rows_to_arrays
from api.models import Document, Line


def next_series_order(db: Session, series_id: int | None) -> int:
    """The slot after the series' last chapter; 0 for a document outside any series."""
    if series_id is None:
        return 0
    return db.scalar(
        select(func.coalesce(func.max(Document.series_order), 0) + 1).where(
            Document.series_id == series_id
        )
    )


def write_lines(db: Session, document_id: int, rows: list[dict]) -> None:
    """Insert ``lines_to_db_rows()`` output. Its blank-line prefix ``""`` is stored as
    ``"%"`` (the column holds % or $); ``line_arrays()`` turns it back into ``""``."""
    db.add_all(
        Line(
            document_id=document_id,
            line_number=row["line_number"],
            prefix=row["prefix"] or "%",
            raw_text=row["raw_text"],
            translated_text=row["translated_text"],
        )
        for row in rows
    )
    db.flush()


def line_arrays(db: Session, document_id: int) -> tuple[list[str], list[str]]:
    """(raw_lines, translated_lines) in the shape the ported text functions expect.

    A blank line comes back as ``""`` rather than ``"%"``, so the Markdown builders emit
    a paragraph break for it and a TXT export re-imports to the same lines."""
    rows = db.execute(
        select(Line.prefix, Line.raw_text, Line.translated_text)
        .where(Line.document_id == document_id)
        .order_by(Line.line_number)
    )
    return db_rows_to_arrays([
        {"line_number": i, "prefix": prefix if raw else "", "raw_text": raw,
         "translated_text": translated}
        for i, (prefix, raw, translated) in enumerate(rows)
    ])
```

- [ ] **Step 4: Write `api/schemas/documents.py`**

```python
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import Patch, Title

# A long web-novel chapter is ~30k characters; this bounds a pasted body well above that.
MAX_RAW_CHARS = 1_000_000


class DocumentCreate(BaseModel):
    title: Title
    chapter_title: str = ""
    series_id: int | None = None
    volume_id: int | None = None
    source_url: str = ""
    source_language: str = Field(default="ja", min_length=2, max_length=16)
    raw_text: str = Field(default="", max_length=MAX_RAW_CHARS)


class DocumentUpdate(Patch):
    NULLABLE: ClassVar[frozenset[str]] = frozenset({"series_id", "volume_id"})

    title: Title | None = None
    chapter_title: str | None = None
    series_id: int | None = None
    volume_id: int | None = None
    source_url: str | None = None
    source_language: str | None = Field(default=None, min_length=2, max_length=16)
    last_position: int | None = Field(default=None, ge=0)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    chapter_title: str
    series_id: int | None
    volume_id: int | None
    series_order: int
    source_language: str
    source_url: str
    last_position: int
    wp_status: str
    wp_post_url: str
    created_at: datetime
    updated_at: datetime


class DocumentListItem(DocumentOut):
    """A picker row: the document plus what the picker shows about its progress."""

    line_count: int
    translated_count: int
    image_count: int
    has_cover: bool
    progress: int
```

- [ ] **Step 5: Write `api/routers/documents.py`**

```python
from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.core.text import build_new_file, lines_to_db_rows, parse_file_content
from api.deps import current_user, db_session, owned_ref, scoped
from api.library import next_series_order, write_lines
from api.models import Document, DocumentImage, Line, Series, User, Volume
from api.routing import api_router
from api.schemas.documents import (
    DocumentCreate,
    DocumentListItem,
    DocumentOut,
    DocumentUpdate,
)

router = api_router(prefix="/documents", tags=["documents"])


def progress(line_count: int, translated_count: int, image_count: int) -> int:
    """The desktop list_documents rule; an illustration-only chapter counts as done."""
    if line_count == 0:
        return 100 if image_count else 0
    return translated_count * 100 // line_count


def check_placement(
    db: Session, user_id: int, series_id: int | None, volume_id: int | None
) -> None:
    """A (series, volume) pair named in a request body must be the caller's and agree."""
    if series_id is not None:
        owned_ref(db, Series, series_id, user_id, "series_id")
    if volume_id is None:
        return
    volume = db.get(Volume, volume_id)
    if series_id is None or volume is None or volume.series_id != series_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "volume_id: not a volume of that series"
        )


@router.get("", response_model=list[DocumentListItem])
def list_documents(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[DocumentListItem]:
    """Every document the caller owns, most recently edited first; the picker groups
    by series_id and filters client-side."""
    # ponytail: one unpaginated list; page it if a library outgrows a few thousand chapters
    has_text = func.trim(Line.raw_text) != ""
    lines = (
        select(
            Line.document_id,
            func.count().filter(has_text).label("line_count"),
            func.count().filter(has_text, Line.translated_text != "").label("translated_count"),
        )
        .group_by(Line.document_id)
        .subquery()
    )
    images = (
        select(
            DocumentImage.document_id,
            func.count().label("image_count"),
            func.bool_or(DocumentImage.is_cover).label("has_cover"),
        )
        .group_by(DocumentImage.document_id)
        .subquery()
    )
    rows = db.execute(
        select(
            Document,
            func.coalesce(lines.c.line_count, 0),
            func.coalesce(lines.c.translated_count, 0),
            func.coalesce(images.c.image_count, 0),
            func.coalesce(images.c.has_cover, False),
        )
        .outerjoin(lines, lines.c.document_id == Document.id)
        .outerjoin(images, images.c.document_id == Document.id)
        .where(Document.user_id == user.id)
        .order_by(Document.updated_at.desc(), Document.id.desc())
    )
    return [
        DocumentListItem(
            **DocumentOut.model_validate(doc).model_dump(),
            line_count=lc,
            translated_count=tc,
            image_count=ic,
            has_cover=hc,
            progress=progress(lc, tc, ic),
        )
        for doc, lc, tc, ic, hc in rows
    ]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Document:
    return scoped(db, Document, document_id, user.id)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(
    body: DocumentCreate, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Document:
    """The desktop "New document" dialog: pasted source text is split into sentence
    lines by the ported build_new_file."""
    check_placement(db, user.id, body.series_id, body.volume_id)
    doc = Document(
        user_id=user.id,
        series_order=next_series_order(db, body.series_id),
        **body.model_dump(exclude={"raw_text"}),
    )
    db.add(doc)
    db.flush()
    if body.raw_text.strip():
        raw, translated, _ = parse_file_content(build_new_file(body.raw_text))
        write_lines(db, doc.id, lines_to_db_rows(raw, translated))
    return doc


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: int,
    body: DocumentUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Document:
    doc = scoped(db, Document, document_id, user.id)
    changes = body.model_dump(exclude_unset=True)
    series_id = changes.get("series_id", doc.series_id)
    moving = series_id != doc.series_id
    if moving:
        # A chapter changing series leaves its old volume unless the body names a new one.
        changes.setdefault("volume_id", None)
    check_placement(db, user.id, series_id, changes.get("volume_id", doc.volume_id))
    if moving:
        changes["series_order"] = next_series_order(db, series_id)
    for field, value in changes.items():
        setattr(doc, field, value)
    db.flush()
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    db.delete(scoped(db, Document, document_id, user.id))
    db.flush()
```

- [ ] **Step 6: Register the router in `api/main.py`**

Add `documents` to the `from api.routers import ...` line (keep it sorted) and `app.include_router(documents.router)` after the series line.

- [ ] **Step 7: Run the tests and lint**

Run: `pytest tests/test_documents.py tests/test_commit_boundary.py -q && ruff check .`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add api/library.py api/schemas/documents.py api/routers/documents.py api/main.py tests/test_documents.py
git commit -m "feat(documents): document CRUD and the picker listing with progress"
```

---

### Task 4: Volumes, chapter assignment, and covers

**Files:**
- Create: `api/uploads.py`, `api/schemas/volumes.py`, `api/routers/volumes.py`
- Modify: `api/deps.py` (add `scoped_volume`), `api/schemas/documents.py` (add `DocumentIds`), `api/main.py`
- Test: `tests/test_volumes.py`

**Interfaces:**
- Consumes: `scoped`, `conflict`, `DocumentOut`, fixtures `me`, `make_series`, `make_doc`.
- Produces:
  - `api.deps.scoped_volume(db, volume_id, user_id) -> Volume`: 404 when missing or foreign.
  - `api.uploads.read_capped(upload, limit) -> bytes`: 413 over the limit.
  - `api.uploads.sniff_image(data) -> str | None`: returns `"png"`, `"jpg"`, `"gif"`, `"webp"`, or `None`.
  - `api.schemas.documents.DocumentIds` (`document_ids: list[int]`, at least 1).
  - `api.schemas.volumes.VolumeCreate`, `VolumeUpdate`, `VolumeOut`, `CoverOut`.
  - `api.routers.volumes.router` (no prefix) and `MAX_IMAGE_BYTES`.

- [ ] **Step 1: Write the failing tests in `tests/test_volumes.py`**

```python
import pytest
from sqlalchemy import select

from api.models import Document, DocumentImage, Volume

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def series(me, make_series):
    return make_series(me)


def _volume(client, series, title="V1"):
    return client.post(f"/series/{series.id}/volumes", json={"title": title})


def test_create_appends_volume_order_and_lists_in_order(app_client, series):
    a, b = _volume(app_client, series, "V1"), _volume(app_client, series, "V2")
    assert (a.status_code, a.json()["volume_order"], b.json()["volume_order"]) == (201, 1, 2)
    listed = app_client.get(f"/series/{series.id}/volumes").json()
    assert [v["title"] for v in listed] == ["V1", "V2"]


def test_duplicate_title_in_series_is_409(app_client, series):
    _volume(app_client, series)
    assert _volume(app_client, series).status_code == 409


def test_same_title_in_another_series_is_fine(app_client, me, make_series, series):
    _volume(app_client, series)
    assert _volume(app_client, make_series(me, "Other")).status_code == 201


def test_patch_sets_epub_metadata(app_client, series):
    vid = _volume(app_client, series).json()["id"]
    r = app_client.patch(f"/volumes/{vid}", json={"epub_author": "Author", "epub_language": "ja"})
    assert (r.json()["epub_author"], r.json()["epub_language"]) == ("Author", "ja")


def test_rename_onto_existing_is_409(app_client, series):
    _volume(app_client, series, "V1")
    vid = _volume(app_client, series, "V2").json()["id"]
    assert app_client.patch(f"/volumes/{vid}", json={"title": "V1"}).status_code == 409


def test_delete_volume_unassigns_chapters(app_client, db, me, series, make_doc):
    vol = Volume(series_id=series.id, title="V")
    db.add(vol)
    db.flush()
    doc = make_doc(me, series=series, volume=vol)
    assert app_client.delete(f"/volumes/{vol.id}").status_code == 204
    db.expire_all()
    assert db.get(Document, doc.id).volume_id is None


def test_assign_chapters(app_client, me, series, make_doc):
    vid = _volume(app_client, series).json()["id"]
    a, b = make_doc(me, series=series, order=1), make_doc(me, series=series, order=2)
    r = app_client.post(f"/volumes/{vid}/documents", json={"document_ids": [b.id, a.id]})
    assert r.status_code == 200
    assert [(d["id"], d["volume_id"]) for d in r.json()] == [(a.id, vid), (b.id, vid)]


@pytest.mark.parametrize("stray_owner", ["me", "other"])
def test_assign_refuses_strays_and_changes_nothing(
    app_client, db, me, make_user, make_series, series, make_doc, stray_owner
):
    vid = _volume(app_client, series).json()["id"]
    mine = make_doc(me, series=series)
    if stray_owner == "me":
        stray = make_doc(me, series=make_series(me, "Other"))
    else:
        stray = make_doc(make_user(email="other@example.com"))
    r = app_client.post(f"/volumes/{vid}/documents", json={"document_ids": [mine.id, stray.id]})
    assert r.status_code == 422
    db.expire_all()
    assert db.get(Document, mine.id).volume_id is None


def test_cover_upload_replaces_the_previous_one(app_client, db, me, make_doc):
    doc = make_doc(me, ["a"])
    for _ in range(2):
        r = app_client.put(
            f"/documents/{doc.id}/cover", files={"file": ("c.png", PNG, "image/png")}
        )
        assert r.status_code == 200
    covers = db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc.id)).all()
    assert [(c.is_cover, c.src_path, c.anchor_position) for c in covers] == [
        (True, "cover.png", 0)
    ]


def test_cover_must_really_be_an_image(app_client, me, make_doc):
    doc = make_doc(me)
    r = app_client.put(
        f"/documents/{doc.id}/cover", files={"file": ("c.png", b"<svg/>", "image/png")}
    )
    assert r.status_code == 415


def test_cover_size_is_capped(app_client, me, make_doc, monkeypatch):
    from api.routers import volumes

    monkeypatch.setattr(volumes, "MAX_IMAGE_BYTES", 8)
    doc = make_doc(me)
    r = app_client.put(f"/documents/{doc.id}/cover", files={"file": ("c.png", PNG, "image/png")})
    assert r.status_code == 413


def test_clear_cover_is_idempotent(app_client, db, me, make_doc):
    doc = make_doc(me)
    app_client.put(f"/documents/{doc.id}/cover", files={"file": ("c.png", PNG, "image/png")})
    assert app_client.delete(f"/documents/{doc.id}/cover").status_code == 204
    assert app_client.delete(f"/documents/{doc.id}/cover").status_code == 204
    assert db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc.id)).all() == []


@pytest.fixture
def theirs(db, me, make_user, make_series, make_doc):
    other = make_user(email="other@example.com")
    series = make_series(other, "Theirs")
    volume = Volume(series_id=series.id, title="V")
    db.add(volume)
    db.flush()
    return {"series": series.id, "volume": volume.id, "doc": make_doc(other, ["x"]).id}


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/series/{series}/volumes", {}),
        ("POST", "/series/{series}/volumes", {"json": {"title": "V2"}}),
        ("PATCH", "/volumes/{volume}", {"json": {"title": "x"}}),
        ("DELETE", "/volumes/{volume}", {}),
        ("POST", "/volumes/{volume}/documents", {"json": {"document_ids": [1]}}),
        ("PUT", "/documents/{doc}/cover", {"files": {"file": ("c.png", PNG, "image/png")}}),
        ("DELETE", "/documents/{doc}/cover", {}),
    ],
)
def test_another_users_objects_are_404(app_client, theirs, method, path, kwargs):
    assert app_client.request(method, path.format(**theirs), **kwargs).status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_volumes.py -q`
Expected: FAIL with 404 or 405 responses, since none of these routes exist.

- [ ] **Step 3: Add `scoped_volume` to `api/deps.py`**

Extend the models import to `from api.models import Series, User, Volume` (keeping `Session as SessionRow` on its own line), then append:

```python
def scoped_volume(db: Session, volume_id: int, user_id: int) -> Volume:
    """A volume is owned through its series; 404 for missing and foreign alike."""
    volume = db.scalar(
        select(Volume).join(Series).where(Volume.id == volume_id, Series.user_id == user_id)
    )
    if volume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return volume
```

- [ ] **Step 4: Write `api/uploads.py`**

```python
"""Reading uploads: a hard size cap, and image types decided by content, not by the
client's Content-Type."""

from fastapi import HTTPException, UploadFile, status


def read_capped(upload: UploadFile, limit: int) -> bytes:
    """The upload's bytes, or 413 if it is larger than ``limit``.

    Starlette has already spooled the body (to disk past 1 MB), so this bounds what
    reaches memory and the database, not what crossed the network.
    # ponytail: the proxy should cap request bodies too; that arrives with Caddy in phase 3
    """
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"upload exceeds {limit} bytes")
    return data


def sniff_image(data: bytes) -> str | None:
    """The file extension for a PNG, JPEG, GIF, or WebP, judged by magic bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None
```

- [ ] **Step 5: Add `DocumentIds` to `api/schemas/documents.py`**

Append:

```python
class DocumentIds(BaseModel):
    document_ids: list[int] = Field(min_length=1)
```

- [ ] **Step 6: Write `api/schemas/volumes.py`**

```python
from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import Patch, Title


class VolumeCreate(BaseModel):
    title: Title
    volume_order: int | None = Field(default=None, ge=0)  # None: after the last volume
    epub_title: str = ""
    epub_author: str = ""
    epub_language: str = Field(default="en", min_length=2, max_length=16)
    epub_description: str = ""
    epub_illustrator: str = ""
    epub_publisher: str = ""
    epub_identifier: str = ""


class VolumeUpdate(Patch):
    title: Title | None = None
    volume_order: int | None = Field(default=None, ge=0)
    epub_title: str | None = None
    epub_author: str | None = None
    epub_language: str | None = Field(default=None, min_length=2, max_length=16)
    epub_description: str | None = None
    epub_illustrator: str | None = None
    epub_publisher: str | None = None
    epub_identifier: str | None = None


class VolumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    title: str
    volume_order: int
    epub_title: str
    epub_author: str
    epub_language: str
    epub_description: str
    epub_illustrator: str
    epub_publisher: str
    epub_identifier: str


class CoverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    src_path: str
```

- [ ] **Step 7: Write `api/routers/volumes.py`**

```python
from fastapi import Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, scoped, scoped_volume
from api.errors import conflict
from api.models import Document, DocumentImage, Series, User, Volume
from api.routing import api_router
from api.schemas.documents import DocumentIds, DocumentOut
from api.schemas.volumes import CoverOut, VolumeCreate, VolumeOut, VolumeUpdate
from api.uploads import read_capped, sniff_image

router = api_router(tags=["volumes"])

TITLE_TAKEN = "a volume with that title exists in this series"
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@router.get("/series/{series_id}/volumes", response_model=list[VolumeOut])
def list_volumes(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[Volume]:
    series = scoped(db, Series, series_id, user.id)
    return list(
        db.scalars(
            select(Volume)
            .where(Volume.series_id == series.id)
            .order_by(Volume.volume_order, Volume.id)
        )
    )


@router.post(
    "/series/{series_id}/volumes", response_model=VolumeOut, status_code=status.HTTP_201_CREATED
)
def create_volume(
    series_id: int,
    body: VolumeCreate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Volume:
    series = scoped(db, Series, series_id, user.id)
    order = body.volume_order
    if order is None:
        order = db.scalar(
            select(func.coalesce(func.max(Volume.volume_order), 0) + 1).where(
                Volume.series_id == series.id
            )
        )
    volume = Volume(
        series_id=series.id, volume_order=order, **body.model_dump(exclude={"volume_order"})
    )
    try:
        with db.begin_nested():
            db.add(volume)
    except IntegrityError as exc:
        raise conflict(exc, TITLE_TAKEN) from exc
    return volume


@router.patch("/volumes/{volume_id}", response_model=VolumeOut)
def update_volume(
    volume_id: int,
    body: VolumeUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Volume:
    volume = scoped_volume(db, volume_id, user.id)
    try:
        with db.begin_nested():
            for field, value in body.model_dump(exclude_unset=True).items():
                setattr(volume, field, value)
    except IntegrityError as exc:
        raise conflict(exc, TITLE_TAKEN) from exc
    return volume


@router.delete("/volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_volume(
    volume_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    """Chapters survive, unassigned: documents.volume_id is ON DELETE SET NULL."""
    db.delete(scoped_volume(db, volume_id, user.id))
    db.flush()


@router.post("/volumes/{volume_id}/documents", response_model=list[DocumentOut])
def assign_documents(
    volume_id: int,
    body: DocumentIds,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[Document]:
    """Put chapters of the volume's series into it. All or nothing."""
    volume = scoped_volume(db, volume_id, user.id)
    wanted = set(body.document_ids)
    docs = list(
        db.scalars(
            select(Document)
            .where(
                Document.id.in_(wanted),
                Document.user_id == user.id,
                Document.series_id == volume.series_id,
            )
            .order_by(Document.series_order, Document.id)
        )
    )
    if len(docs) != len(wanted):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "document_ids: every chapter must be yours and in this volume's series",
        )
    for doc in docs:
        doc.volume_id = volume.id
    db.flush()
    return docs


@router.put("/documents/{document_id}/cover", response_model=CoverOut)
def set_cover(
    document_id: int,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> DocumentImage:
    """Designate a chapter's cover (the desktop replace_document_cover): any previous
    cover on the chapter is replaced."""
    doc = scoped(db, Document, document_id, user.id)
    data = read_capped(file, MAX_IMAGE_BYTES)
    ext = sniff_image(data)
    if ext is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "cover must be a PNG, JPEG, GIF or WebP image"
        )
    db.execute(
        delete(DocumentImage).where(DocumentImage.document_id == doc.id, DocumentImage.is_cover)
    )
    cover = DocumentImage(
        document_id=doc.id, anchor_position=0, is_cover=True, src_path=f"cover.{ext}", data=data
    )
    db.add(cover)
    db.flush()
    return cover


@router.delete("/documents/{document_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
def clear_cover(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    doc = scoped(db, Document, document_id, user.id)
    db.execute(
        delete(DocumentImage).where(DocumentImage.document_id == doc.id, DocumentImage.is_cover)
    )
```

- [ ] **Step 8: Register the router in `api/main.py`**

Add `volumes` to the sorted import and `app.include_router(volumes.router)` after the documents line.

- [ ] **Step 9: Run the tests and lint**

Run: `pytest tests/test_volumes.py tests/test_commit_boundary.py -q && ruff check .`
Expected: all pass

- [ ] **Step 10: Commit**

```bash
git add api/deps.py api/uploads.py api/schemas/documents.py api/schemas/volumes.py api/routers/volumes.py api/main.py tests/test_volumes.py
git commit -m "feat(volumes): volume CRUD, chapter assignment, and sniffed cover uploads"
```

---

### Task 5: Chapter reorder and renumber by title

**Files:**
- Modify: `api/library.py`, `api/routers/series.py`
- Test: `tests/test_series.py` (append)

**Interfaces:**
- Consumes: `natural_key` (`api.core.text`), `DocumentIds`, `DocumentOut`, `scoped`.
- Produces:
  - `api.library.chapters(db, series_id) -> list[Document]`, ordered by `(series_order, id)`.
  - `api.library.renumber(docs: list[Document]) -> None`: sets `series_order` to 1..N in list order without flushing.
  - `PUT /series/{id}/order` and `POST /series/{id}/renumber`. Both return `list[DocumentOut]` in the new order.

- [ ] **Step 1: Append the failing tests to `tests/test_series.py`**

```python
def test_reorder_sets_the_given_order(app_client, me, make_series, make_doc):
    s = make_series(me)
    a, b, c = (make_doc(me, series=s, order=i, title=t) for i, t in [(1, "A"), (2, "B"), (3, "C")])
    r = app_client.put(f"/series/{s.id}/order", json={"document_ids": [c.id, a.id, b.id]})
    assert [(d["title"], d["series_order"]) for d in r.json()] == [("C", 1), ("A", 2), ("B", 3)]


@pytest.mark.parametrize("case", ["missing_one", "duplicate", "foreign"])
def test_reorder_needs_exactly_the_series_chapters(
    app_client, db, me, make_user, make_series, make_doc, case
):
    s = make_series(me)
    a, b = make_doc(me, series=s, order=1), make_doc(me, series=s, order=2)
    stranger = make_doc(make_user(email="other@example.com"), ["x"])
    ids = {
        "missing_one": [b.id],
        "duplicate": [a.id, a.id, b.id],
        "foreign": [b.id, a.id, stranger.id],
    }[case]
    assert app_client.put(f"/series/{s.id}/order", json={"document_ids": ids}).status_code == 422
    db.expire_all()
    assert (db.get(Document, a.id).series_order, db.get(Document, b.id).series_order) == (1, 2)


def test_renumber_sorts_titles_naturally(app_client, me, make_series, make_doc):
    s = make_series(me)
    for order, title in enumerate(["Ch 10", "Ch 2", "Ch 1"], start=1):
        make_doc(me, series=s, order=order, title=title)
    r = app_client.post(f"/series/{s.id}/renumber")
    assert [(d["chapter_title"], d["series_order"]) for d in r.json()] == [
        ("Ch 1", 1), ("Ch 2", 2), ("Ch 10", 3),
    ]


def test_renumber_falls_back_to_title(app_client, db, me, make_series, make_doc):
    s = make_series(me)
    make_doc(me, series=s, order=1, title="B")
    untitled = make_doc(me, series=s, order=2, title="A")
    untitled.chapter_title = ""
    db.flush()
    r = app_client.post(f"/series/{s.id}/renumber")
    assert [d["title"] for d in r.json()] == ["A", "B"]


@pytest.mark.parametrize(
    ("method", "suffix", "kwargs"),
    [("put", "/order", {"json": {"document_ids": [1]}}), ("post", "/renumber", {})],
)
def test_another_users_series_order_is_404(
    app_client, me, make_user, make_series, method, suffix, kwargs
):
    theirs = make_series(make_user(email="other@example.com"), "Theirs")
    r = getattr(app_client, method)(f"/series/{theirs.id}{suffix}", **kwargs)
    assert r.status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_series.py -q -k "reorder or renumber"`
Expected: FAIL with 404 or 405, since the routes are missing.

- [ ] **Step 3: Add `chapters` and `renumber` to `api/library.py`**

Append:

```python
def chapters(db: Session, series_id: int) -> list[Document]:
    """A series' chapters in reading order (ties broken by id, as the desktop does)."""
    return list(
        db.scalars(
            select(Document)
            .where(Document.series_id == series_id)
            .order_by(Document.series_order, Document.id)
        )
    )


def renumber(docs: list[Document]) -> None:
    """Give ``docs`` series_order 1..N in list order (the caller flushes)."""
    for order, doc in enumerate(docs, start=1):
        doc.series_order = order
```

- [ ] **Step 4: Add the two routes to `api/routers/series.py`**

Extend the imports:

```python
from fastapi import Depends, HTTPException, status

from api.core.text import natural_key
from api.library import chapters, renumber
from api.models import Document, Profile, Series, User
from api.schemas.documents import DocumentIds, DocumentOut
```

Append:

```python
@router.put("/{series_id}/order", response_model=list[DocumentOut])
def reorder_chapters(
    series_id: int,
    body: DocumentIds,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[Document]:
    """Drag-and-drop reorder: the body lists every chapter of the series once, in the
    new order. A stale list (a chapter added meanwhile) is refused, not half-applied."""
    series = scoped(db, Series, series_id, user.id)
    by_id = {doc.id: doc for doc in chapters(db, series.id)}
    if sorted(body.document_ids) != sorted(by_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "document_ids must list every chapter of the series exactly once",
        )
    ordered = [by_id[doc_id] for doc_id in body.document_ids]
    renumber(ordered)
    db.flush()
    return ordered


@router.post("/{series_id}/renumber", response_model=list[DocumentOut])
def renumber_by_title(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[Document]:
    """series_order 1..N by natural sort ("Ch 2" before "Ch 10") of the title the
    desktop displays: chapter_title, else title."""
    series = scoped(db, Series, series_id, user.id)
    ordered = sorted(chapters(db, series.id), key=lambda d: natural_key(d.chapter_title or d.title))
    renumber(ordered)
    db.flush()
    return ordered
```

- [ ] **Step 5: Run the tests and lint**

Run: `pytest tests/test_series.py -q && ruff check .`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add api/library.py api/routers/series.py tests/test_series.py
git commit -m "feat(series): drag-and-drop chapter reorder and natural renumber by title"
```

---

### Task 6: Merge and split

**Files:**
- Create: `api/restructure.py`
- Modify: `api/schemas/documents.py` (merge and split bodies), `api/routers/documents.py` (two routes)
- Test: `tests/test_restructure.py`

**Interfaces:**
- Consumes: `chapters`, `renumber` (`api.library`); models `Document`, `Line`, `DocumentImage`, `Volume`; fixtures `make_user`, `make_series`, `make_doc`, `me`.
- Produces:
  - `api.restructure.merge_documents(db, user_id, doc_ids: list[int], merged_title: str) -> Document`: the survivor.
  - `api.restructure.split_document(db, user_id, doc_id, cuts: list[tuple[int, str]]) -> list[Document]`: `[original, new, ...]`.
  - `RestructureError(ValueError)`, which maps to 422, and `NotOwned(Exception)`, which maps to 404.
  - `MergeRequest`, `SplitCut`, `SplitRequest`.
  - `POST /documents/merge` returns `DocumentOut`. `POST /documents/{id}/split` returns `list[DocumentOut]`.

The service tests are the desktop's `tests/test_db.py` merge and split tests (lines 1586–1850 at `f1a96ce`), rewritten against this schema. They are kept one for one, so the ported behaviour can be checked against the reference. Tests marked `# new` pin the two improvements and the tenancy rule.

- [ ] **Step 1: Write the failing tests in `tests/test_restructure.py`**

```python
"""Merge and split: the desktop reference tests plus what this port fixes (# new)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update

from api.models import Document, DocumentImage, Line, Volume
from api.restructure import NotOwned, RestructureError, merge_documents, split_document

T1 = datetime(2026, 1, 1, tzinfo=UTC)
T2 = datetime(2026, 2, 2, tzinfo=UTC)


@pytest.fixture
def user(make_user):
    return make_user()


@pytest.fixture
def series(user, make_series):
    return make_series(user)


@pytest.fixture
def chapter(db, user, series, make_doc):
    """chapter(title, order, raws, prefixes=None) -> Document in `series`."""

    def _make(title, order, raws, prefixes=None):
        doc = make_doc(user, raws, series=series, order=order, title=title)
        for i, prefix in enumerate(prefixes or []):
            db.execute(
                update(Line)
                .where(Line.document_id == doc.id, Line.line_number == i)
                .values(prefix=prefix)
            )
        return doc

    return _make


def col(db, doc_id, field="raw_text"):
    return list(
        db.scalars(
            select(getattr(Line, field))
            .where(Line.document_id == doc_id)
            .order_by(Line.line_number)
        )
    )


def images(db, doc_id):
    rows = db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc_id))
    return {img.src_path: img.anchor_position for img in rows}


def add_image(db, doc, anchor, name):
    db.add(DocumentImage(document_id=doc.id, anchor_position=anchor, src_path=name, data=b"x"))
    db.flush()


def stamp(db, doc, when):
    db.execute(update(Line).where(Line.document_id == doc.id).values(translated_at=when))


def orders(db, *docs):
    db.expire_all()
    return {db.get(Document, d.id).chapter_title: db.get(Document, d.id).series_order for d in docs}


# --- merge -----------------------------------------------------------------


def test_merge_concatenates_lines_in_series_order(db, user, chapter):
    a, b = chapter("A", 1, ["a0", "a1"]), chapter("B", 2, ["b0", "b1"])
    target = merge_documents(db, user.id, [b.id, a.id], "Merged")
    assert target.id == a.id
    assert col(db, a.id) == ["a0", "a1", "b0", "b1"]
    assert col(db, a.id, "translated_text") == ["tr:a0", "tr:a1", "tr:b0", "tr:b1"]


def test_merge_renumbers_lines_contiguously(db, user, chapter):
    a, b = chapter("A", 1, ["a0", "a1"]), chapter("B", 2, ["b0"])
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert col(db, a.id, "line_number") == [0, 1, 2]


def test_merge_forces_paragraph_prefix_at_boundary(db, user, chapter):
    a, b = chapter("A", 1, ["a0"]), chapter("B", 2, ["b0", "b1"], prefixes=["$", "$"])
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert col(db, a.id, "prefix") == ["%", "%", "$"]


def test_merge_reanchors_images(db, user, chapter):
    a, b = chapter("A", 1, ["a0", "a1", "a2"]), chapter("B", 2, ["b0", "b1"])
    add_image(db, a, 1, "a.png")
    add_image(db, b, 0, "b.png")
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert images(db, a.id) == {"a.png": 1, "b.png": 3}


def test_merge_deletes_source_documents(db, user, chapter):
    a, b = chapter("A", 1, ["a0"]), chapter("B", 2, ["b0"])
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert db.get(Document, b.id) is None


def test_merge_sets_merged_title_and_keeps_target_wp_fields(db, user, chapter):
    a, b = chapter("A", 1, ["a0"]), chapter("B", 2, ["b0"])
    a.wp_status, a.wp_post_url = "publish", "http://x/a"
    b.wp_status, b.wp_post_url = "publish", "http://x/b"
    db.flush()
    target = merge_documents(db, user.id, [a.id, b.id], "Combined Chapter")
    assert (target.chapter_title, target.wp_status, target.wp_post_url) == (
        "Combined Chapter", "publish", "http://x/a",
    )


def test_merge_compacts_series_order(db, user, chapter):
    a, b, c, d = (chapter(t, i, [t]) for i, t in enumerate("ABCD", start=1))
    merge_documents(db, user.id, [b.id, c.id], "BC")
    assert orders(db, a, b, d) == {"A": 1, "BC": 2, "D": 3}


def test_merge_three_way(db, user, chapter):
    a, b, c = chapter("A", 1, ["a0"]), chapter("B", 2, ["b0"]), chapter("C", 3, ["c0"])
    assert merge_documents(db, user.id, [c.id, a.id, b.id], "ABC").id == a.id
    assert col(db, a.id) == ["a0", "b0", "c0"]


def test_merge_rejects_a_single_document(db, user, chapter):
    with pytest.raises(RestructureError):
        merge_documents(db, user.id, [chapter("A", 1, ["a0"]).id], "Merged")


def test_merge_rejects_mixed_series(db, user, chapter, make_series, make_doc):
    a = chapter("A", 1, ["a0"])
    b = make_doc(user, ["b0"], series=make_series(user, "S2"), order=1)
    with pytest.raises(RestructureError):
        merge_documents(db, user.id, [a.id, b.id], "Merged")


def test_merge_rejects_a_document_listed_twice(db, user, chapter):  # new
    a = chapter("A", 1, ["a0"])
    with pytest.raises(RestructureError):
        merge_documents(db, user.id, [a.id, a.id], "Merged")


def test_merge_keeps_every_lines_translated_at(db, user, chapter):  # new
    a, b = chapter("A", 1, ["a0", "a1"]), chapter("B", 2, ["b0"])
    stamp(db, a, T1)
    stamp(db, b, T2)
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert col(db, a.id, "translated_at") == [T1, T1, T2]


def test_merge_with_a_foreign_document_changes_nothing(  # new
    db, user, chapter, make_user, make_doc
):
    a = chapter("A", 1, ["a0"])
    theirs = make_doc(make_user(email="other@example.com"), ["z"])
    with pytest.raises(NotOwned):
        merge_documents(db, user.id, [a.id, theirs.id], "Merged")
    assert col(db, a.id) == ["a0"]
    assert col(db, theirs.id) == ["z"]


# --- split -----------------------------------------------------------------


def test_split_partitions_lines_at_cut(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3"])
    first, second = split_document(db, user.id, doc.id, [(2, "Part 2")])
    assert first.id == doc.id
    assert (col(db, doc.id), col(db, second.id)) == (["l0", "l1"], ["l2", "l3"])


def test_split_renumbers_each_segment_from_zero(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3", "l4"])
    _, p2, p3 = split_document(db, user.id, doc.id, [(2, "P2"), (4, "P3")])
    assert (col(db, p2.id, "line_number"), col(db, p3.id, "line_number")) == ([0, 1], [0])


def test_split_preserves_translations_by_index(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3"])
    _, second = split_document(db, user.id, doc.id, [(2, "P2")])
    assert col(db, doc.id, "translated_text") == ["tr:l0", "tr:l1"]
    assert col(db, second.id, "translated_text") == ["tr:l2", "tr:l3"]


def test_split_forces_paragraph_prefix_at_segment_head(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2"], prefixes=["%", "$", "$"])
    _, second = split_document(db, user.id, doc.id, [(1, "P2")])
    assert col(db, second.id, "prefix") == ["%", "$"]


def test_split_reanchors_images_to_owning_segment(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3"])
    add_image(db, doc, 0, "a.png")
    add_image(db, doc, 3, "b.png")
    _, second = split_document(db, user.id, doc.id, [(2, "P2")])
    assert (images(db, doc.id), images(db, second.id)) == ({"a.png": 0}, {"b.png": 1})


def test_split_moves_an_end_anchored_image_to_the_last_segment(db, user, chapter):  # new
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3"])
    add_image(db, doc, 4, "closing.png")  # anchored after the last line
    _, second = split_document(db, user.id, doc.id, [(2, "P2")])
    assert (images(db, doc.id), images(db, second.id)) == ({}, {"closing.png": 2})


def test_split_new_segment_takes_typed_title(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1"])
    _, second = split_document(db, user.id, doc.id, [(1, "Second Half")])
    assert (second.title, second.chapter_title) == ("Second Half", "Second Half")


def test_split_blank_title_autonames(db, user, chapter):
    doc = chapter("My Chapter", 1, ["l0", "l1", "l2"])
    _, p2, p3 = split_document(db, user.id, doc.id, [(1, ""), (2, "  ")])
    assert (p2.chapter_title, p3.chapter_title) == ("My Chapter (2)", "My Chapter (3)")


def test_split_original_keeps_wp_fields_new_segments_unpublished(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1"])
    doc.wp_status, doc.wp_post_url = "publish", "http://x/1"
    db.flush()
    first, second = split_document(db, user.id, doc.id, [(1, "P2")])
    assert (first.wp_status, first.wp_post_url) == ("publish", "http://x/1")
    assert (second.wp_status, second.wp_post_url) == ("", "")


def test_split_new_segments_inherit_volume(db, user, series, make_doc):
    vol = Volume(series_id=series.id, title="Vol 1")
    db.add(vol)
    db.flush()
    doc = make_doc(user, ["l0", "l1", "l2", "l3"], series=series, order=1, volume=vol)
    _, second = split_document(db, user.id, doc.id, [(2, "P2")])
    assert (second.series_id, second.volume_id) == (series.id, vol.id)


def test_split_inserts_segments_after_original_in_series_order(db, user, chapter):
    a = chapter("A", 1, ["a0"])
    src = chapter("Src", 2, ["s0", "s1", "s2"])
    c = chapter("C", 3, ["c0"])
    _, s2, s3 = split_document(db, user.id, src.id, [(1, "Src2"), (2, "Src3")])
    assert orders(db, a, src, s2, s3, c) == {"A": 1, "Src": 2, "Src2": 3, "Src3": 4, "C": 5}


def test_split_three_way(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3", "l4", "l5"])
    segments = split_document(db, user.id, doc.id, [(2, "P2"), (4, "P3")])
    assert [col(db, s.id) for s in segments] == [["l0", "l1"], ["l2", "l3"], ["l4", "l5"]]


def test_split_keeps_every_lines_translated_at(db, user, chapter):  # new
    doc = chapter("Ch1", 1, ["l0", "l1", "l2"])
    stamp(db, doc, T1)
    _, second = split_document(db, user.id, doc.id, [(1, "P2")])
    assert col(db, second.id, "translated_at") == [T1, T1]


@pytest.mark.parametrize(
    "cuts", [[], [(0, "P")], [(3, "P")], [(2, "P"), (2, "Q")], [(2, "P"), (1, "Q")]]
)
def test_split_rejects_bad_cuts(db, user, chapter, cuts):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2"])
    with pytest.raises(RestructureError):
        split_document(db, user.id, doc.id, cuts)


def test_split_of_a_foreign_document_is_not_owned(db, user, make_user, make_doc):  # new
    theirs = make_doc(make_user(email="other@example.com"), ["a", "b"])
    with pytest.raises(NotOwned):
        split_document(db, user.id, theirs.id, [(1, "P")])


# --- endpoints -------------------------------------------------------------


def test_merge_endpoint(app_client, db, me, make_series, make_doc):
    s = make_series(me)
    a, b = make_doc(me, ["a0"], series=s, order=1), make_doc(me, ["b0"], series=s, order=2)
    r = app_client.post("/documents/merge", json={"document_ids": [a.id, b.id], "title": "AB"})
    assert (r.status_code, r.json()["id"], r.json()["chapter_title"]) == (200, a.id, "AB")
    assert col(db, a.id) == ["a0", "b0"]


def test_merge_endpoint_404s_on_a_foreign_id(app_client, db, me, make_user, make_doc):
    mine = make_doc(me, ["a0"])
    theirs = make_doc(make_user(email="other@example.com"), ["z"])
    r = app_client.post(
        "/documents/merge", json={"document_ids": [mine.id, theirs.id], "title": "AB"}
    )
    assert r.status_code == 404
    assert col(db, theirs.id) == ["z"]


def test_merge_endpoint_422s_on_one_id(app_client, me, make_doc):
    doc = make_doc(me, ["a0"])
    r = app_client.post("/documents/merge", json={"document_ids": [doc.id], "title": "A"})
    assert r.status_code == 422


def test_split_endpoint(app_client, me, make_doc):
    doc = make_doc(me, ["l0", "l1", "l2"])
    r = app_client.post(f"/documents/{doc.id}/split", json={"cuts": [{"start": 1, "title": "B"}]})
    assert r.status_code == 200
    assert [d["chapter_title"] for d in r.json()] == ["Ch", "B"]


def test_split_endpoint_422s_out_of_range(app_client, me, make_doc):
    doc = make_doc(me, ["l0", "l1"])
    r = app_client.post(f"/documents/{doc.id}/split", json={"cuts": [{"start": 5}]})
    assert r.status_code == 422


def test_split_endpoint_404s_on_a_foreign_document(app_client, me, make_user, make_doc):
    theirs = make_doc(make_user(email="other@example.com"), ["a", "b"])
    r = app_client.post(f"/documents/{theirs.id}/split", json={"cuts": [{"start": 1}]})
    assert r.status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_restructure.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'api.restructure'`

- [ ] **Step 3: Write `api/restructure.py`**

```python
"""Merge and split, ported from the desktop ``Database.merge_documents`` /
``split_document`` (f1a96ce) as the reference behaviour.

One change of method: lines and images are *moved* (UPDATE of document_id and
line_number) rather than deleted and re-inserted, so every line keeps its
``translated_at`` and the stats history survives a restructure. The desktop's
``save_lines`` re-keyed timestamps by line number and lost them.
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from api.library import chapters, renumber
from api.models import Document, DocumentImage, Line


class RestructureError(ValueError):
    """The merge or split cannot be done as asked (the API answers 422)."""


class NotOwned(Exception):
    """A named document is missing or someone else's (the API answers 404)."""


def _line_end(db: Session, document_id: int) -> int:
    """One past the last line number: where appended lines start."""
    return db.scalar(
        select(func.coalesce(func.max(Line.line_number) + 1, 0)).where(
            Line.document_id == document_id
        )
    )


def merge_documents(
    db: Session, user_id: int, doc_ids: list[int], merged_title: str
) -> Document:
    """Merge 2+ chapters of one series into the lowest-series_order one.

    The others' lines are appended in series order (each one's first line forced to a
    '%' paragraph start), their images re-anchored by the same offset, and their rows
    deleted. The survivor keeps its id, volume, and wp_* fields and takes
    ``merged_title`` as its chapter_title; the series is renumbered 1..N.
    Everything is validated before the first write.
    """
    if len(doc_ids) < 2:
        raise RestructureError("merge needs at least two documents")
    if len(set(doc_ids)) != len(doc_ids):
        raise RestructureError("a document is listed twice")
    docs = list(
        db.scalars(
            select(Document).where(Document.id.in_(doc_ids), Document.user_id == user_id)
        )
    )
    if len(docs) != len(doc_ids):
        raise NotOwned
    if len({doc.series_id for doc in docs}) != 1:
        raise RestructureError("cannot merge documents from different series")
    docs.sort(key=lambda doc: (doc.series_order, doc.id))
    target, others = docs[0], docs[1:]

    offset = _line_end(db, target.id)
    for doc in others:
        length = _line_end(db, doc.id)
        db.execute(
            update(Line)
            .where(Line.document_id == doc.id, Line.line_number == 0)
            .values(prefix="%")
        )
        db.execute(
            update(Line)
            .where(Line.document_id == doc.id)
            .values(document_id=target.id, line_number=Line.line_number + offset)
        )
        db.execute(
            update(DocumentImage)
            .where(DocumentImage.document_id == doc.id)
            .values(document_id=target.id, anchor_position=DocumentImage.anchor_position + offset)
        )
        offset += length
    # A bulk delete, not session.delete(): the ORM cascade would also delete any Line
    # objects still sitting in a loaded `doc.lines` collection, which have just moved.
    db.execute(delete(Document).where(Document.id.in_([doc.id for doc in others])))

    target.chapter_title = merged_title
    if target.series_id is not None:
        renumber(chapters(db, target.series_id))
    db.flush()
    db.expire_all()  # loaded line/image collections are stale after the moves
    return target


def split_document(
    db: Session, user_id: int, doc_id: int, cuts: list[tuple[int, str]]
) -> list[Document]:
    """Split one chapter into consecutive segments at ``cuts``.

    ``cuts`` is ``[(start_line_number, title), ...]``, strictly increasing, each
    ``1 <= start <= last line``. Segment 0 stays in ``doc_id`` with its id, title, and
    wp_* fields. Each later segment becomes a new document in the same series and
    volume, titled as given (blank: ``"<chapter title> (n)"``), with its first line
    forced to a '%' paragraph start. Images move with the segment their anchor falls
    in; the last segment also takes any image anchored after the final line (a
    closing illustration), which the desktop left stranded on segment 0. The new
    chapters take the series slots right after the original, and the series is
    renumbered 1..N. Returns ``[original, new, ...]`` in segment order.
    """
    doc = db.scalar(select(Document).where(Document.id == doc_id, Document.user_id == user_id))
    if doc is None:
        raise NotOwned
    if not cuts:
        raise RestructureError("split needs at least one cut")
    starts = [start for start, _ in cuts]
    if starts != sorted(set(starts)):
        raise RestructureError("cut points must be strictly increasing")
    if starts[0] < 1 or starts[-1] > _line_end(db, doc.id) - 1:
        raise RestructureError("cut points out of range")

    siblings = chapters(db, doc.series_id) if doc.series_id is not None else []
    base_name = doc.chapter_title or doc.title
    ends: list[int | None] = [*starts[1:], None]  # None: through the end of the chapter
    new_docs: list[Document] = []
    for n, ((lo, title), hi) in enumerate(zip(cuts, ends, strict=True), start=2):
        name = title.strip() or f"{base_name} ({n})"
        new = Document(
            user_id=user_id,
            series_id=doc.series_id,
            volume_id=doc.volume_id,
            title=name,
            chapter_title=name,
            source_language=doc.source_language,
            series_order=doc.series_order,
        )
        db.add(new)
        db.flush()
        lines = [Line.document_id == doc.id, Line.line_number >= lo]
        anchored = [DocumentImage.document_id == doc.id, DocumentImage.anchor_position >= lo]
        if hi is not None:
            lines.append(Line.line_number < hi)
            anchored.append(DocumentImage.anchor_position < hi)
        db.execute(
            update(Line).where(*lines).values(document_id=new.id, line_number=Line.line_number - lo)
        )
        db.execute(
            update(Line)
            .where(Line.document_id == new.id, Line.line_number == 0)
            .values(prefix="%")
        )
        db.execute(
            update(DocumentImage)
            .where(*anchored)
            .values(document_id=new.id, anchor_position=DocumentImage.anchor_position - lo)
        )
        new_docs.append(new)

    if doc.series_id is not None:
        at = siblings.index(doc) + 1
        renumber([*siblings[:at], *new_docs, *siblings[at:]])
    doc.updated_at = func.now()
    db.flush()
    db.expire_all()
    return [doc, *new_docs]
```

- [ ] **Step 4: Add the request bodies to `api/schemas/documents.py`**

Append:

```python
class MergeRequest(BaseModel):
    document_ids: list[int] = Field(min_length=2)
    title: Title


class SplitCut(BaseModel):
    start: int
    title: str = ""


class SplitRequest(BaseModel):
    cuts: list[SplitCut] = Field(min_length=1)
```

- [ ] **Step 5: Add the two routes to `api/routers/documents.py`**

Extend the imports with `from api.restructure import NotOwned, RestructureError, merge_documents, split_document`, and add `MergeRequest` and `SplitRequest` to the `api.schemas.documents` import. Append:

```python
@router.post("/merge", response_model=DocumentOut)
def merge(
    body: MergeRequest, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Document:
    try:
        return merge_documents(db, user.id, body.document_ids, body.title)
    except NotOwned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found") from None
    except RestructureError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.post("/{document_id}/split", response_model=list[DocumentOut])
def split(
    document_id: int,
    body: SplitRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[Document]:
    cuts = [(cut.start, cut.title) for cut in body.cuts]
    try:
        return split_document(db, user.id, document_id, cuts)
    except NotOwned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found") from None
    except RestructureError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
```

- [ ] **Step 6: Run the tests and lint**

Run: `pytest tests/test_restructure.py tests/test_documents.py -q && ruff check .`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add api/restructure.py api/schemas/documents.py api/routers/documents.py tests/test_restructure.py
git commit -m "feat(documents): merge and split that keep translation timestamps"
```

---

### Task 7: TXT import and exports, plus README

**Files:**
- Create: `api/routers/transfer.py`
- Modify: `api/main.py`, `README.md`
- Test: `tests/test_transfer.py`

**Interfaces:**
- Consumes: `SEPARATOR`, `parse_file_content`, `lines_to_db_rows`, `calculate_progress`, `build_markdown_translation`, `build_markdown_ruby`, `sanitize_filename`; `next_series_order`, `write_lines`, `line_arrays`, `chapters`; `read_capped`; `owned_ref`, `scoped`; `DocumentOut`.
- Produces:
  - `api.routers.transfer.router` (no prefix), `MAX_TEXT_BYTES`, and `attachment(filename) -> dict[str, str]`.
  - `POST /documents/import/txt`, `GET /documents/{id}/export`, `GET /series/{id}/export/markdown`.

- [ ] **Step 1: Write the failing tests in `tests/test_transfer.py`**

```python
import io
import zipfile
from urllib.parse import quote

import pytest
from sqlalchemy import select

from api.models import Line

SEP = "---SEPERATOR---"
BODY = f"%一文目。\n$二文目。\n\n%次\n{SEP}\nOne.\nTwo.\n\nNext\n".encode()


def upload(client, body, name="ch1.txt", **form):
    return client.post(
        "/documents/import/txt", files={"file": (name, body, "text/plain")}, data=form
    )


def rows(db, doc_id):
    return [
        tuple(r)
        for r in db.execute(
            select(Line.prefix, Line.raw_text, Line.translated_text)
            .where(Line.document_id == doc_id)
            .order_by(Line.line_number)
        )
    ]


def test_import_txt_creates_document(app_client, db, me):
    r = upload(app_client, BODY, name="第1話.txt")
    assert (r.status_code, r.json()["title"]) == (201, "第1話")
    assert rows(db, r.json()["id"]) == [
        ("%", "一文目。", "One."), ("$", "二文目。", "Two."), ("%", "", ""), ("%", "次", "Next"),
    ]


def test_import_txt_tolerates_bom_and_crlf(app_client, db, me):
    body = ("﻿%行\r\n" + SEP + "\r\nLine\r\n").encode()
    r = upload(app_client, body)
    assert rows(db, r.json()["id"]) == [("%", "行", "Line")]


def test_import_txt_into_a_series_with_a_title(app_client, me, make_series, make_doc):
    series = make_series(me)
    make_doc(me, series=series, order=2)
    r = upload(app_client, BODY, title="Custom", series_id=str(series.id))
    assert (r.json()["title"], r.json()["series_id"], r.json()["series_order"]) == (
        "Custom", series.id, 3,
    )


@pytest.mark.parametrize(
    "body",
    [
        b"%no separator here\n",  # not the TXT format
        "%あ\n---SEPERATOR---\n".encode("shift_jis"),  # not UTF-8
        b"%a\x00\n---SEPERATOR---\n",  # binary
    ],
)
def test_import_txt_rejects_unreadable_files(app_client, me, body):
    r = upload(app_client, body)
    assert r.status_code == 422
    assert r.json()["detail"]


def test_import_txt_size_is_capped(app_client, me, monkeypatch):
    from api.routers import transfer

    monkeypatch.setattr(transfer, "MAX_TEXT_BYTES", 8)
    assert upload(app_client, BODY).status_code == 413


def test_import_txt_into_a_foreign_series_is_422(app_client, me, make_user, make_series):
    theirs = make_series(make_user(email="other@example.com"))
    assert upload(app_client, BODY, series_id=str(theirs.id)).status_code == 422


def test_txt_export_round_trips_the_import(app_client, me):
    doc_id = upload(app_client, BODY).json()["id"]
    r = app_client.get(f"/documents/{doc_id}/export", params={"format": "txt"})
    assert r.status_code == 200
    assert r.content == BODY


def test_markdown_exports(app_client, me):
    doc_id = upload(app_client, BODY, name="第1話.txt").json()["id"]
    md = app_client.get(f"/documents/{doc_id}/export", params={"format": "md"})
    assert md.text == "# 第1話\n\nOne. Two.\n\n\nNext\n\n"
    ruby = app_client.get(f"/documents/{doc_id}/export", params={"format": "md-ruby"})
    assert "<ruby>One. Two.<rt>一文目。二文目。</rt></ruby>" in ruby.text


def test_download_name_keeps_a_japanese_title(app_client, me):
    doc_id = upload(app_client, BODY, name="第1話.txt").json()["id"]
    r = app_client.get(f"/documents/{doc_id}/export", params={"format": "md"})
    assert f"filename*=UTF-8''{quote('第1話.md')}" in r.headers["content-disposition"]


def test_unknown_format_is_422(app_client, me, make_doc):
    doc = make_doc(me, ["a"])
    r = app_client.get(f"/documents/{doc.id}/export", params={"format": "pdf"})
    assert r.status_code == 422


def test_series_markdown_zip_skips_incomplete_chapters(app_client, me, make_series, make_doc):
    s = make_series(me, "シリーズ")
    make_doc(me, ["a"], series=s, order=1, title="A")
    make_doc(me, ["b"], series=s, order=2, title="B")
    make_doc(me, ["c"], series=s, order=3, title="C", translated=False)
    make_doc(me, ["d"], series=s, order=2, title="B")  # same order and title as B
    r = app_client.get(f"/series/{s.id}/export/markdown", params={"variant": "plain"})
    assert r.status_code == 200
    assert r.headers["x-ta-skipped-incomplete"] == "1"
    assert quote("シリーズ.zip") in r.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert names[:2] == ["001 - A.md", "002 - B.md"]
    assert len(names) == 3 and names[2].startswith("002 - B (")


@pytest.mark.parametrize(
    "path", ["/documents/{doc}/export", "/series/{series}/export/markdown"]
)
def test_another_users_exports_are_404(app_client, me, make_user, make_series, make_doc, path):
    other = make_user(email="other@example.com")
    series = make_series(other)
    doc = make_doc(other, ["x"], series=series, order=1)
    assert app_client.get(path.format(doc=doc.id, series=series.id)).status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_transfer.py -q`
Expected: FAIL with 404 or 405, since the routes are missing.

- [ ] **Step 3: Write `api/routers/transfer.py`**

```python
"""File-shaped operations: TXT import and the TXT / Markdown downloads that replace the
desktop's save dialogs."""

import io
import zipfile
from pathlib import PureWindowsPath
from typing import Literal
from urllib.parse import quote

from fastapi import Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from api.core.text import (
    SEPARATOR,
    build_markdown_ruby,
    build_markdown_translation,
    calculate_progress,
    lines_to_db_rows,
    parse_file_content,
    sanitize_filename,
)
from api.deps import current_user, db_session, owned_ref, scoped
from api.library import chapters, line_arrays, next_series_order, write_lines
from api.models import Document, Series, User
from api.routing import api_router
from api.schemas.documents import DocumentOut
from api.uploads import read_capped

router = api_router(tags=["transfer"])

MAX_TEXT_BYTES = 5 * 1024 * 1024


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def attachment(filename: str) -> dict[str, str]:
    """Content-Disposition for a download: an ASCII fallback plus the RFC 5987 UTF-8
    name. Header values must be latin-1, so a Japanese title written raw would 500."""
    fallback = (
        filename.encode("ascii", "replace").decode("ascii").replace("?", "_").replace('"', "_")
    )
    return {
        "Content-Disposition": (
            f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"
        )
    }


@router.post(
    "/documents/import/txt", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
def import_txt(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    series_id: int | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Document:
    """A desktop ---SEPERATOR--- file becomes a document (the desktop import_txt). The
    title defaults to the file name without its extension."""
    data = read_capped(file, MAX_TEXT_BYTES)
    if b"\x00" in data:
        raise _unprocessable("not a text file")
    try:
        text = data.decode("utf-8-sig")  # -sig: Windows editors prepend a BOM
    except UnicodeDecodeError:
        raise _unprocessable("file is not UTF-8 text") from None
    try:
        raw, translated, _ = parse_file_content(text)
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    if series_id is not None:
        owned_ref(db, Series, series_id, user.id, "series_id")
    name = (title or "").strip() or PureWindowsPath(file.filename or "").stem or "Untitled"
    doc = Document(
        user_id=user.id,
        title=name,
        series_id=series_id,
        series_order=next_series_order(db, series_id),
    )
    db.add(doc)
    db.flush()
    write_lines(db, doc.id, lines_to_db_rows(raw, translated))
    return doc


@router.get("/documents/{document_id}/export")
def export_document(
    document_id: int,
    fmt: Literal["txt", "md", "md-ruby"] = Query("txt", alias="format"),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Response:
    doc = scoped(db, Document, document_id, user.id)
    raw, translated = line_arrays(db, doc.id)
    stem = sanitize_filename(doc.title) or f"document-{doc.id}"
    if fmt == "txt":
        # The desktop export_txt layout, which parse_file_content reads back.
        body = "\n".join(raw) + "\n" + SEPARATOR + "\n" + "".join(t + "\n" for t in translated)
        return Response(
            body, media_type="text/plain; charset=utf-8", headers=attachment(f"{stem}.txt")
        )
    build = build_markdown_ruby if fmt == "md-ruby" else build_markdown_translation
    return Response(
        build(raw, translated, doc.chapter_title or doc.title),
        media_type="text/markdown; charset=utf-8",
        headers=attachment(f"{stem}.md"),
    )


@router.get("/series/{series_id}/export/markdown")
def export_series_markdown(
    series_id: int,
    variant: Literal["plain", "ruby"] = "plain",
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Response:
    """Every fully translated chapter as ``NNN - title.md`` in one ZIP (the desktop
    wrote a folder). Incomplete chapters are skipped, as the desktop does; the count
    is in the X-TA-Skipped-Incomplete header."""
    # ponytail: built in memory; stream it if a series' Markdown outgrows a few MB
    series = scoped(db, Series, series_id, user.id)
    build = build_markdown_ruby if variant == "ruby" else build_markdown_translation
    buf = io.BytesIO()
    skipped = 0
    names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in chapters(db, series.id):
            raw, translated = line_arrays(db, doc.id)
            if calculate_progress(raw, translated)[0] < 100:
                skipped += 1
                continue
            stem = sanitize_filename(doc.title) or f"doc_{doc.id}"
            name = f"{doc.series_order:03d} - {stem}.md"
            if name in names:  # a duplicate entry would shadow the first in most unzippers
                name = f"{doc.series_order:03d} - {stem} ({doc.id}).md"
            names.add(name)
            zf.writestr(name, build(raw, translated, doc.chapter_title or doc.title))
    folder = sanitize_filename(series.title) or "series"
    headers = attachment(f"{folder}.zip") | {"X-TA-Skipped-Incomplete": str(skipped)}
    return Response(buf.getvalue(), media_type="application/zip", headers=headers)
```

- [ ] **Step 4: Register the router in `api/main.py`**

Add `transfer` to the sorted import and `app.include_router(transfer.router)` **before** `documents.router`. This is defensive: `POST /documents/import/txt` cannot collide with any documents route today, but declaring the literal path first keeps it that way if a `POST /documents/{id}/{action}` is ever added.

- [ ] **Step 5: Run the whole suite and lint**

Run: `pytest -q && ruff check .`
Expected: all pass. The total is the 170 tests from Phase 1 plus the new modules.

- [ ] **Step 6: Update `README.md`**

Replace the first paragraph ("This repo currently holds **phase 1** ...") with:

```markdown
Web port of the Translation Assistant desktop app. This repo currently holds **phases 1-2**:
the skeleton (FastAPI app, full Postgres schema via Alembic, session auth with invites,
per-user profiles/settings/shortcuts/encrypted credentials, the `ta.db` importer) and the
library API (series, volumes, documents, picker listing with progress, reorder and renumber,
merge and split, covers, TXT import, TXT/Markdown export). There is no web UI yet; the SPA
arrives in phase 3. Phases 3-6 are described in the spec.
```

Add the Phase 2 plan link under the Phase 1 plan link:

```markdown
- Phase 2 plan: [`docs/superpowers/plans/2026-10-10-phase2-library.md`](docs/superpowers/plans/2026-10-10-phase2-library.md)
```

Add a section after "Importing a desktop `ta.db`":

````markdown
## Backup

There is no in-app backup. Dump the database with `pg_dump` (custom format, restorable
with `pg_restore`):

```bash
docker compose exec -T postgres pg_dump -U ta -Fc ta > ta-$(date +%F).dump
docker compose exec -T postgres pg_restore -U ta -d ta --clean --if-exists < ta-2026-10-10.dump
```

Back up `TA_SECRET_KEY` alongside it: without the key, the stored credentials in a restored
dump cannot be decrypted.
````

Append to "Design decisions":

```markdown
- **An id in a request body that is missing or someone else's is a 422**, with one message for
  both (`series_id: no such item`). The URL names the resource, so a 404 there would misreport
  which thing was not found; the single message keeps existence undisclosed.
- **Deleting a series or a volume keeps its chapters.** They become unsorted / unassigned
  (`ON DELETE SET NULL`); deleting chapters is its own action.
- **Merge and split move line rows rather than rewriting them**, so each line keeps its
  `translated_at` (the desktop lost these on merge/split). In split, an image anchored after
  the last line goes to the last segment.
- **The last opened document** is the `last_document_id` user setting, written by the client via
  `PUT /settings`; a deleted document simply answers 404.
- **Uploads are capped and sniffed:** TXT at most 5 MiB, UTF-8 (BOM allowed), no NUL bytes;
  covers at most 10 MiB, PNG/JPEG/GIF/WebP by magic bytes.
```

- [ ] **Step 7: Commit**

```bash
git add api/routers/transfer.py api/main.py README.md tests/test_transfer.py
git commit -m "feat(transfer): TXT import and TXT/Markdown/series ZIP export"
```

---

## Self-Review Notes

- **Spec coverage (§6 and §15 phase 2):**
  - Document create, rename, and delete: Task 3.
  - Restore last opened: settings key (deviation 4).
  - Series create, rename, delete, URL, and profile: Task 2.
  - Drag-and-drop reorder and natural renumber: Task 5.
  - Merge and split with translations, prefixes, and image anchors, plus `series_order` compaction and its own test module: Task 6.
  - Volume assign, rename, EPUB metadata, and cover: Task 4.
  - Picker filtering, progress, and last-edited time: Task 3 (the API; the UI is deviation 1).
  - TXT import and TXT / Markdown / ruby / per-series exports: Task 7.
  - `pg_dump` documented: Task 7.
  - Upload caps and sniffing: Tasks 4 and 7.
  - Tenancy 404 per router (§12): every task's parametrized test.
- **Deferred by the spec's own phasing:** batch file import, EPUB import, and EPUB export are phase 6. The `zip` and `..` extraction rules in §6 apply to those and arrive with them.
- **Names used across tasks:**
  - `owned_ref`, `scoped_volume` (`api/deps.py`).
  - `next_series_order`, `write_lines`, `line_arrays`, `chapters`, `renumber` (`api/library.py`).
  - `DocumentIds`, `DocumentOut` (`api/schemas/documents.py`).
  - `NotOwned`, `RestructureError` (`api/restructure.py`).
  - `MAX_IMAGE_BYTES` (volumes) and `MAX_TEXT_BYTES` (transfer), which tests monkeypatch.
