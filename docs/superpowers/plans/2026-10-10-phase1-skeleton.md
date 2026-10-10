# Phase 1 — Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `ta-web` backend skeleton — FastAPI app, the complete Postgres schema under Alembic, session auth with invite-only accounts, per-user settings/shortcuts/credentials, and a working `ta.db` importer — so later phases only add features, never plumbing.

**Architecture:** A single FastAPI application (`api/`) talking to Postgres through SQLAlchemy 2.0 ORM, with Alembic owning the schema from an empty database. Authentication is an opaque random session token stored in a `sessions` table and carried in an `HttpOnly` cookie; every user-owned query goes through one scoping dependency so tenancy cannot be forgotten per-handler. The desktop app's SQLite library is loaded by a standalone CLI (`tools/import_tadb.py`) that reads `ta.db` with the standard library and writes through the same ORM models.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16, pydantic / pydantic-settings, argon2-cffi, cryptography (Fernet), psycopg 3, pytest + httpx, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-10-web-app-port-design.md` (this plan implements §15 phase 1; schema from §3, auth from §4, importer from §11, testing from §12, deployment from §13)

## Global Constraints

- Python 3.12 or newer. SQLAlchemy 2.0 style only — `Mapped[...]` / `mapped_column`, no legacy `Column` declarations, no `Query` API.
- PostgreSQL only. Tests run against a real Postgres from `docker-compose.yml`, never SQLite — the schema uses `bytea`, `JSONB`, and `timestamptz`.
- Alembic starts from an empty database; the desktop `ALTER TABLE` chain is not carried over. One initial migration holds the whole schema.
- `TA_SECRET_KEY` (minimum 32 characters) and `TA_DATABASE_URL` are required. The app refuses to start without `TA_SECRET_KEY`.
- All configuration comes from the environment with the `TA_` prefix. No config files at runtime.
- Session cookie: name `ta_session`, `HttpOnly`, `SameSite=Lax`, `Secure` on by default (`TA_COOKIE_SECURE=false` only for local HTTP development).
- Passwords hashed with argon2id via `argon2-cffi` defaults. Never store or log a plaintext password.
- Secrets in `api_credentials` are encrypted with Fernet. No endpoint ever returns a decrypted secret — responses carry a presence boolean and a last-four hint only.
- Cross-user access returns **404, never 403** — existence is not disclosed.
- Registration is closed by default (`TA_ALLOW_PUBLIC_SIGNUP=false`); accounts come from `tools/seed_admin.py` or an admin-issued invite.
- No Redis, no Celery, no message broker in Phase 1 (the job worker arrives in phase 6).
- No Python module over ~400 lines.
- Every task ends on a commit. Conventional Commits (`feat:`, `test:`, `chore:`, `docs:`).

**One documented deviation from the spec:** §4 says "a signed session id". This plan uses an opaque 256-bit random token stored in a `sessions` row instead. An unguessable random token looked up server-side gives the same guarantee as a signed one without adding a signing dependency, and it makes server-side revocation trivial. Note it in the README.

**Two tables the spec's §3 listing does not enumerate** but §4 requires: `sessions` and `invites`. They are part of this phase's schema.

## Review Focus

1. **Missing or short `TA_SECRET_KEY`** — the app must refuse to start with a clear message, not boot with a weak or absent key. (Task 1)
2. **Cross-user object ids** — every user-scoped endpoint must answer 404 for another user's id, including on `PATCH`/`DELETE`, not only `GET`. (Task 7)
3. **Re-running the importer on the same `ta.db`** — must be refused without `--force` rather than silently duplicating a whole library. (Task 10)
4. **An older `ta.db` missing newer columns** (`translated_at`, `volume_title`, `exclude_export`, `source_url`) — the importer must tolerate absent columns and report, not crash mid-library. (Task 10)
5. **Expired, unknown, or malformed session cookie** — must produce 401 and clear the cookie, never a 500 or an unhandled lookup. (Task 5)

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Dependencies, pytest and ruff configuration |
| `docker-compose.yml` | `postgres` service for dev and tests; `api` service |
| `.env.example` | Every `TA_*` variable with a safe default |
| `api/config.py` | `Settings` (pydantic-settings) + cached accessor; fail-fast validation |
| `api/main.py` | App factory, router registration, `/healthz` |
| `api/db.py` | Engine, `SessionLocal`, `Base` |
| `api/models/identity.py` | `User`, `Session`, `Invite`, `Profile`, `UserSetting`, `Shortcut`, `ApiCredential` |
| `api/models/content.py` | `Series`, `Volume`, `Document`, `Line`, `DocumentImage`, `MtCache`, `WorkSession` |
| `api/security.py` | Password hashing, Fernet encrypt/decrypt, token generation, login rate limiter |
| `api/deps.py` | `db_session`, `current_user`, `require_admin`, `scoped` |
| `api/schemas/*.py` | Pydantic request/response models per router |
| `api/routers/auth.py` | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/accept-invite` |
| `api/routers/invites.py` | Admin invite creation and listing |
| `api/routers/profiles.py` | Profile CRUD — the first user-scoped resource |
| `api/routers/settings.py` | Per-user key/value settings and shortcuts |
| `api/routers/credentials.py` | `api_credentials` CRUD, secrets write-only |
| `migrations/` | Alembic environment plus the single initial migration |
| `tools/seed_admin.py` | Create the first admin account |
| `tools/import_tadb.py` | One-shot `ta.db` → Postgres importer |
| `tests/conftest.py` | Postgres engine, per-test transaction rollback, client and user fixtures |
| `.github/workflows/ci.yml` | Lint + tests against a Postgres service container |

---

### Task 1: Repository scaffold, configuration, health endpoint

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `docker-compose.yml`
- Create: `api/__init__.py`, `api/config.py`, `api/main.py`
- Test: `tests/__init__.py`, `tests/test_config.py`, `tests/test_health.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `api.config.Settings` with fields `secret_key: str`, `database_url: str`, `allow_public_signup: bool`, `session_ttl_days: int`, `cookie_secure: bool`; `api.config.get_settings() -> Settings` (cached); `api.main.create_app() -> FastAPI`; module-level `api.main.app`.

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError

from api.config import Settings


def test_settings_require_secret_key(monkeypatch):
    monkeypatch.delenv("TA_SECRET_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_reject_short_secret_key(monkeypatch):
    monkeypatch.setenv("TA_SECRET_KEY", "too-short")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_read_env_with_prefix(monkeypatch):
    monkeypatch.setenv("TA_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("TA_DATABASE_URL", "postgresql+psycopg://u:p@h:5432/d")
    monkeypatch.setenv("TA_ALLOW_PUBLIC_SIGNUP", "true")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@h:5432/d"
    assert s.allow_public_signup is True
    assert s.cookie_secure is True
    assert s.session_ttl_days == 30
```

`tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from api.main import create_app


def test_healthz_reports_ok():
    client = TestClient(create_app())
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_config.py tests/test_health.py -v`
Expected: collection errors — `ModuleNotFoundError: No module named 'api'`.

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[project]
name = "ta-web"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0.30",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "argon2-cffi>=23.1",
    "cryptography>=42.0",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-cov>=5.0",
    "httpx>=0.27",
    "ruff>=0.5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.setuptools.packages.find]
include = ["api*", "tools*"]
```

- [ ] **Step 4: Write `api/config.py`**

```python
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Environment only — no config files."""

    model_config = SettingsConfigDict(
        env_prefix="TA_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: str = Field(min_length=32)
    database_url: str = "postgresql+psycopg://ta:ta@localhost:5432/ta"
    allow_public_signup: bool = False
    session_ttl_days: int = 30
    cookie_secure: bool = True
    login_max_attempts: int = 10
    login_window_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Write `api/main.py` and `api/__init__.py`**

`api/__init__.py` is empty. `api/main.py`:

```python
from fastapi import FastAPI

from api.config import get_settings


def create_app() -> FastAPI:
    get_settings()  # fail fast: refuses to start without TA_SECRET_KEY
    app = FastAPI(title="ta-web", version="0.1.0")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 6: Write `.env.example`, `.gitignore`, `docker-compose.yml`**

`.env.example`:

```
TA_SECRET_KEY=change-me-to-at-least-32-characters-long
TA_DATABASE_URL=postgresql+psycopg://ta:ta@localhost:5432/ta
TA_ALLOW_PUBLIC_SIGNUP=false
TA_COOKIE_SECURE=false
```

`.gitignore`:

```
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
.ruff_cache/
dist/
*.db
```

`docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: ta
      POSTGRES_PASSWORD: ta
      POSTGRES_DB: ta
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ta"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata:
```

- [ ] **Step 7: Install and run the tests**

Run:
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
TA_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(32))") pytest tests/test_config.py tests/test_health.py -v
```
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore .env.example docker-compose.yml api tests
git commit -m "feat: scaffold FastAPI app with fail-fast configuration"
```

---

### Task 2: ORM models for the whole schema

Models only — no database connection yet. Tests assert the mapped metadata, which catches typos in column names and constraints before Alembic is involved.

**Files:**
- Create: `api/db.py`, `api/models/__init__.py`, `api/models/identity.py`, `api/models/content.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `api.config.get_settings`.
- Produces: `api.db.Base` (DeclarativeBase), `api.db.engine`, `api.db.SessionLocal`; models `User, Session, Invite, Profile, UserSetting, Shortcut, ApiCredential` from `api.models.identity` and `Series, Volume, Document, Line, DocumentImage, MtCache, WorkSession` from `api.models.content`, all re-exported from `api.models`.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:

```python
from api.db import Base
from api.models import Document, Line, Profile, Series, User


def test_every_spec_table_is_mapped():
    expected = {
        "users", "sessions", "invites", "profiles", "user_settings", "shortcuts",
        "api_credentials", "series", "volumes", "documents", "lines",
        "document_images", "mt_cache", "work_sessions",
    }
    assert expected <= set(Base.metadata.tables)


def test_user_owned_tables_carry_user_id():
    for table in ("profiles", "series", "documents", "work_sessions", "api_credentials"):
        assert "user_id" in Base.metadata.tables[table].columns


def test_line_is_unique_per_document_and_number():
    cols = {
        tuple(c.name for c in uc.columns)
        for uc in Base.metadata.tables["lines"].constraints
        if hasattr(uc, "columns") and uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("document_id", "line_number") in cols


def test_series_title_is_unique_per_user():
    cols = {
        tuple(c.name for c in uc.columns)
        for uc in Base.metadata.tables["series"].constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("user_id", "title") in cols


def test_relationship_paths_exist():
    assert Document.lines.property.mapper.class_ is Line
    assert Series.documents.property.mapper.class_ is Document
    assert Profile.user.property.mapper.class_ is User
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: `ModuleNotFoundError: No module named 'api.db'`.

- [ ] **Step 3: Write `api/db.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from api.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
```

- [ ] **Step 4: Write `api/models/identity.py`**

```python
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profiles: Mapped[list["Profile"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parse_chars: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="、 。 ？ ！ 「 」 …… "
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="profiles")
    glossary: Mapped[list["GlossaryEntry"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    custom_words: Mapped[list["CustomWord"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class GlossaryEntry(Base):
    __tablename__ = "glossary"
    __table_args__ = (UniqueConstraint("profile_id", "phrase"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    profile: Mapped[Profile] = relationship(back_populates="glossary")


class CustomWord(Base):
    __tablename__ = "custom_words"
    __table_args__ = (UniqueConstraint("profile_id", "word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    word: Mapped[str] = mapped_column(String(120), nullable=False)

    profile: Mapped[Profile] = relationship(back_populates="custom_words")


class UserSetting(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONB, nullable=False
    )


class Shortcut(Base):
    __tablename__ = "shortcuts"
    __table_args__ = (UniqueConstraint("user_id", "action_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_key: Mapped[str] = mapped_column(String(120), nullable=False)
    binding: Mapped[str] = mapped_column(String(120), nullable=False)


class ApiCredential(Base):
    __tablename__ = "api_credentials"
    __table_args__ = (UniqueConstraint("user_id", "kind", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    secret_enc: Mapped[bytes] = mapped_column(nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

Note on `secret_enc`: declare it as `mapped_column(LargeBinary, nullable=False)` — import `LargeBinary` from `sqlalchemy` and use it explicitly rather than relying on type inference for `bytes`.

- [ ] **Step 5: Write `api/models/content.py`**

```python
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (UniqueConstraint("user_id", "title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    syosetu_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wp_series_slug: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wp_series_title_short: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wp_password_enabled: Mapped[bool | None] = mapped_column(Boolean)
    wp_unlock_after: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="series")
    volumes: Mapped[list["Volume"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class Volume(Base):
    __tablename__ = "volumes"
    __table_args__ = (UniqueConstraint("series_id", "title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    volume_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    epub_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    epub_author: Mapped[str] = mapped_column(Text, nullable=False, default="")
    epub_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    epub_description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    series: Mapped[Series] = relationship(back_populates="volumes")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), index=True
    )
    volume_id: Mapped[int | None] = mapped_column(ForeignKey("volumes.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_language: Mapped[str] = mapped_column(String(16), nullable=False, default="ja")
    series_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wp_post_id: Mapped[int | None] = mapped_column(Integer)
    wp_status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    wp_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wp_scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    series: Mapped[Series | None] = relationship(back_populates="documents")
    lines: Mapped[list["Line"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    images: Mapped[list["DocumentImage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Line(Base):
    __tablename__ = "lines"
    __table_args__ = (
        UniqueConstraint("document_id", "line_number"),
        Index("ix_lines_document_number", "document_id", "line_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prefix: Mapped[str] = mapped_column(String(1), nullable=False, default="%")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    document: Mapped[Document] = relationship(back_populates="lines")


class DocumentImage(Base):
    __tablename__ = "document_images"
    __table_args__ = (Index("ix_document_images_doc_anchor", "document_id", "anchor_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    anchor_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_cover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    src_path: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    exclude_export: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    document: Mapped[Document] = relationship(back_populates="images")


class MtCache(Base):
    __tablename__ = "mt_cache"
    __table_args__ = (
        UniqueConstraint("backend", "source_lang", "target_lang", "source_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backend: Mapped[str] = mapped_column(String(40), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkSession(Base):
    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lines_translated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    words_translated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 6: Write `api/models/__init__.py`**

```python
from api.models.content import (
    Document, DocumentImage, Line, MtCache, Series, Volume, WorkSession,
)
from api.models.identity import (
    ApiCredential, CustomWord, GlossaryEntry, Invite, Profile, Session, Shortcut,
    User, UserSetting,
)

__all__ = [
    "ApiCredential", "CustomWord", "Document", "DocumentImage", "GlossaryEntry",
    "Invite", "Line", "MtCache", "Profile", "Series", "Session", "Shortcut",
    "User", "UserSetting", "Volume", "WorkSession",
]
```

- [ ] **Step 7: Run the tests**

Run: `TA_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(32))") pytest tests/test_models.py -v`
Expected: 5 passed.

- [ ] **Step 8: Commit**

```bash
git add api/db.py api/models tests/test_models.py
git commit -m "feat: add ORM models for the full schema"
```

---

### Task 3: Alembic initial migration and the test database harness

**Files:**
- Create: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_initial.py`
- Create: `tests/conftest.py`
- Test: `tests/test_schema_roundtrip.py`

**Interfaces:**
- Consumes: `api.db.Base`, `api.models` (all models must be imported for autogenerate to see them), `api.config.get_settings`.
- Produces: pytest fixtures `db` (a `Session` in a rolled-back transaction) and `app_client` (a `TestClient` whose `db_session` dependency is overridden to use `db`); revision `0001` as the schema head.

- [ ] **Step 1: Write the failing test**

`tests/test_schema_roundtrip.py`:

```python
from sqlalchemy import inspect, text

from api.models import Document, Line, Profile, User


def test_migration_created_every_table(db):
    names = set(inspect(db.get_bind()).get_table_names())
    assert {"users", "sessions", "invites", "profiles", "documents", "lines"} <= names


def test_insert_and_read_back_a_document_tree(db):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, name="default", is_default=True))
    doc = Document(user_id=user.id, title="Chapter 1")
    db.add(doc)
    db.flush()
    db.add_all([
        Line(document_id=doc.id, line_number=0, prefix="%", raw_text="一行目"),
        Line(document_id=doc.id, line_number=1, prefix="$", raw_text="二行目"),
    ])
    db.flush()
    rows = db.query(Line).filter_by(document_id=doc.id).order_by(Line.line_number).all()
    assert [r.raw_text for r in rows] == ["一行目", "二行目"]
    assert rows[0].translated_text == ""


def test_deleting_a_document_cascades_to_lines(db):
    user = User(email="b@example.com", password_hash="x")
    db.add(user)
    db.flush()
    doc = Document(user_id=user.id, title="Chapter 2")
    db.add(doc)
    db.flush()
    db.add(Line(document_id=doc.id, line_number=0, prefix="%", raw_text="x"))
    db.flush()
    db.execute(text("DELETE FROM documents WHERE id = :i"), {"i": doc.id})
    assert db.query(Line).filter_by(document_id=doc.id).count() == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_schema_roundtrip.py -v`
Expected: `fixture 'db' not found`.

- [ ] **Step 3: Write `alembic.ini`**

```ini
[alembic]
script_location = migrations
prepend_sys_path = .

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

The database URL deliberately stays out of `alembic.ini` — `env.py` reads it from settings so there is exactly one source.

- [ ] **Step 4: Write `migrations/env.py`**

```python
from alembic import context
from sqlalchemy import create_engine

from api.config import get_settings
from api.db import Base
import api.models  # noqa: F401  — registers every mapper with Base.metadata

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url, future=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
```

Copy `migrations/script.py.mako` from the Alembic default template (`alembic init` output) without modification.

- [ ] **Step 5: Generate and review the initial migration**

Run:
```bash
docker compose up -d postgres
export TA_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(32))")
export TA_DATABASE_URL=postgresql+psycopg://ta:ta@localhost:5432/ta
alembic revision --autogenerate -m "initial schema" --rev-id 0001
```

Then read `migrations/versions/0001_initial.py` and verify by eye: 14 tables created, every `user_id` / `profile_id` / `document_id` foreign key present with the `ondelete` behaviour from the models, the unique constraints on `("document_id","line_number")`, `("user_id","title")`, `("profile_id","phrase")`, `("user_id","name")`, and the `mt_cache` four-column unique. Fix the models and regenerate if anything is missing; never hand-patch the migration to paper over a model mistake.

- [ ] **Step 6: Write `tests/conftest.py`**

```python
import os
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

os.environ.setdefault("TA_SECRET_KEY", "test-secret-key-at-least-32-chars-long")
os.environ.setdefault(
    "TA_DATABASE_URL", "postgresql+psycopg://ta:ta@localhost:5432/ta_test"
)
os.environ.setdefault("TA_COOKIE_SECURE", "false")


@pytest.fixture(scope="session")
def engine():
    """Create the test database once per session and migrate it to head."""
    admin_url = os.environ["TA_DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
    name = os.environ["TA_DATABASE_URL"].rsplit("/", 1)[1]
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    eng = create_engine(os.environ["TA_DATABASE_URL"], future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    """One test, one transaction, always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def app_client(db):
    from api.deps import db_session
    from api.main import create_app

    app = create_app()
    app.dependency_overrides[db_session] = lambda: db
    with TestClient(app) as client:
        yield client
```

`app_client` imports `api.deps.db_session`, which Task 4 creates. Until then, only the `db` fixture is used; add the `app_client` fixture in this step anyway so Task 4 needs no conftest edits — the import is inside the fixture body, so it does not break collection.

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_schema_roundtrip.py -v`
Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add alembic.ini migrations tests/conftest.py tests/test_schema_roundtrip.py
git commit -m "feat: add Alembic initial schema migration and Postgres test harness"
```

---

### Task 4: Security primitives

**Files:**
- Create: `api/security.py`, `api/deps.py`
- Test: `tests/test_security.py`

**Interfaces:**
- Consumes: `api.config.get_settings`, `api.db.SessionLocal`.
- Produces:
  - `hash_password(plain: str) -> str`
  - `verify_password(plain: str, hashed: str) -> bool`
  - `new_token() -> str` (43-char urlsafe, 256 bits)
  - `token_hash(token: str) -> str` (64-char lowercase hex, SHA-256)
  - `encrypt_secret(plain: str) -> bytes`
  - `decrypt_secret(blob: bytes) -> str`
  - `LoginLimiter.check(key: str) -> bool` and `LoginLimiter.record_failure(key: str) -> None`, with module-level `login_limiter`
  - `api.deps.db_session()` — FastAPI dependency yielding a `Session`

- [ ] **Step 1: Write the failing test**

`tests/test_security.py`:

```python
import pytest

from api.security import (
    LoginLimiter, decrypt_secret, encrypt_secret, hash_password, new_token,
    token_hash, verify_password,
)


def test_password_round_trip():
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert h.startswith("$argon2")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong horse", h)


def test_each_hash_is_salted_differently():
    assert hash_password("same") != hash_password("same")


def test_tokens_are_unguessable_and_hash_to_hex():
    t1, t2 = new_token(), new_token()
    assert t1 != t2
    assert len(t1) >= 43
    h = token_hash(t1)
    assert len(h) == 64 and h == h.lower()
    assert token_hash(t1) == h  # deterministic


def test_secret_round_trip_and_ciphertext_differs():
    blob = encrypt_secret("deepl-api-key-123")
    assert isinstance(blob, bytes)
    assert b"deepl-api-key-123" not in blob
    assert decrypt_secret(blob) == "deepl-api-key-123"


def test_decrypt_rejects_tampered_ciphertext():
    blob = bytearray(encrypt_secret("x"))
    blob[-1] ^= 0xFF
    with pytest.raises(ValueError):
        decrypt_secret(bytes(blob))


def test_login_limiter_blocks_after_max_attempts():
    limiter = LoginLimiter(max_attempts=3, window_seconds=300)
    assert limiter.check("1.2.3.4")
    for _ in range(3):
        limiter.record_failure("1.2.3.4")
    assert not limiter.check("1.2.3.4")
    assert limiter.check("5.6.7.8")  # per-key, not global
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_security.py -v`
Expected: `ModuleNotFoundError: No module named 'api.security'`.

- [ ] **Step 3: Write `api/security.py`**

```python
import base64
import hashlib
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken

from api.config import get_settings

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fernet() -> Fernet:
    digest = hashlib.sha256(get_settings().secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> bytes:
    return _fernet().encrypt(plain.encode("utf-8"))


def decrypt_secret(blob: bytes) -> str:
    try:
        return _fernet().decrypt(blob).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("secret could not be decrypted") from exc


class LoginLimiter:
    """Per-key fixed-window failure counter.

    # ponytail: in-memory, single process. Move to a table when the
    # deployment runs more than one API replica.
    """

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.window_seconds:
            q.popleft()
        return q

    def check(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) < self.max_attempts

    def record_failure(self, key: str) -> None:
        self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


_settings = get_settings()
login_limiter = LoginLimiter(_settings.login_max_attempts, _settings.login_window_seconds)
```

- [ ] **Step 4: Write `api/deps.py` (the session dependency only; auth arrives in Task 5)**

```python
from collections.abc import Iterator

from sqlalchemy.orm import Session

from api.db import SessionLocal


def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_security.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add api/security.py api/deps.py tests/test_security.py
git commit -m "feat: add password hashing, secret encryption, tokens, login limiter"
```

---

### Task 5: Session authentication

Covers Review Focus item 5 (expired / unknown / malformed cookie → 401).

**Files:**
- Create: `api/schemas/auth.py`, `api/routers/auth.py`
- Modify: `api/deps.py` (add `current_user`, `require_admin`), `api/main.py` (register the router)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `api.security.*`, `api.models.User`, `api.models.Session`, `api.deps.db_session`.
- Produces:
  - `POST /auth/login` body `{"email": str, "password": str}` → 200 `{"id": int, "email": str, "is_admin": bool}`, sets the `ta_session` cookie; 401 on bad credentials; 429 when the limiter trips.
  - `POST /auth/logout` → 204, deletes the session row and clears the cookie.
  - `GET /auth/me` → 200 the same user body, 401 without a valid cookie.
  - `api.deps.current_user(request, db) -> User` (401 on any invalid cookie) and `api.deps.require_admin(user) -> User` (403 for non-admins).
  - Test fixture helper `make_user(db, email, password, is_admin=False) -> User` added to `tests/conftest.py`.

- [ ] **Step 1: Add the user factory to `tests/conftest.py`**

```python
@pytest.fixture
def make_user(db):
    from api.models import User
    from api.security import hash_password

    def _make(email: str = "user@example.com", password: str = "pw-correct", is_admin: bool = False):
        user = User(email=email, password_hash=hash_password(password), is_admin=is_admin)
        db.add(user)
        db.flush()
        return user

    return _make
```

- [ ] **Step 2: Write the failing test**

`tests/test_auth.py`:

```python
from datetime import datetime, timedelta, timezone

from api.models import Session as SessionRow


def test_login_sets_cookie_and_returns_user(app_client, make_user):
    make_user(email="a@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"email": "a@example.com", "password": "pw-correct"})
    assert r.status_code == 200
    assert r.json()["email"] == "a@example.com"
    assert "ta_session" in r.cookies


def test_login_rejects_wrong_password(app_client, make_user):
    make_user(email="b@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"email": "b@example.com", "password": "nope"})
    assert r.status_code == 401
    assert "ta_session" not in r.cookies


def test_login_rejects_unknown_email_with_same_status(app_client):
    r = app_client.post("/auth/login", json={"email": "ghost@example.com", "password": "x"})
    assert r.status_code == 401


def test_me_requires_a_session(app_client):
    assert app_client.get("/auth/me").status_code == 401


def test_me_returns_the_logged_in_user(app_client, make_user):
    make_user(email="c@example.com", password="pw-correct")
    app_client.post("/auth/login", json={"email": "c@example.com", "password": "pw-correct"})
    r = app_client.get("/auth/me")
    assert r.status_code == 200 and r.json()["email"] == "c@example.com"


def test_malformed_cookie_is_401_not_500(app_client):
    app_client.cookies.set("ta_session", "not-a-real-token")
    r = app_client.get("/auth/me")
    assert r.status_code == 401


def test_expired_session_is_401(app_client, db, make_user):
    user = make_user(email="d@example.com", password="pw-correct")
    app_client.post("/auth/login", json={"email": "d@example.com", "password": "pw-correct"})
    row = db.query(SessionRow).filter_by(user_id=user.id).one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()
    assert app_client.get("/auth/me").status_code == 401


def test_logout_deletes_the_session(app_client, db, make_user):
    user = make_user(email="e@example.com", password="pw-correct")
    app_client.post("/auth/login", json={"email": "e@example.com", "password": "pw-correct"})
    assert app_client.post("/auth/logout").status_code == 204
    assert db.query(SessionRow).filter_by(user_id=user.id).count() == 0
    assert app_client.get("/auth/me").status_code == 401


def test_repeated_failures_are_rate_limited(app_client, make_user):
    make_user(email="f@example.com", password="pw-correct")
    from api.security import login_limiter

    login_limiter.reset("testclient")
    codes = [
        app_client.post("/auth/login", json={"email": "f@example.com", "password": "bad"}).status_code
        for _ in range(12)
    ]
    assert 429 in codes
    login_limiter.reset("testclient")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_auth.py -v`
Expected: every test fails with 404 — `/auth/login` does not exist.

- [ ] **Step 4: Write `api/schemas/auth.py`**

```python
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    is_admin: bool
```

`EmailStr` needs `pydantic[email]`; add `"pydantic[email]>=2.7"` to `pyproject.toml` dependencies in this step.

- [ ] **Step 5: Add `current_user` and `require_admin` to `api/deps.py`**

```python
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select

from api.models import Session as SessionRow
from api.models import User
from api.security import token_hash

COOKIE_NAME = "ta_session"


def current_user(request: Request, db: Session = Depends(db_session)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    row = db.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash(token)))
    if row is None or row.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session invalid or expired")
    row.last_seen_at = datetime.now(timezone.utc)
    return row.user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user
```

Any cookie value is safe to feed to `token_hash` — it hashes arbitrary text, so a malformed cookie becomes a lookup miss and a 401, which is what the malformed-cookie test pins.

- [ ] **Step 6: Write `api/routers/auth.py`**

```python
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.deps import COOKIE_NAME, current_user, db_session
from api.models import Session as SessionRow
from api.models import User
from api.schemas.auth import LoginRequest, UserOut
from api.security import login_limiter, new_token, token_hash, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _rate_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(db_session),
) -> User:
    key = _rate_key(request)
    if not login_limiter.check(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts")

    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        login_limiter.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    settings = get_settings()
    token = new_token()
    db.add(
        SessionRow(
            token_hash=token_hash(token),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days),
        )
    )
    db.flush()
    login_limiter.reset(key)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_days * 86400,
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(db_session)) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        row = db.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash(token)))
        if row is not None:
            db.delete(row)
            db.flush()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
```

`UserOut` reads attributes off the ORM object, so set `model_config = ConfigDict(from_attributes=True)` on it in `api/schemas/auth.py` during this step.

- [ ] **Step 7: Register the router in `api/main.py`**

```python
from api.routers import auth

# inside create_app(), after the health endpoint:
    app.include_router(auth.router)
```

- [ ] **Step 8: Run the tests**

Run: `pytest tests/test_auth.py -v`
Expected: 9 passed.

- [ ] **Step 9: Commit**

```bash
git add api/deps.py api/schemas api/routers api/main.py pyproject.toml tests/test_auth.py tests/conftest.py
git commit -m "feat: add session authentication with login rate limiting"
```

---

### Task 6: Invites and the first admin

**Files:**
- Create: `api/schemas/invites.py`, `api/routers/invites.py`, `tools/__init__.py`, `tools/seed_admin.py`
- Modify: `api/routers/auth.py` (add `POST /auth/accept-invite`), `api/main.py`
- Test: `tests/test_invites.py`, `tests/test_seed_admin.py`

**Interfaces:**
- Consumes: `api.deps.require_admin`, `api.models.Invite`, `api.security.*`.
- Produces:
  - `POST /invites` (admin) body `{"email": str | None, "ttl_days": int = 14}` → 201 `{"token": str, "expires_at": datetime}` — the plaintext token is returned **once** and never stored.
  - `GET /invites` (admin) → list of `{"id", "email", "created_at", "expires_at", "accepted_at"}`.
  - `POST /auth/accept-invite` body `{"token": str, "email": str, "password": str}` → 201 `UserOut`, creates the user plus a `default` profile, marks the invite accepted.
  - `tools.seed_admin.create_admin(db, email: str, password: str) -> User`.

- [ ] **Step 1: Write the failing tests**

`tests/test_invites.py`:

```python
def _login(client, email, password="pw-correct"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_non_admin_cannot_create_invites(app_client, make_user):
    make_user(email="plain@example.com")
    _login(app_client, "plain@example.com")
    assert app_client.post("/invites", json={}).status_code == 403


def test_anonymous_cannot_create_invites(app_client):
    assert app_client.post("/invites", json={}).status_code == 401


def test_admin_creates_an_invite_and_gets_the_token_once(app_client, db, make_user):
    make_user(email="admin@example.com", is_admin=True)
    _login(app_client, "admin@example.com")
    r = app_client.post("/invites", json={"email": "new@example.com"})
    assert r.status_code == 201
    token = r.json()["token"]
    assert token
    listed = app_client.get("/invites").json()
    assert len(listed) == 1
    assert "token" not in listed[0]  # plaintext is never retrievable again


def test_accept_invite_creates_user_with_default_profile(app_client, make_user):
    make_user(email="admin2@example.com", is_admin=True)
    _login(app_client, "admin2@example.com")
    token = app_client.post("/invites", json={}).json()["token"]
    app_client.post("/auth/logout")

    r = app_client.post(
        "/auth/accept-invite",
        json={"token": token, "email": "fresh@example.com", "password": "pw-fresh-123"},
    )
    assert r.status_code == 201
    assert _login(app_client, "fresh@example.com", "pw-fresh-123").status_code == 200
    profiles = app_client.get("/profiles").json() if False else None  # profiles router: Task 7
    assert profiles is None


def test_an_invite_cannot_be_used_twice(app_client, make_user):
    make_user(email="admin3@example.com", is_admin=True)
    _login(app_client, "admin3@example.com")
    token = app_client.post("/invites", json={}).json()["token"]
    app_client.post("/auth/logout")
    body = {"token": token, "email": "one@example.com", "password": "pw-one-12345"}
    assert app_client.post("/auth/accept-invite", json=body).status_code == 201
    body2 = {"token": token, "email": "two@example.com", "password": "pw-two-12345"}
    assert app_client.post("/auth/accept-invite", json=body2).status_code == 400


def test_unknown_invite_token_is_rejected(app_client):
    r = app_client.post(
        "/auth/accept-invite",
        json={"token": "nonsense", "email": "x@example.com", "password": "pw-x-123456"},
    )
    assert r.status_code == 400


def test_expired_invite_is_rejected(app_client, db, make_user):
    from datetime import datetime, timedelta, timezone

    from api.models import Invite

    make_user(email="admin4@example.com", is_admin=True)
    _login(app_client, "admin4@example.com")
    token = app_client.post("/invites", json={}).json()["token"]
    db.query(Invite).one().expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    app_client.post("/auth/logout")
    r = app_client.post(
        "/auth/accept-invite",
        json={"token": token, "email": "late@example.com", "password": "pw-late-1234"},
    )
    assert r.status_code == 400
```

Drop the dead `profiles` line from `test_accept_invite_creates_user_with_default_profile` and assert the profile directly instead:

```python
    from api.models import Profile, User
    user = db.query(User).filter_by(email="fresh@example.com").one()
    assert [p.name for p in db.query(Profile).filter_by(user_id=user.id)] == ["default"]
```

`tests/test_seed_admin.py`:

```python
import pytest

from api.models import Profile, User
from tools.seed_admin import create_admin


def test_create_admin_makes_an_admin_with_a_default_profile(db):
    user = create_admin(db, "root@example.com", "pw-root-12345")
    assert user.is_admin is True
    assert user.password_hash.startswith("$argon2")
    assert [p.name for p in db.query(Profile).filter_by(user_id=user.id)] == ["default"]


def test_create_admin_refuses_a_duplicate_email(db):
    create_admin(db, "dup@example.com", "pw-dup-123456")
    with pytest.raises(ValueError, match="already exists"):
        create_admin(db, "dup@example.com", "pw-dup-123456")


def test_create_admin_refuses_a_short_password(db):
    with pytest.raises(ValueError, match="at least 12"):
        create_admin(db, "short@example.com", "tiny")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_invites.py tests/test_seed_admin.py -v`
Expected: 404s on `/invites`, and `ModuleNotFoundError: No module named 'tools'`.

- [ ] **Step 3: Write `api/schemas/invites.py`**

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class InviteCreate(BaseModel):
    email: EmailStr | None = None
    ttl_days: int = Field(default=14, ge=1, le=90)


class InviteCreated(BaseModel):
    token: str
    expires_at: datetime


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None


class AcceptInvite(BaseModel):
    token: str
    email: EmailStr
    password: str = Field(min_length=12)
```

- [ ] **Step 4: Write `api/routers/invites.py`**

```python
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import db_session, require_admin
from api.models import Invite, User
from api.schemas.invites import InviteCreate, InviteCreated, InviteOut
from api.security import new_token, token_hash

router = APIRouter(prefix="/invites", tags=["invites"])


@router.post("", response_model=InviteCreated, status_code=status.HTTP_201_CREATED)
def create_invite(
    body: InviteCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
) -> InviteCreated:
    token = new_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=body.ttl_days)
    db.add(
        Invite(
            token_hash=token_hash(token),
            email=body.email,
            created_by=admin.id,
            expires_at=expires_at,
        )
    )
    db.flush()
    return InviteCreated(token=token, expires_at=expires_at)


@router.get("", response_model=list[InviteOut])
def list_invites(
    admin: User = Depends(require_admin), db: Session = Depends(db_session)
) -> list[Invite]:
    return list(db.scalars(select(Invite).order_by(Invite.created_at.desc())))
```

- [ ] **Step 5: Add `POST /auth/accept-invite` to `api/routers/auth.py`**

```python
from api.models import Invite, Profile
from api.schemas.invites import AcceptInvite
from api.security import hash_password


@router.post("/accept-invite", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def accept_invite(body: AcceptInvite, db: Session = Depends(db_session)) -> User:
    invite = db.scalar(select(Invite).where(Invite.token_hash == token_hash(body.token)))
    now = datetime.now(timezone.utc)
    if invite is None or invite.accepted_at is not None or invite.expires_at <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invite is invalid or already used")
    if invite.email is not None and invite.email.lower() != body.email.lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invite is invalid or already used")
    if db.scalar(select(User).where(User.email == body.email)) is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "email already registered")

    user = User(email=body.email, password_hash=hash_password(body.password), is_admin=False)
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, name="default", is_default=True))
    invite.accepted_at = now
    db.flush()
    return user
```

Every rejection path returns the same message so a caller cannot probe which invites exist.

- [ ] **Step 6: Write `tools/seed_admin.py`**

```python
"""Create the first admin account: python -m tools.seed_admin --email … """

import argparse
import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import Profile, User
from api.security import hash_password

MIN_PASSWORD = 12


def create_admin(db: Session, email: str, password: str) -> User:
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise ValueError(f"user {email} already exists")
    user = User(email=email, password_hash=hash_password(password), is_admin=True)
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, name="default", is_default=True))
    db.flush()
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first admin account")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat: "):
        raise SystemExit("passwords do not match")
    with SessionLocal() as db:
        user = create_admin(db, args.email, password)
        db.commit()
        print(f"created admin {user.email} (id={user.id})")


if __name__ == "__main__":
    main()
```

`tools/__init__.py` is empty.

- [ ] **Step 7: Register the invites router in `api/main.py`**

```python
from api.routers import auth, invites

    app.include_router(auth.router)
    app.include_router(invites.router)
```

- [ ] **Step 8: Run the tests**

Run: `pytest tests/test_invites.py tests/test_seed_admin.py -v`
Expected: 10 passed.

- [ ] **Step 9: Commit**

```bash
git add api tools tests/test_invites.py tests/test_seed_admin.py
git commit -m "feat: add admin invites, invite acceptance, and seed_admin CLI"
```

---

### Task 7: Scoped access and the profiles resource

Covers Review Focus item 2 (cross-user ids → 404 on every verb).

**Files:**
- Create: `api/schemas/profiles.py`, `api/routers/profiles.py`
- Modify: `api/deps.py` (add `scoped`), `api/main.py`
- Test: `tests/test_profiles.py`, `tests/test_tenancy.py`

**Interfaces:**
- Consumes: `api.deps.current_user`, `api.deps.db_session`, `api.models.Profile`.
- Produces:
  - `api.deps.scoped(db, model, obj_id, user_id)` → the row, or `HTTPException(404)`. Signature: `scoped(db: Session, model: type[T], obj_id: int, user_id: int) -> T`.
  - `GET /profiles` → list of `{"id", "name", "parse_chars", "is_default"}`, current user only.
  - `POST /profiles` body `{"name", "parse_chars"?, "is_default"?}` → 201; 409 on a duplicate name for that user.
  - `PATCH /profiles/{id}` partial update → 200; 404 for another user's id.
  - `DELETE /profiles/{id}` → 204; 404 for another user's id; 409 when it is the only profile.
- Later tasks and later phases use `scoped` for every user-owned row; they must not write their own ownership checks.

- [ ] **Step 1: Write the failing tests**

`tests/test_profiles.py`:

```python
def _login(client, email, password="pw-correct"):
    client.post("/auth/login", json={"email": email, "password": password})


def test_profiles_require_authentication(app_client):
    assert app_client.get("/profiles").status_code == 401


def test_list_returns_only_my_profiles(app_client, db, make_user):
    from api.models import Profile

    mine = make_user(email="mine@example.com")
    theirs = make_user(email="theirs@example.com")
    db.add_all([
        Profile(user_id=mine.id, name="default", is_default=True),
        Profile(user_id=theirs.id, name="default", is_default=True),
        Profile(user_id=theirs.id, name="secret"),
    ])
    db.flush()
    _login(app_client, "mine@example.com")
    names = [p["name"] for p in app_client.get("/profiles").json()]
    assert names == ["default"]


def test_create_profile(app_client, make_user):
    make_user(email="c@example.com")
    _login(app_client, "c@example.com")
    r = app_client.post("/profiles", json={"name": "wn", "parse_chars": "。！"})
    assert r.status_code == 201
    assert r.json()["parse_chars"] == "。！"


def test_duplicate_profile_name_is_409(app_client, make_user):
    make_user(email="d@example.com")
    _login(app_client, "d@example.com")
    app_client.post("/profiles", json={"name": "wn"})
    assert app_client.post("/profiles", json={"name": "wn"}).status_code == 409


def test_same_profile_name_is_allowed_for_two_users(app_client, db, make_user):
    make_user(email="e1@example.com")
    make_user(email="e2@example.com")
    _login(app_client, "e1@example.com")
    assert app_client.post("/profiles", json={"name": "shared"}).status_code == 201
    app_client.post("/auth/logout")
    _login(app_client, "e2@example.com")
    assert app_client.post("/profiles", json={"name": "shared"}).status_code == 201


def test_patch_updates_parse_chars(app_client, make_user):
    make_user(email="f@example.com")
    _login(app_client, "f@example.com")
    pid = app_client.post("/profiles", json={"name": "wn"}).json()["id"]
    r = app_client.patch(f"/profiles/{pid}", json={"parse_chars": "。"})
    assert r.status_code == 200 and r.json()["parse_chars"] == "。"


def test_delete_last_profile_is_409(app_client, make_user):
    make_user(email="g@example.com")
    _login(app_client, "g@example.com")
    pid = app_client.post("/profiles", json={"name": "only"}).json()["id"]
    assert app_client.delete(f"/profiles/{pid}").status_code == 409


def test_delete_one_of_several(app_client, make_user):
    make_user(email="h@example.com")
    _login(app_client, "h@example.com")
    app_client.post("/profiles", json={"name": "keep"})
    pid = app_client.post("/profiles", json={"name": "drop"}).json()["id"]
    assert app_client.delete(f"/profiles/{pid}").status_code == 204
    assert [p["name"] for p in app_client.get("/profiles").json()] == ["keep"]
```

`tests/test_tenancy.py`:

```python
import pytest


def _login(client, email, password="pw-correct"):
    client.post("/auth/login", json={"email": email, "password": password})


@pytest.fixture
def other_users_profile_id(app_client, make_user):
    make_user(email="owner@example.com")
    make_user(email="intruder@example.com")
    _login(app_client, "owner@example.com")
    pid = app_client.post("/profiles", json={"name": "owned"}).json()["id"]
    app_client.post("/auth/logout")
    _login(app_client, "intruder@example.com")
    return pid


def test_get_another_users_profile_is_404(app_client, other_users_profile_id):
    assert app_client.get(f"/profiles/{other_users_profile_id}").status_code == 404


def test_patch_another_users_profile_is_404(app_client, other_users_profile_id):
    r = app_client.patch(f"/profiles/{other_users_profile_id}", json={"name": "stolen"})
    assert r.status_code == 404


def test_delete_another_users_profile_is_404(app_client, other_users_profile_id):
    assert app_client.delete(f"/profiles/{other_users_profile_id}").status_code == 404


def test_missing_id_is_also_404_not_403(app_client, make_user):
    make_user(email="nobody@example.com")
    _login(app_client, "nobody@example.com")
    assert app_client.get("/profiles/999999").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_profiles.py tests/test_tenancy.py -v`
Expected: all fail with 404 on `/profiles` (no router yet).

- [ ] **Step 3: Add `scoped` to `api/deps.py`**

```python
from typing import TypeVar

T = TypeVar("T")


def scoped(db: Session, model: type[T], obj_id: int, user_id: int) -> T:
    """Fetch a user-owned row or raise 404.

    404, never 403: a wrong owner and a missing row are indistinguishable
    to the caller, so existence is never disclosed.
    """
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "user_id", None) != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return obj
```

- [ ] **Step 4: Write `api/schemas/profiles.py`**

```python
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PARSE_CHARS = "、 。 ？ ！ 「 」 …… "


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parse_chars: str = DEFAULT_PARSE_CHARS
    is_default: bool = False


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parse_chars: str | None = None
    is_default: bool | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parse_chars: str
    is_default: bool
```

- [ ] **Step 5: Write `api/routers/profiles.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, scoped
from api.models import Profile, User
from api.schemas.profiles import ProfileCreate, ProfileOut, ProfileUpdate

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[ProfileOut])
def list_profiles(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[Profile]:
    return list(
        db.scalars(select(Profile).where(Profile.user_id == user.id).order_by(Profile.name))
    )


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile(
    profile_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Profile:
    return scoped(db, Profile, profile_id, user.id)


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProfileCreate, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Profile:
    profile = Profile(
        user_id=user.id,
        name=body.name,
        parse_chars=body.parse_chars,
        is_default=body.is_default,
    )
    db.add(profile)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "a profile with that name exists") from exc
    return profile


@router.patch("/{profile_id}", response_model=ProfileOut)
def update_profile(
    profile_id: int,
    body: ProfileUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Profile:
    profile = scoped(db, Profile, profile_id, user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "a profile with that name exists") from exc
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    profile = scoped(db, Profile, profile_id, user.id)
    remaining = db.scalar(
        select(Profile).where(Profile.user_id == user.id, Profile.id != profile_id).limit(1)
    )
    if remaining is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot delete the only profile")
    db.delete(profile)
    db.flush()
```

- [ ] **Step 6: Register the router and run the tests**

Add `app.include_router(profiles.router)` to `create_app()`.

Run: `pytest tests/test_profiles.py tests/test_tenancy.py -v`
Expected: 12 passed.

- [ ] **Step 7: Commit**

```bash
git add api tests/test_profiles.py tests/test_tenancy.py
git commit -m "feat: add scoped row access and the profiles resource"
```

---

### Task 8: Per-user settings and shortcuts

Replaces `QSettings` and the desktop shortcut customization.

**Files:**
- Create: `api/schemas/settings.py`, `api/routers/settings.py`
- Modify: `api/main.py`
- Test: `tests/test_settings_api.py`

**Interfaces:**
- Consumes: `api.deps.current_user`, `api.deps.db_session`, `api.models.UserSetting`, `api.models.Shortcut`.
- Produces:
  - `GET /settings` → `{key: value}` for the current user.
  - `PUT /settings` body `{key: value, ...}` → 200 with the merged map; upserts each key, accepts any JSON value.
  - `DELETE /settings/{key}` → 204 (idempotent: 204 even when absent).
  - `GET /shortcuts` → `{action_key: binding}`.
  - `PUT /shortcuts` body `{action_key: binding}` → 200 merged map; 409 when two action keys are given the same binding.
  - `DELETE /shortcuts/{action_key}` → 204, reverting that action to the client default.

- [ ] **Step 1: Write the failing test**

`tests/test_settings_api.py`:

```python
def _login(client, email="s@example.com", password="pw-correct"):
    client.post("/auth/login", json={"email": email, "password": password})


def test_settings_require_authentication(app_client):
    assert app_client.get("/settings").status_code == 401


def test_settings_start_empty(app_client, make_user):
    make_user(email="s@example.com")
    _login(app_client)
    assert app_client.get("/settings").json() == {}


def test_put_settings_accepts_any_json_value(app_client, make_user):
    make_user(email="s@example.com")
    _login(app_client)
    payload = {"font_size": 14.5, "tm_visible": True, "last_doc_id": 7, "panels": {"mt": False}}
    assert app_client.put("/settings", json=payload).json() == payload
    assert app_client.get("/settings").json() == payload


def test_put_settings_merges_rather_than_replaces(app_client, make_user):
    make_user(email="s@example.com")
    _login(app_client)
    app_client.put("/settings", json={"a": 1})
    assert app_client.put("/settings", json={"b": 2}).json() == {"a": 1, "b": 2}


def test_delete_setting_is_idempotent(app_client, make_user):
    make_user(email="s@example.com")
    _login(app_client)
    app_client.put("/settings", json={"a": 1})
    assert app_client.delete("/settings/a").status_code == 204
    assert app_client.delete("/settings/a").status_code == 204
    assert app_client.get("/settings").json() == {}


def test_settings_are_per_user(app_client, make_user):
    make_user(email="s@example.com")
    make_user(email="t@example.com")
    _login(app_client)
    app_client.put("/settings", json={"font_size": 20})
    app_client.post("/auth/logout")
    _login(app_client, "t@example.com")
    assert app_client.get("/settings").json() == {}


def test_shortcuts_round_trip(app_client, make_user):
    make_user(email="s@example.com")
    _login(app_client)
    body = {"next_line": "Down", "prev_line": "Up", "find": "Ctrl+F"}
    assert app_client.put("/shortcuts", json=body).json() == body
    assert app_client.get("/shortcuts").json() == body


def test_conflicting_binding_is_409(app_client, make_user):
    make_user(email="s@example.com")
    _login(app_client)
    app_client.put("/shortcuts", json={"next_line": "Down"})
    r = app_client.put("/shortcuts", json={"next_paragraph": "Down"})
    assert r.status_code == 409


def test_rebinding_the_same_action_is_allowed(app_client, make_user):
    make_user(email="s@example.com")
    _login(app_client)
    app_client.put("/shortcuts", json={"next_line": "Down"})
    assert app_client.put("/shortcuts", json={"next_line": "Ctrl+Down"}).status_code == 200


def test_delete_shortcut_reverts_to_default(app_client, make_user):
    make_user(email="s@example.com")
    _login(app_client)
    app_client.put("/shortcuts", json={"next_line": "Down"})
    assert app_client.delete("/shortcuts/next_line").status_code == 204
    assert app_client.get("/shortcuts").json() == {}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_settings_api.py -v`
Expected: 404s — no `/settings` router.

- [ ] **Step 3: Write `api/schemas/settings.py`**

```python
from typing import Any

JsonValue = Any  # the settings store is deliberately schema-free, like QSettings was
SettingsMap = dict[str, JsonValue]
ShortcutsMap = dict[str, str]
```

- [ ] **Step 4: Write `api/routers/settings.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.deps import current_user, db_session
from api.models import Shortcut, User, UserSetting
from api.schemas.settings import SettingsMap, ShortcutsMap

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsMap)
def get_settings_map(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> SettingsMap:
    rows = db.scalars(select(UserSetting).where(UserSetting.user_id == user.id))
    return {r.key: r.value_json for r in rows}


@router.put("/settings", response_model=SettingsMap)
def put_settings_map(
    body: SettingsMap, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> SettingsMap:
    existing = {
        r.key: r
        for r in db.scalars(select(UserSetting).where(UserSetting.user_id == user.id))
    }
    for key, value in body.items():
        if key in existing:
            existing[key].value_json = value
        else:
            db.add(UserSetting(user_id=user.id, key=key, value_json=value))
    db.flush()
    return get_settings_map(user=user, db=db)


@router.delete("/settings/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_setting(
    key: str, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    db.execute(
        delete(UserSetting).where(UserSetting.user_id == user.id, UserSetting.key == key)
    )
    db.flush()


@router.get("/shortcuts", response_model=ShortcutsMap)
def get_shortcuts(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> ShortcutsMap:
    rows = db.scalars(select(Shortcut).where(Shortcut.user_id == user.id))
    return {r.action_key: r.binding for r in rows}


@router.put("/shortcuts", response_model=ShortcutsMap)
def put_shortcuts(
    body: ShortcutsMap, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> ShortcutsMap:
    rows = {
        r.action_key: r for r in db.scalars(select(Shortcut).where(Shortcut.user_id == user.id))
    }
    merged = {k: r.binding for k, r in rows.items()} | body
    seen: dict[str, str] = {}
    for action, binding in merged.items():
        if binding in seen:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{binding} is already bound to {seen[binding]}",
            )
        seen[binding] = action
    for action, binding in body.items():
        if action in rows:
            rows[action].binding = binding
        else:
            db.add(Shortcut(user_id=user.id, action_key=action, binding=binding))
    db.flush()
    return get_shortcuts(user=user, db=db)


@router.delete("/shortcuts/{action_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shortcut(
    action_key: str, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    db.execute(
        delete(Shortcut).where(Shortcut.user_id == user.id, Shortcut.action_key == action_key)
    )
    db.flush()
```

- [ ] **Step 5: Register the router and run the tests**

Add `app.include_router(settings.router)` to `create_app()`.

Run: `pytest tests/test_settings_api.py -v`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add api tests/test_settings_api.py
git commit -m "feat: add per-user settings and rebindable shortcuts"
```

---

### Task 9: Per-user API credentials, write-only

**Files:**
- Create: `api/schemas/credentials.py`, `api/routers/credentials.py`
- Modify: `api/main.py`
- Test: `tests/test_credentials.py`

**Interfaces:**
- Consumes: `api.security.encrypt_secret`, `api.security.decrypt_secret`, `api.deps.scoped`.
- Produces:
  - `GET /credentials` → list of `{"id", "kind", "name", "endpoint_url", "has_secret": bool, "secret_hint": str}` where `secret_hint` is `"…" + last 4 characters` (empty when the secret is shorter than 8 characters).
  - `POST /credentials` body `{"kind", "name"?, "secret", "endpoint_url"?}` → 201; `kind` restricted to `deepl | libretranslate | wordpress | ollama`; 409 on a duplicate `(kind, name)`.
  - `PATCH /credentials/{id}` → 200; a `secret` field replaces the stored secret, omitting it leaves it untouched.
  - `DELETE /credentials/{id}` → 204.
  - `api.routers.credentials.load_secret(db, user_id, kind, name="") -> str | None` — the only decryption path; later phases call this server-side and never over HTTP.

- [ ] **Step 1: Write the failing test**

`tests/test_credentials.py`:

```python
def _login(client, email="k@example.com", password="pw-correct"):
    client.post("/auth/login", json={"email": email, "password": password})


def test_credentials_require_authentication(app_client):
    assert app_client.get("/credentials").status_code == 401


def test_create_and_list_never_exposes_the_secret(app_client, make_user):
    make_user(email="k@example.com")
    _login(app_client)
    r = app_client.post(
        "/credentials", json={"kind": "deepl", "secret": "abcd1234efgh5678"}
    )
    assert r.status_code == 201
    body = r.json()
    assert "secret" not in body and "secret_enc" not in body
    assert body["has_secret"] is True
    assert body["secret_hint"] == "…5678"
    assert app_client.get("/credentials").json()[0]["secret_hint"] == "…5678"


def test_short_secret_gets_no_hint(app_client, make_user):
    make_user(email="k@example.com")
    _login(app_client)
    r = app_client.post("/credentials", json={"kind": "ollama", "secret": "abc"})
    assert r.json()["secret_hint"] == ""


def test_unknown_kind_is_rejected(app_client, make_user):
    make_user(email="k@example.com")
    _login(app_client)
    r = app_client.post("/credentials", json={"kind": "hotmail", "secret": "x"})
    assert r.status_code == 422


def test_duplicate_kind_and_name_is_409(app_client, make_user):
    make_user(email="k@example.com")
    _login(app_client)
    app_client.post("/credentials", json={"kind": "deepl", "name": "main", "secret": "a" * 10})
    r = app_client.post("/credentials", json={"kind": "deepl", "name": "main", "secret": "b" * 10})
    assert r.status_code == 409


def test_patch_without_secret_leaves_it_intact(app_client, db, make_user):
    from api.routers.credentials import load_secret

    user = make_user(email="k@example.com")
    _login(app_client)
    cid = app_client.post(
        "/credentials", json={"kind": "wordpress", "secret": "wp-secret-value"}
    ).json()["id"]
    app_client.patch(f"/credentials/{cid}", json={"endpoint_url": "https://example.com/wp-json"})
    assert load_secret(db, user.id, "wordpress") == "wp-secret-value"


def test_patch_with_secret_replaces_it(app_client, db, make_user):
    from api.routers.credentials import load_secret

    user = make_user(email="k@example.com")
    _login(app_client)
    cid = app_client.post("/credentials", json={"kind": "deepl", "secret": "old-secret"}).json()["id"]
    app_client.patch(f"/credentials/{cid}", json={"secret": "new-secret"})
    assert load_secret(db, user.id, "deepl") == "new-secret"


def test_secret_is_encrypted_at_rest(app_client, db, make_user):
    from api.models import ApiCredential

    make_user(email="k@example.com")
    _login(app_client)
    app_client.post("/credentials", json={"kind": "deepl", "secret": "plaintext-xyz"})
    blob = db.query(ApiCredential).one().secret_enc
    assert b"plaintext-xyz" not in blob


def test_another_users_credential_is_404(app_client, make_user):
    make_user(email="k@example.com")
    make_user(email="other@example.com")
    _login(app_client)
    cid = app_client.post("/credentials", json={"kind": "deepl", "secret": "a" * 10}).json()["id"]
    app_client.post("/auth/logout")
    _login(app_client, "other@example.com")
    assert app_client.patch(f"/credentials/{cid}", json={"name": "x"}).status_code == 404
    assert app_client.delete(f"/credentials/{cid}").status_code == 404


def test_load_secret_returns_none_when_absent(app_client, db, make_user):
    from api.routers.credentials import load_secret

    user = make_user(email="k@example.com")
    assert load_secret(db, user.id, "deepl") is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_credentials.py -v`
Expected: 404s and `ModuleNotFoundError: No module named 'api.routers.credentials'`.

- [ ] **Step 3: Write `api/schemas/credentials.py`**

```python
from typing import Literal

from pydantic import BaseModel, Field

CredentialKind = Literal["deepl", "libretranslate", "wordpress", "ollama"]


class CredentialCreate(BaseModel):
    kind: CredentialKind
    name: str = ""
    secret: str = Field(min_length=1)
    endpoint_url: str = ""


class CredentialUpdate(BaseModel):
    name: str | None = None
    secret: str | None = Field(default=None, min_length=1)
    endpoint_url: str | None = None


class CredentialOut(BaseModel):
    id: int
    kind: str
    name: str
    endpoint_url: str
    has_secret: bool
    secret_hint: str
```

- [ ] **Step 4: Write `api/routers/credentials.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, scoped
from api.models import ApiCredential, User
from api.schemas.credentials import CredentialCreate, CredentialOut, CredentialUpdate
from api.security import decrypt_secret, encrypt_secret

router = APIRouter(prefix="/credentials", tags=["credentials"])

HINT_MIN_LENGTH = 8


def _hint(secret: str) -> str:
    return f"…{secret[-4:]}" if len(secret) >= HINT_MIN_LENGTH else ""


def _out(row: ApiCredential) -> CredentialOut:
    try:
        secret = decrypt_secret(row.secret_enc)
    except ValueError:
        secret = ""
    return CredentialOut(
        id=row.id,
        kind=row.kind,
        name=row.name,
        endpoint_url=row.endpoint_url,
        has_secret=bool(secret),
        secret_hint=_hint(secret),
    )


def load_secret(db: Session, user_id: int, kind: str, name: str = "") -> str | None:
    """Server-side only. Nothing reachable over HTTP returns this value."""
    row = db.scalar(
        select(ApiCredential).where(
            ApiCredential.user_id == user_id,
            ApiCredential.kind == kind,
            ApiCredential.name == name,
        )
    )
    return None if row is None else decrypt_secret(row.secret_enc)


@router.get("", response_model=list[CredentialOut])
def list_credentials(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[CredentialOut]:
    rows = db.scalars(
        select(ApiCredential)
        .where(ApiCredential.user_id == user.id)
        .order_by(ApiCredential.kind, ApiCredential.name)
    )
    return [_out(r) for r in rows]


@router.post("", response_model=CredentialOut, status_code=status.HTTP_201_CREATED)
def create_credential(
    body: CredentialCreate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> CredentialOut:
    row = ApiCredential(
        user_id=user.id,
        kind=body.kind,
        name=body.name,
        secret_enc=encrypt_secret(body.secret),
        endpoint_url=body.endpoint_url,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "that credential already exists") from exc
    return _out(row)


@router.patch("/{credential_id}", response_model=CredentialOut)
def update_credential(
    credential_id: int,
    body: CredentialUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> CredentialOut:
    row = scoped(db, ApiCredential, credential_id, user.id)
    data = body.model_dump(exclude_unset=True)
    if "secret" in data:
        row.secret_enc = encrypt_secret(data.pop("secret"))
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return _out(row)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    credential_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    db.delete(scoped(db, ApiCredential, credential_id, user.id))
    db.flush()
```

- [ ] **Step 5: Register the router and run the tests**

Add `app.include_router(credentials.router)` to `create_app()`.

Run: `pytest tests/test_credentials.py -v`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add api tests/test_credentials.py
git commit -m "feat: add per-user API credentials with write-only secrets"
```

---

### Task 10: The `ta.db` importer

Covers Review Focus items 3 and 4.

**Files:**
- Create: `tools/import_tadb.py`
- Test: `tests/test_import_tadb.py`

**Interfaces:**
- Consumes: `api.models.*`, `api.db.SessionLocal`.
- Produces:
  - `tools.import_tadb.ImportReport` — dataclass with `written: dict[str, int]`, `skipped: dict[str, int]`, `messages: list[str]`.
  - `tools.import_tadb.import_tadb(db, sqlite_path: Path, user_id: int, *, dry_run: bool = False, force: bool = False) -> ImportReport`
  - `tools.import_tadb.source_fingerprint(sqlite_path: Path) -> str` — SHA-256 of the file, recorded in `user_settings` under the key `imported_tadb_fingerprints` (a list) so a second run is detectable.
  - CLI: `python -m tools.import_tadb --db ta.db --user you@example.com [--dry-run] [--force]`

- [ ] **Step 1: Write the failing test**

`tests/test_import_tadb.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from api.models import Document, DocumentImage, Line, Profile, Series, UserSetting
from tools.import_tadb import ImportReport, import_tadb

LEGACY_DDL = """
CREATE TABLE profiles (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
    parse_chars TEXT NOT NULL DEFAULT '。', created_at TEXT, is_default INTEGER DEFAULT 0);
CREATE TABLE glossary (id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL,
    phrase TEXT NOT NULL, translation TEXT NOT NULL, sort_order INTEGER DEFAULT 0);
CREATE TABLE custom_words (id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL, word TEXT NOT NULL);
CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT NOT NULL,
    source_language TEXT DEFAULT 'ja', created_at TEXT, updated_at TEXT,
    last_position INTEGER DEFAULT 0, series_title TEXT DEFAULT '',
    series_order INTEGER DEFAULT 0, volume_title TEXT DEFAULT '',
    source_url TEXT DEFAULT '', wp_post_id INTEGER, wp_status TEXT DEFAULT '');
CREATE TABLE lines (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL, prefix TEXT DEFAULT '%', raw_text TEXT NOT NULL,
    translated_text TEXT DEFAULT '', translated_at TEXT);
CREATE TABLE document_images (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL,
    anchor_position INTEGER DEFAULT 0, is_cover INTEGER DEFAULT 0,
    src_path TEXT NOT NULL, data BLOB NOT NULL, exclude_export INTEGER DEFAULT 0);
CREATE TABLE series_profiles (series_title TEXT PRIMARY KEY, profile_name TEXT DEFAULT '',
    syosetu_url TEXT DEFAULT '', wp_series_slug TEXT DEFAULT '');
"""


def _legacy_db(tmp_path: Path, *, with_optional_columns: bool = True) -> Path:
    path = tmp_path / "ta.db"
    conn = sqlite3.connect(path)
    ddl = LEGACY_DDL
    if not with_optional_columns:
        ddl = (
            ddl.replace(", translated_at TEXT", "")
            .replace(", volume_title TEXT DEFAULT ''", "")
            .replace(", exclude_export INTEGER DEFAULT 0", "")
            .replace(", source_url TEXT DEFAULT ''", "")
        )
    conn.executescript(ddl)
    conn.execute("INSERT INTO profiles (name, parse_chars, is_default) VALUES ('wn', '。！', 1)")
    conn.execute("INSERT INTO series_profiles (series_title, profile_name, syosetu_url) "
                 "VALUES ('My Series', 'wn', 'https://ncode.syosetu.com/n0000a/')")
    cols = "title, series_title, series_order"
    vals = "('Chapter 1', 'My Series', 0)"
    if with_optional_columns:
        cols += ", volume_title"
        vals = "('Chapter 1', 'My Series', 0, 'Volume 1')"
    conn.execute(f"INSERT INTO documents ({cols}) VALUES {vals}")
    line_cols = "document_id, line_number, prefix, raw_text, translated_text"
    conn.execute(f"INSERT INTO lines ({line_cols}) VALUES (1, 0, '%', '一行目', 'Line one')")
    conn.execute(f"INSERT INTO lines ({line_cols}) VALUES (1, 1, '$', '二行目', '')")
    conn.execute(
        "INSERT INTO document_images (document_id, anchor_position, is_cover, src_path, data) "
        "VALUES (1, 0, 1, 'cover.jpg', X'FFD8FF')"
    )
    conn.commit()
    conn.close()
    return path


def test_import_loads_the_whole_library(db, make_user, tmp_path):
    user = make_user()
    report = import_tadb(db, _legacy_db(tmp_path), user.id)
    assert isinstance(report, ImportReport)
    assert report.written["documents"] == 1
    assert report.written["lines"] == 2
    assert report.written["series"] == 1

    series = db.query(Series).filter_by(user_id=user.id).one()
    assert series.title == "My Series"
    assert series.syosetu_url == "https://ncode.syosetu.com/n0000a/"
    doc = db.query(Document).filter_by(user_id=user.id).one()
    assert doc.series_id == series.id
    assert doc.volume_id is not None
    lines = db.query(Line).filter_by(document_id=doc.id).order_by(Line.line_number).all()
    assert [l.raw_text for l in lines] == ["一行目", "二行目"]
    assert lines[0].translated_text == "Line one"
    assert db.query(DocumentImage).filter_by(document_id=doc.id).one().is_cover is True
    assert [p.name for p in db.query(Profile).filter_by(user_id=user.id)] == ["wn"]


def test_dry_run_writes_nothing(db, make_user, tmp_path):
    user = make_user()
    report = import_tadb(db, _legacy_db(tmp_path), user.id, dry_run=True)
    assert report.written["documents"] == 1
    assert db.query(Document).filter_by(user_id=user.id).count() == 0


def test_second_run_on_the_same_file_is_refused(db, make_user, tmp_path):
    user = make_user()
    path = _legacy_db(tmp_path)
    import_tadb(db, path, user.id)
    with pytest.raises(RuntimeError, match="already imported"):
        import_tadb(db, path, user.id)
    assert db.query(Document).filter_by(user_id=user.id).count() == 1


def test_force_allows_a_second_run(db, make_user, tmp_path):
    user = make_user()
    path = _legacy_db(tmp_path)
    import_tadb(db, path, user.id)
    import_tadb(db, path, user.id, force=True)
    assert db.query(Document).filter_by(user_id=user.id).count() == 2


def test_dry_run_does_not_record_the_fingerprint(db, make_user, tmp_path):
    user = make_user()
    path = _legacy_db(tmp_path)
    import_tadb(db, path, user.id, dry_run=True)
    import_tadb(db, path, user.id)  # must not raise
    assert db.query(Document).filter_by(user_id=user.id).count() == 1


def test_older_database_without_optional_columns_imports(db, make_user, tmp_path):
    user = make_user()
    report = import_tadb(db, _legacy_db(tmp_path, with_optional_columns=False), user.id)
    assert report.written["documents"] == 1
    doc = db.query(Document).filter_by(user_id=user.id).one()
    assert doc.volume_id is None
    assert doc.source_url == ""
    assert db.query(Line).filter_by(document_id=doc.id).first().translated_at is None


def test_rows_failing_validation_are_reported_not_dropped_silently(db, make_user, tmp_path):
    path = _legacy_db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO lines (document_id, line_number, prefix, raw_text) "
                 "VALUES (999, 0, '%', 'orphan')")
    conn.commit()
    conn.close()
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.skipped["lines"] == 1
    assert any("999" in m for m in report.messages)


def test_fingerprint_is_recorded_in_user_settings(db, make_user, tmp_path):
    user = make_user()
    import_tadb(db, _legacy_db(tmp_path), user.id)
    row = db.query(UserSetting).filter_by(
        user_id=user.id, key="imported_tadb_fingerprints"
    ).one()
    assert isinstance(row.value_json, list) and len(row.value_json) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_import_tadb.py -v`
Expected: `ModuleNotFoundError: No module named 'tools.import_tadb'`.

- [ ] **Step 3: Write `tools/import_tadb.py`**

```python
"""One-shot importer: desktop ta.db (SQLite) → ta-web (Postgres).

Reads a copy of the desktop database with the standard library and writes
through the ORM so every constraint applies.
"""

import argparse
import hashlib
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import (
    CustomWord, Document, DocumentImage, GlossaryEntry, Line, Profile, Series,
    User, UserSetting, Volume,
)

FINGERPRINT_KEY = "imported_tadb_fingerprints"


@dataclass
class ImportReport:
    written: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    skipped: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    messages: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{k}: {v} written" for k, v in sorted(self.written.items())]
        parts += [f"{k}: {v} skipped" for k, v in sorted(self.skipped.items()) if v]
        return "\n".join(parts)


def source_fingerprint(sqlite_path: Path) -> str:
    digest = hashlib.sha256()
    with open(sqlite_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _get(row: sqlite3.Row, key: str, default=None):
    """Read a column that may not exist in an older ta.db."""
    return row[key] if key in row.keys() and row[key] is not None else default


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _fingerprints(db: Session, user_id: int) -> tuple[UserSetting | None, list[str]]:
    row = db.scalar(
        select(UserSetting).where(
            UserSetting.user_id == user_id, UserSetting.key == FINGERPRINT_KEY
        )
    )
    return row, list(row.value_json) if row and isinstance(row.value_json, list) else []


def import_tadb(
    db: Session,
    sqlite_path: Path,
    user_id: int,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> ImportReport:
    sqlite_path = Path(sqlite_path)
    report = ImportReport()
    fingerprint = source_fingerprint(sqlite_path)
    setting_row, seen = _fingerprints(db, user_id)
    if fingerprint in seen and not force:
        raise RuntimeError(
            f"{sqlite_path} was already imported for this user; pass force=True to import again"
        )

    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        _import_all(conn, db, user_id, report)
    finally:
        conn.close()

    if dry_run:
        db.rollback()
        return report

    if setting_row is None:
        db.add(
            UserSetting(user_id=user_id, key=FINGERPRINT_KEY, value_json=[fingerprint])
        )
    elif fingerprint not in seen:
        setting_row.value_json = [*seen, fingerprint]
    db.flush()
    return report


def _import_all(
    conn: sqlite3.Connection, db: Session, user_id: int, report: ImportReport
) -> None:
    profiles_by_name = _import_profiles(conn, db, user_id, report)
    series_by_title = _import_series(conn, db, user_id, report, profiles_by_name)
    _import_documents(conn, db, user_id, report, series_by_title)


def _import_profiles(
    conn: sqlite3.Connection, db: Session, user_id: int, report: ImportReport
) -> dict[str, Profile]:
    by_name: dict[str, Profile] = {}
    by_old_id: dict[int, Profile] = {}
    for row in conn.execute("SELECT * FROM profiles"):
        profile = Profile(
            user_id=user_id,
            name=row["name"],
            parse_chars=_get(row, "parse_chars", "、 。 ？ ！ 「 」 …… "),
            is_default=bool(_get(row, "is_default", 0)),
        )
        db.add(profile)
        db.flush()
        by_name[row["name"]] = profile
        by_old_id[row["id"]] = profile
        report.written["profiles"] += 1

    for row in conn.execute("SELECT * FROM glossary"):
        profile = by_old_id.get(row["profile_id"])
        if profile is None:
            report.skipped["glossary"] += 1
            report.messages.append(f"glossary row {row['id']}: unknown profile_id")
            continue
        db.add(
            GlossaryEntry(
                profile_id=profile.id,
                phrase=row["phrase"],
                translation=row["translation"],
                sort_order=_get(row, "sort_order", 0),
            )
        )
        report.written["glossary"] += 1

    for row in conn.execute("SELECT * FROM custom_words"):
        profile = by_old_id.get(row["profile_id"])
        if profile is None:
            report.skipped["custom_words"] += 1
            report.messages.append(f"custom_words row {row['id']}: unknown profile_id")
            continue
        db.add(CustomWord(profile_id=profile.id, word=row["word"]))
        report.written["custom_words"] += 1

    db.flush()
    return by_name


def _import_series(
    conn: sqlite3.Connection,
    db: Session,
    user_id: int,
    report: ImportReport,
    profiles_by_name: dict[str, Profile],
) -> dict[str, Series]:
    meta: dict[str, sqlite3.Row] = {
        r["series_title"]: r for r in conn.execute("SELECT * FROM series_profiles")
    }
    titles = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT series_title FROM documents "
            "WHERE series_title IS NOT NULL AND series_title != ''"
        )
    ]
    out: dict[str, Series] = {}
    for title in titles:
        m = meta.get(title)
        profile = profiles_by_name.get(_get(m, "profile_name", "") if m else "")
        series = Series(
            user_id=user_id,
            title=title,
            profile_id=profile.id if profile else None,
            syosetu_url=_get(m, "syosetu_url", "") if m else "",
            wp_series_slug=_get(m, "wp_series_slug", "") if m else "",
            wp_series_title_short=_get(m, "wp_series_title_short", "") if m else "",
        )
        db.add(series)
        db.flush()
        out[title] = series
        report.written["series"] += 1
    return out


def _import_documents(
    conn: sqlite3.Connection,
    db: Session,
    user_id: int,
    report: ImportReport,
    series_by_title: dict[str, Series],
) -> None:
    doc_cols = _columns(conn, "documents")
    volumes: dict[tuple[int, str], Volume] = {}
    id_map: dict[int, Document] = {}

    for row in conn.execute("SELECT * FROM documents"):
        series = series_by_title.get(_get(row, "series_title", "") or "")
        volume = None
        vol_title = _get(row, "volume_title", "") if "volume_title" in doc_cols else ""
        if series is not None and vol_title:
            key = (series.id, vol_title)
            if key not in volumes:
                volume = Volume(
                    series_id=series.id, title=vol_title, volume_order=len(volumes)
                )
                db.add(volume)
                db.flush()
                volumes[key] = volume
                report.written["volumes"] += 1
            volume = volumes[key]

        doc = Document(
            user_id=user_id,
            series_id=series.id if series else None,
            volume_id=volume.id if volume else None,
            title=row["title"],
            source_language=_get(row, "source_language", "ja"),
            series_order=_get(row, "series_order", 0),
            source_url=_get(row, "source_url", ""),
            last_position=_get(row, "last_position", 0),
            wp_post_id=_get(row, "wp_post_id"),
            wp_status=_get(row, "wp_status", ""),
        )
        db.add(doc)
        db.flush()
        id_map[row["id"]] = doc
        report.written["documents"] += 1

    for row in conn.execute("SELECT * FROM lines ORDER BY document_id, line_number"):
        doc = id_map.get(row["document_id"])
        if doc is None:
            report.skipped["lines"] += 1
            report.messages.append(
                f"lines row {row['id']}: document_id {row['document_id']} not found"
            )
            continue
        db.add(
            Line(
                document_id=doc.id,
                line_number=row["line_number"],
                prefix=_get(row, "prefix", "%") or "%",
                raw_text=row["raw_text"],
                translated_text=_get(row, "translated_text", "") or "",
                translated_at=_parse_ts(_get(row, "translated_at")),
            )
        )
        report.written["lines"] += 1

    for row in conn.execute("SELECT * FROM document_images"):
        doc = id_map.get(row["document_id"])
        if doc is None:
            report.skipped["document_images"] += 1
            report.messages.append(
                f"document_images row {row['id']}: document_id {row['document_id']} not found"
            )
            continue
        db.add(
            DocumentImage(
                document_id=doc.id,
                anchor_position=_get(row, "anchor_position", 0),
                is_cover=bool(_get(row, "is_cover", 0)),
                src_path=row["src_path"],
                data=row["data"],
                exclude_export=bool(_get(row, "exclude_export", 0)),
            )
        )
        report.written["document_images"] += 1

    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a desktop ta.db into ta-web")
    parser.add_argument("--db", required=True, type=Path, help="path to a copy of ta.db")
    parser.add_argument("--user", required=True, help="email of the destination account")
    parser.add_argument("--dry-run", action="store_true", help="report counts, write nothing")
    parser.add_argument("--force", action="store_true", help="import again even if seen before")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.user))
        if user is None:
            raise SystemExit(f"no such user: {args.user}")
        report = import_tadb(
            db, args.db, user.id, dry_run=args.dry_run, force=args.force
        )
        if args.dry_run:
            print("DRY RUN — nothing written")
        else:
            db.commit()
        print(report.summary())
        for message in report.messages:
            print(f"  ! {message}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_import_tadb.py -v`
Expected: 8 passed.

Note for the implementer: the `dry_run` path calls `db.rollback()`, which in the test harness rolls back to the enclosing savepoint rather than discarding the outer transaction — that is why `join_transaction_mode="create_savepoint"` is set on the `db` fixture in Task 3. Do not remove it.

- [ ] **Step 5: Commit**

```bash
git add tools/import_tadb.py tests/test_import_tadb.py
git commit -m "feat: add one-shot ta.db importer with dry-run and re-run guard"
```

---

### Task 11: CI, developer documentation, and the API container

**Files:**
- Create: `.github/workflows/ci.yml`, `Dockerfile`
- Modify: `README.md`, `docker-compose.yml` (add the `api` service)
- Test: `tests/test_smoke_startup.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `make`-free one-liners documented in the README; a CI job that fails on lint errors or any failing test.

- [ ] **Step 1: Write the failing test**

`tests/test_smoke_startup.py`:

```python
from api.main import create_app


def test_every_phase1_route_is_registered():
    paths = {r.path for r in create_app().routes}
    expected = {
        "/healthz",
        "/auth/login", "/auth/logout", "/auth/me", "/auth/accept-invite",
        "/invites",
        "/profiles", "/profiles/{profile_id}",
        "/settings", "/settings/{key}",
        "/shortcuts", "/shortcuts/{action_key}",
        "/credentials", "/credentials/{credential_id}",
    }
    assert expected <= paths


def test_openapi_schema_builds():
    schema = create_app().openapi()
    assert schema["info"]["title"] == "ta-web"
    assert "/auth/login" in schema["paths"]
```

- [ ] **Step 2: Run it**

Run: `pytest tests/test_smoke_startup.py -v`
Expected: 2 passed if every router from Tasks 5–9 is registered; a failing set difference names whichever router was forgotten.

- [ ] **Step 3: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .
COPY api ./api
COPY migrations ./migrations
COPY tools ./tools
COPY alembic.ini ./

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000"]
```

- [ ] **Step 4: Add the `api` service to `docker-compose.yml`**

```yaml
  api:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      TA_SECRET_KEY: ${TA_SECRET_KEY:?set TA_SECRET_KEY in .env}
      TA_DATABASE_URL: postgresql+psycopg://ta:ta@postgres:5432/ta
      TA_COOKIE_SECURE: "false"
    ports: ["8000:8000"]
```

Caddy and TLS arrive with the SPA in phase 3; until then the API is served directly.

- [ ] **Step 5: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: ta
          POSTGRES_PASSWORD: ta
          POSTGRES_DB: ta
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U ta" --health-interval 5s
          --health-timeout 5s --health-retries 10
    env:
      TA_SECRET_KEY: ci-secret-key-at-least-32-characters-long
      TA_DATABASE_URL: postgresql+psycopg://ta:ta@localhost:5432/ta_test
      TA_COOKIE_SECURE: "false"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -q
```

- [ ] **Step 6: Rewrite `README.md`**

It must cover, each as a copy-pasteable block: the prerequisites; `docker compose up -d postgres`; creating `.env` from `.env.example` with a generated `TA_SECRET_KEY`; `pip install -e ".[dev]"`; `alembic upgrade head`; `python -m tools.seed_admin --email you@example.com`; `uvicorn api.main:app --reload`; `pytest`; `python -m tools.import_tadb --db /path/to/ta.db --user you@example.com --dry-run` followed by the real run. Add a short "Design decisions" section noting the opaque-session-token deviation from spec §4 and linking the spec and this plan.

- [ ] **Step 7: Run the whole suite and the linter**

Run:
```bash
ruff check .
pytest -q
```
Expected: ruff clean; all tests from Tasks 1–11 pass (roughly 80 tests).

- [ ] **Step 8: Commit**

```bash
git add .github Dockerfile docker-compose.yml README.md tests/test_smoke_startup.py
git commit -m "chore: add CI, API container, and developer documentation"
```

---

## Self-Review

**Spec coverage for phase 1** (§15 item 1: "repo scaffolding, FastAPI app, Alembic from empty, the full schema, auth with sessions and invites, per-user settings and shortcuts, the `ta.db` importer, docker-compose, CI running both test suites"):

| Phase 1 requirement | Task |
|---|---|
| Repo scaffolding | 1 |
| FastAPI app | 1 |
| Alembic from empty | 3 |
| The full schema (§3) | 2, 3 |
| Auth with sessions (§4) | 5 |
| Invites (§4) | 6 |
| Per-user settings and shortcuts (§3) | 8 |
| Per-user encrypted credentials (§4) | 9 |
| Tenancy enforced in one place (§3) | 7 |
| `ta.db` importer (§11) | 10 |
| docker-compose (§13) | 1, 11 |
| CI | 11 |

One deliberate deferral: CI runs the Python suite only, because the `web/` frontend does not exist until phase 3. The CI file gains a second job then. Spec §12's frontend testing requirements belong to phase 3 and are not in scope here.

**Placeholders:** none. Every code step carries runnable code; every test step carries real assertions.

**Type consistency checked:** `scoped(db, model, obj_id, user_id)` is used with that exact signature in Tasks 7 and 9. `token_hash` / `new_token` are used consistently in Tasks 5, 6 and `tools/`. `COOKIE_NAME` is defined once in `api/deps.py` and imported by `api/routers/auth.py`. `load_secret(db, user_id, kind, name="")` is called with that signature in Task 9's tests. `ImportReport.written` / `.skipped` / `.messages` match the assertions in Task 10.

**Review Focus coverage:** item 1 → `tests/test_config.py` (Task 1); item 2 → `tests/test_tenancy.py` (Task 7); items 3 and 4 → `tests/test_import_tadb.py` (Task 10); item 5 → `tests/test_auth.py` (Task 5).
