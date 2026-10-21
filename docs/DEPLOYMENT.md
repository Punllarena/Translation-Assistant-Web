# Deployment

How to run ta-web on a server you control, keep it backed up, and move a desktop library into it.
For local development see [CONTRIBUTING.md](../CONTRIBUTING.md).

## What runs

`docker compose up -d` starts three containers:

| Service    | Role                                                                                   |
|------------|----------------------------------------------------------------------------------------|
| `postgres` | Postgres 16; data in the `pgdata` volume.                                              |
| `api`      | FastAPI under uvicorn, plus the in-process job worker. Not published on the host.      |
| `caddy`    | Serves the built SPA and proxies `/api/*` to the API (prefix stripped). Owns TLS.      |

Caddy serves `https://$TA_SITE_ADDRESS` (default `localhost`, using Caddy's internal CA, so the
browser warns once). Set `TA_SITE_ADDRESS` to a public hostname and Caddy obtains a real
certificate. uvicorn trusts the forwarded client address because Caddy is its only client, and runs
with `--timeout-graceful-shutdown 5` so open job SSE streams cannot block a shutdown.

Request body caps at Caddy: 12 MB by default, 64 MiB on `/api/epub/*`, 1 GiB for the desktop
`ta.db` upload. The API enforces its own limits as well (see [USAGE.md](USAGE.md)).

## Homelab install

1. Create `.env` with a generated `TA_SECRET_KEY` and a `TA_SITE_ADDRESS`:

   ```bash
   cat > .env <<EOF
   TA_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
   TA_SITE_ADDRESS=:80
   EOF
   ```

   `TA_SECRET_KEY` is optional under Compose: without it the API generates one on first boot and
   stores it at `/data/secret_key` in the `ta_data` volume.

2. Choose the address mode:
   - **Cloudflare Tunnel or `tailscale serve`:** `TA_SITE_ADDRESS=:80` (plain http inside; the
     tunnel terminates TLS). Point the tunnel at `http://<host>:<TA_HTTP_PORT>`.
   - **Tailscale direct / LAN:** `TA_SITE_ADDRESS=<machine>.<tailnet>.ts.net` or the LAN address.
3. Set `TA_HTTP_PORT` / `TA_HTTPS_PORT` in `.env` if ports 80/443 are taken.
4. `docker compose up -d`.
5. **Create the admin account immediately, before enabling Cloudflare Tunnel.** Until an account
   exists, anyone who reaches the site can become admin.

   The session cookie is `Secure`, which browsers store over plain http only on `localhost`. With
   `TA_SITE_ADDRESS=:80`, open the site from the host itself at `http://localhost:<TA_HTTP_PORT>`,
   from another machine through `ssh -L 8080:localhost:<TA_HTTP_PORT> <host>` and then
   `http://localhost:8080`, or through `tailscale serve` (https). Opening `http://<host>` from another
   LAN machine creates the account but the browser drops the cookie, so the next wizard steps fail
   with 401.
6. Follow the setup wizard.

`python -m tools.seed_admin --email you@example.com` (inside the container:
`docker compose run --rm api python -m tools.seed_admin --email you@example.com`) creates an admin
without the wizard.

### Behind Cloudflare Tunnel

- **Body size.** Cloudflare caps proxied request bodies at 100 MB (Free and Pro plans, Tunnel
  included). Import a larger desktop `ta.db` over the LAN, `localhost` or Tailscale.
- **Login limiter.** Every request reaches Caddy from `cloudflared`, so the per-address login limiter
  is effectively global: repeated failures lock everyone out for the window. See
  [SECURITY.md](../SECURITY.md#known-limitations).

## Server settings

Admins can override some environment values at **Admin → Server**: `TA_OLLAMA_URL`,
`TA_LIBRETRANSLATE_URL`, `TA_MT_ALLOW_PRIVATE_URLS`, `TA_WP_ALLOW_PRIVATE_URLS` and
`TA_SYOSETU_DELAY_SECONDS`. A saved value wins over the environment, which wins over the default.

The EDICT2 dictionary used by JParser is downloaded (or uploaded) at **Admin → Dictionary** and kept
in `TA_DATA_DIR`.

## Background jobs

The job worker runs inside the API process (`TA_RUN_JOBS_WORKER=false` disables it). Run a single
API process: the startup sweep marks every running job failed, so a second process would fail the
first one's jobs. Starting an interrupted syosetu fetch again resumes it.

## Backups

There is no in-app backup. Keep three things:

1. **The database**, with `pg_dump` (custom format, restorable with `pg_restore`):

   ```bash
   docker compose exec -T postgres pg_dump -U ta -Fc ta > ta-$(date +%F).dump
   docker compose exec -T postgres pg_restore -U ta -d ta --clean --if-exists < ta-2026-10-10.dump
   ```

2. **The `ta_data` volume** (dictionary files, pending uploads, and the generated key if you did not
   set one).
3. **`TA_SECRET_KEY`.** It encrypts stored credentials (DeepL and WordPress keys). Without it a
   restored database still works, but saved credentials cannot be decrypted. With Compose and no
   explicit key: `docker compose exec api cat /data/secret_key`.

`docker compose down -v` deletes both volumes, database included.

## Importing a desktop `ta.db`

In the browser, use **Import → Desktop library** (dry run first, then the real run). The command
line does the same. Work on a copy of the file:

```bash
docker compose run --rm -v ./ta.db:/import/ta.db:ro api python -m tools.import_tadb --db /import/ta.db --user you@example.com --dry-run
# or, without Docker:
python -m tools.import_tadb --db /path/to/ta.db --user you@example.com --dry-run
python -m tools.import_tadb --db /path/to/ta.db --user you@example.com
```

- The destination user must already exist.
- The importer refuses a file already imported for that user, **and** any account that already
  holds documents (a `ta.db` you kept working in has a different fingerprint, so the document count
  is what stops a duplicate run). `--force` overrides both; chapters whose series and title already
  exist are then skipped, so only new chapters are added.
- `--dry-run` writes nothing and is never refused; it reports which chapters would be added or
  skipped.
- The source's columns are checked against the desktop schema first (`SOURCE_COLUMNS` and
  `OPTIONAL_COLUMNS` in `api/core/tadb_schema.py`). Rows the schema rejects are skipped and listed,
  and the command **exits non-zero if any rows were skipped**.
- Timestamps (`lines.translated_at`, `documents.wp_date`) are read as UTC, as the desktop writes
  them. `documents.created_at` / `updated_at` are not carried over; imported rows get the import
  time.
