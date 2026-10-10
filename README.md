# ta-web

Web port of the Translation Assistant desktop app. This repo currently holds **phase 1**
(the skeleton): FastAPI app, full Postgres schema via Alembic, session auth with invites,
per-user profiles/settings/shortcuts/encrypted credentials, and the `ta.db` importer.
Phases 2-6 (the remaining work) are described in the spec.

- Spec: [`docs/superpowers/specs/2026-10-10-web-app-port-design.md`](docs/superpowers/specs/2026-10-10-web-app-port-design.md)
- Phase 1 plan: [`docs/superpowers/plans/2026-10-10-phase1-skeleton.md`](docs/superpowers/plans/2026-10-10-phase1-skeleton.md)

## Prerequisites

Python 3.12+, Docker (with Compose), and a shell.

## Quick start

```bash
# 1. Postgres (bound to 127.0.0.1:5432)
docker compose up -d postgres

# 2. Virtualenv + dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Config (the app reads .env itself). The app deliberately refuses the .env.example placeholder key,
#    so copying the file unchanged will not boot -- generate a real one:
cp .env.example .env
sed -i "s|^TA_SECRET_KEY=.*|TA_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')|" .env

# 4. Schema
alembic upgrade head

# 5. First admin (prompts for a password)
python -m tools.seed_admin --email you@example.com

# 6. Run
uvicorn api.main:app --reload     # http://127.0.0.1:8000/docs
```

`TA_SECRET_KEY` encrypts stored credentials; losing or changing it makes them unreadable.

## Tests and lint

The test fixtures **drop and recreate** the database named in `TA_DATABASE_URL`, so the suite
refuses to run unless that name ends in `_test`. The default `.env` points at `ta`, so override it:

```bash
export TA_DATABASE_URL=postgresql+psycopg://ta:ta@localhost:5432/ta_test
ruff check .
pytest
```

CI (`.github/workflows/ci.yml`) runs the same two commands against a `ta_test` database.

## Importing a desktop `ta.db`

Work on a copy of the file. Do a dry run first (reports counts, writes nothing), then the real run:

```bash
python -m tools.import_tadb --db /path/to/ta.db --user you@example.com --dry-run
python -m tools.import_tadb --db /path/to/ta.db --user you@example.com
```

The destination user must already exist. A second import of the same file for the same user is
refused unless you pass `--force`. Each row is written in its own savepoint; rows the schema
rejects are skipped and listed, and the command **exits non-zero if any rows were skipped**.

## Container

```bash
docker compose up --build        # needs TA_SECRET_KEY in .env or the environment
```

The `api` service runs `alembic upgrade head` and then uvicorn on port 8000. TLS and a reverse
proxy arrive with the SPA in phase 3; until then the API is served directly. Once a proxy fronts
it, keep `--proxy-headers` on uvicorn (already in the container command) and make sure the
proxy is the only thing that can reach it, otherwise clients can spoof their address.

## Design decisions

- **Sessions are opaque random tokens**, stored hashed in a `sessions` row, instead of the spec's
  "signed session id". Same guarantee, no signing dependency, and revocation is deleting a row.
- **Registration is invite-only** by default (`TA_ALLOW_PUBLIC_SIGNUP=false`).
- **`mt_cache` is global, with no `user_id`.** Its key is the content hash, so identical source
  text dedupes across the whole library.
- **Cross-user access returns 404, not 403**, so the existence of another user's rows is not disclosed.
- **The login limiter keys on both client address and submitted email.** The address comes from
  `request.client.host`, which behind a proxy is the proxy's address for everyone unless uvicorn
  runs with `--proxy-headers` (and trusts the proxy via `--forwarded-allow-ips` if it is not local).
- **`B008` is the only ruff rule ignored** (`Depends()` in default arguments is the FastAPI idiom).
