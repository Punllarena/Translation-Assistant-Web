# Usage

What each feature does, what it needs, and its limits. The full HTTP API is self-documenting: in
development, open `http://127.0.0.1:8000/docs` (OpenAPI/Swagger). The SPA's typed client is
generated from it into `web/src/api/schema.d.ts`.

## Library and editor

- **Library.** Series as a bookshelf or a list. A series page has Volumes, Glossary, Tools and
  Settings tabs.
  Each volume holds a contiguous run of chapters numbered 1..N; loose chapters sit under "No volume".
  Chapters can be reordered, renumbered by title, merged, split, moved between volumes, and exported
  (TXT, Markdown, or a ZIP of ticked chapters).
- **Editor.** One card per source line. Edits save as you type (800 ms after typing stops, or on
  leaving a line), and unsent edits survive a closed tab. Every editor key can be rebound on the
  Shortcuts screen. Edit Source keeps one line per line; a save that changes the line count asks
  first, because translations stay attached by line position.
- **Memory.** One glossary per series (its Glossary tab), translation memory, series-wide find and
  replace (reviewed as a batch), and phrase suggestions (needs MeCab). Parse characters are an
  account setting under Settings → Editor.
- **Spellcheck** runs server-side with enchant. It accepts your account-wide dictionary (Settings →
  Editor) plus the chapter's series dictionary (the series' Glossary tab). Without enchant or an
  English dictionary it reports `available: false`.

## Acquisition

- **Syosetu fetch.** Fetch one chapter from a URL, or a whole series as a background job with live
  progress. Only `*.syosetu.com` hosts are fetched; requests are spaced `TA_SYOSETU_DELAY_SECONDS`
  apart (default 5) across the whole process. At most two interactive syosetu requests wait at once
  (503 beyond), and a series has at most one queued or running fetch job (409 beyond).
- **Syosetu volumes.** Chapters are placed in volumes by syosetu's chapter headings, per the series'
  volume mode (`all`, `marker`, or `off`). Changing the mode can be previewed before it is applied.
- **Re-fetch** a chapter to refresh its source; translations stay attached by line position.
- **Batch TXT import**, optionally with a glossary CSV: at most 500 files, 5 MiB per file, and
  12 MB (Caddy) / 12 MiB (API) per request.
- **EPUB import.** At most a 64 MiB upload, 256 MiB expanded, 4 MiB per XML/XHTML entry, 32 MiB of
  XML/XHTML parsed per book, a 256 MiB budget for one import's chapters and images, and 900
  chapters. Larger omnibus EPUBs are refused (413/422).
- **EPUB download** per volume, once every chapter in it is fully translated.

## Machine translation

Each user configures backends at **Settings → Machine translation**.

| Backend        | Needs                                                                                      |
|----------------|--------------------------------------------------------------------------------------------|
| DeepL          | Your own API key. Free keys end in `:fx` and use the free API host.                        |
| LibreTranslate | A URL: the server default `TA_LIBRETRANSLATE_URL`, or a per-user URL.                      |
| Ollama         | The server default `TA_OLLAMA_URL` or a per-user URL, and a model name. Streams its output. |
| MeCab          | The `mecab` extra (`pip install -e '.[mecab]'`; the Docker image includes it).             |
| JParser        | The EDICT2 dictionary, downloaded at **Admin → Dictionary** (or `TA_EDICT_PATH`).          |

Results are cached per backend and endpoint, so one user's server never answers for another's.

User-supplied LibreTranslate and Ollama URLs that resolve to a private, loopback, link-local or CGNAT
address are refused unless `TA_MT_ALLOW_PRIVATE_URLS=true` (for example, a LibreTranslate on your
LAN). The server defaults are operator-trusted and not checked. See [SECURITY.md](../SECURITY.md).

The EDICT2 dictionary is © the Electronic Dictionary Research and Development Group
(<https://www.edrdg.org/>), used under CC BY-SA 4.0.

## WordPress publishing

1. Install the Translation Assistant Publisher plugin on the WordPress site.
2. Enter its endpoint (site URL or `…/wp-json/ta-publisher/v1/publish`) and API key under
   **Settings → WordPress**.
3. Set each series' slug and short title on its series page.

Publish one chapter from its row's ⋯ menu, or select chapters and publish or schedule them as a
background job. Volumes have a **Publish illustrations** action. Re-publishing an already published
chapter asks for confirmation.

- The endpoint may not resolve to a private or local address unless `TA_WP_ALLOW_PRIVATE_URLS=true`.
- The server never follows a redirect from WordPress; save the address it redirects to instead.
- Images are downscaled to keep each request under the ~1 MB limit some hosts enforce; images over
  40 megapixels are sent unchanged.

## Statistics

The Statistics page shows a 52-week activity heatmap, today / 7-day / 30-day / all-time totals with
the change against the previous period, current and longest streaks, a per-day table, and a
per-series breakdown. Everything comes from the day each line was first translated, counted in the
viewer's time zone.

## Limits at a glance

| What                         | Limit                                                     |
|------------------------------|-----------------------------------------------------------|
| Lines per chapter            | 50,000                                                    |
| TXT file                     | 5 MiB, UTF-8 (BOM allowed), no NUL bytes                  |
| Cover image                  | 10 MiB; PNG, JPEG, GIF or WebP                            |
| Spellcheck request           | 200 texts, 100,000 characters each, 200,000 in total      |
| Desktop `ta.db` upload       | 1 GiB (100 MB through Cloudflare)                         |
