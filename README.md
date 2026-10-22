# ta-web

**Translate Japanese web novels in your browser: a self-hosted, multi-user home for your library,
glossaries, machine translation and WordPress publishing.**

[![CI](https://github.com/Punllarena/Translation-Assistant-Web/actions/workflows/ci.yml/badge.svg)](https://github.com/Punllarena/Translation-Assistant-Web/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Postgres 16](https://img.shields.io/badge/Postgres-16-4169E1?logo=postgresql&logoColor=white)

ta-web is the web port of the [Translation Assistant](https://github.com/Punllarena/Translation-Assistant)
desktop app: a FastAPI + Postgres server with a React SPA, served by Caddy.

<!-- TODO: add a screenshot or GIF of the editor, e.g. docs/images/editor.png -->
> _Screenshot coming soon._

## Features

- **Library:** series, volumes and chapters; reorder, renumber, merge, split, covers; TXT, Markdown,
  ZIP and EPUB export.
- **Editor:** one card per source line, save as you type, rebindable keys, find, spellcheck, inline
  images.
- **Memory:** a glossary per series, translation memory, series-wide find and replace, phrase
  suggestions.
- **Machine translation:** DeepL, LibreTranslate, Ollama (streamed), MeCab and JParser, with a shared
  cache.
- **Acquisition:** fetch whole series from syosetu as background jobs; batch TXT and EPUB import.
- **Publishing:** publish or schedule chapters and volume illustrations to WordPress.
- **Statistics:** activity heatmap, streaks, and per-series progress.
- **Multi-user:** invite-only accounts, per-user settings, encrypted credentials, import of a desktop
  `ta.db`.

## Requirements

| To…                     | You need                                                        |
|-------------------------|-----------------------------------------------------------------|
| Run the app             | Docker with Compose v2                                          |
| Develop without Docker  | Python 3.12+, Node 24, Postgres 16, enchant + an English dictionary |

## Quick start

```bash
git clone https://github.com/Punllarena/Translation-Assistant-Web.git ta-web
cd ta-web
docker compose up -d --build
```

Open <https://localhost> (Caddy's local certificate makes the browser warn once). The setup wizard
creates the first admin account.

> [!IMPORTANT]
> Until that first account exists, anyone who can reach the site can become admin. Finish setup
> before exposing the server; see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

For hot-reload development (`docker compose --profile dev up`) and running the tests, see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Configuration

Set variables in `.env` (copy [`.env.example`](.env.example)) or the environment. Rows marked ★ can
also be set by an admin at **Admin → Server**, which takes precedence.

| Name                       | Description                                                                 | Default                                      | Required |
|----------------------------|-----------------------------------------------------------------------------|----------------------------------------------|----------|
| `TA_SECRET_KEY`            | Encrypts stored credentials; at least 32 characters. Back it up.           | Generated into `/data/secret_key` by Compose | Without Docker |
| `TA_SITE_ADDRESS`          | Address Caddy serves; a public hostname gets a real certificate. `:80` behind a tunnel. | `localhost`                     | No       |
| `TA_HTTP_PORT` / `TA_HTTPS_PORT` | Host ports Caddy publishes.                                           | `80` / `443`                                 | No       |
| `TA_DATABASE_URL`          | SQLAlchemy URL for Postgres.                                                | `postgresql+psycopg://ta:ta@localhost:5432/ta` | No     |
| `TA_DATA_DIR`              | Dictionary files and pending uploads.                                       | `./data` (`/data` in Compose)                | No       |
| `TA_COOKIE_SECURE`         | Mark the session cookie `Secure`. Set `false` for plain-http development.  | `true`                                       | No       |
| `TA_SESSION_TTL_DAYS`      | Session lifetime.                                                           | `30`                                         | No       |
| `TA_LOGIN_MAX_ATTEMPTS`    | Failed logins allowed per window.                                           | `10`                                         | No       |
| `TA_LOGIN_WINDOW_SECONDS`  | Login rate-limit window.                                                    | `300`                                        | No       |
| `TA_OLLAMA_URL` ★          | Default Ollama server.                                                      | `http://localhost:11434`                     | No       |
| `TA_LIBRETRANSLATE_URL` ★  | Default LibreTranslate server; empty means not configured.                  | _(empty)_                                    | No       |
| `TA_MT_ALLOW_PRIVATE_URLS` ★ | Let users point LibreTranslate/Ollama at private or loopback addresses.   | `false`                                      | No       |
| `TA_WP_ALLOW_PRIVATE_URLS` ★ | Let users point WordPress at a private or loopback address.               | `false`                                      | No       |
| `TA_SYOSETU_DELAY_SECONDS` ★ | Seconds between requests to syosetu.                                      | `5`                                          | No       |
| `TA_EDICT_PATH`            | EDICT2 file for JParser; overrides the one downloaded at Admin → Dictionary. | _(empty)_                                  | No       |
| `TA_CONJUGATIONS_PATH`     | Desktop `Conjugations.txt`; enables JParser deconjugation.                  | _(empty)_                                    | No       |
| `TA_RUN_JOBS_WORKER`       | Run the background job worker in the API process.                          | `true`                                       | No       |
| `TA_ALLOW_PUBLIC_SIGNUP`   | Reserved; currently has no effect (accounts are invite-only).              | `false`                                      | No       |

## Documentation

| Document                                     | What's in it                                                       |
|----------------------------------------------|--------------------------------------------------------------------|
| [docs/USAGE.md](docs/USAGE.md)               | Features in depth: acquisition, MT backends, WordPress, limits     |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)     | Homelab install, Cloudflare/Tailscale, backups, `ta.db` import     |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, directory layout, request lifecycle, design decisions |
| [CONTRIBUTING.md](CONTRIBUTING.md)           | Dev setup, tests, code conventions, pull requests                  |
| [SECURITY.md](SECURITY.md)                   | Reporting vulnerabilities, security model, known limitations       |
| [CHANGELOG.md](CHANGELOG.md)                 | What changed, phase by phase                                       |
| [docs/superpowers/specs/](docs/superpowers/specs/) | Design specs ([port spec](docs/superpowers/specs/2026-10-10-web-app-port-design.md)) |
| [docs/TODO.md](docs/TODO.md)                 | Deferred work                                                      |

The HTTP API documents itself at `http://127.0.0.1:8000/docs` when running in development.

## License

No license has been chosen yet, so all rights are reserved by default. The EDICT2 dictionary the app
downloads is © the [Electronic Dictionary Research and Development Group](https://www.edrdg.org/),
used under CC BY-SA 4.0.
