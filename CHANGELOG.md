# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There are no tagged releases yet; the
package version is `0.1.0`. Each entry links to the design spec or phase plan that describes it.

## [Unreleased]

### Added

- **Series glossaries.** Each series owns its glossary and a series dictionary; an account-wide
  dictionary and the parse characters live under Settings → Editor. Profiles are removed; the
  migration copies each series the glossary and words it used.
  ([spec](docs/superpowers/specs/2026-10-22-series-glossary-design.md))
- **Volume naming.** Volumes have a kind, an optional numeric index and a subtitle instead of a
  free title; the displayed and EPUB title come from a per-series template.
  ([spec](docs/superpowers/specs/2026-10-21-volume-naming-design.md))
- **Syosetu heading volumes.** Fetched chapters land in volumes by syosetu's chapter headings, with a
  previewable per-series mode. ([spec](docs/superpowers/specs/2026-10-21-syosetu-heading-volumes-design.md))
- **Library redesign.** Series-only library (bookshelf or list), a two-pane Volumes tab, selection
  bar, ZIP export of ticked chapters, and in-app dialogs.
  ([spec](docs/superpowers/specs/2026-10-20-library-redesign-design.md))
- **Job progress.** Running-jobs indicator in the header and resumable `ta.db` import.
  ([spec](docs/superpowers/specs/2026-10-19-job-progress-design.md))
- **Onboarding.** First-run setup wizard, admin server settings, usernames, in-browser EDICT2 download
  and `ta.db` import. ([spec](docs/superpowers/specs/2026-10-16-web-onboarding-design.md))
- **Phase 7a: visual system.** Design tokens, light and dark themes, self-hosted fonts.
  ([spec](docs/superpowers/specs/2026-10-14-web-redesign-design.md))
- **Phase 6b: publishing and statistics.** WordPress publish, batch publish and schedule, volume
  illustrations, and the Statistics page.
- **Phase 6a: acquisition.** Background jobs, syosetu fetch, batch TXT and EPUB import, per-volume
  EPUB build.
- **Phase 5: machine translation.** DeepL, LibreTranslate and Ollama (streamed), MeCab and JParser,
  with a shared cache.
- **Phase 4: memory.** Glossary and profiles, translation memory, series find and replace, phrase
  suggestions.
- **Phase 3: editor.** Line cards with save-as-you-type, rebindable keymap, find, spellcheck, inline
  images, Edit Source/Split; Caddy and the SPA.
- **Phase 2: library.** Series, volumes and chapters; reorder, renumber, merge and split; covers;
  TXT import; TXT and Markdown export.
- **Phase 1: skeleton.** FastAPI app, Postgres schema, invite-only session auth, per-user profiles,
  settings, shortcuts and encrypted credentials, and the desktop `ta.db` importer.

Phase plans: [`docs/superpowers/plans/`](docs/superpowers/plans/).

### Changed

- Deleting a series now deletes its volumes and chapters (chapters always belong to a series).
- Chapters are numbered per volume; each volume is a contiguous run.

## Migration notes

- The `api` container applies database migrations on start; without Docker, run
  `alembic upgrade head` after pulling. Back up first; see
  [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#backups).
- Volume titles from earlier builds are split into kind, index and subtitle by migration
  `6182106ad19b`. Review renamed volumes after upgrading.
