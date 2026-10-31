# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Mostly one person: the owner, a fan translator of Japanese web novels who runs their own server and does the
translating themselves. Accounts are invite-only and the app is multi-user, but no audience beyond the owner is a
design target today.

## Product Purpose

ta-web takes a Japanese web novel from source to published translation: fetch or import the chapters, translate them
line by line with glossary, memory and machine-translation aids, then publish to WordPress or export. It is the web
port of the Translation Assistant desktop app and carries over all of that app's features. Success means the owner can
do the whole job here, without juggling other tools.

## Positioning

The whole pipeline in one place. DeepL translates text and a CAT tool manages segments; neither also fetches the novel
from syosetu, holds the series' glossary and drafts, and schedules the chapters on the translator's own WordPress site.
When features compete, what keeps a chapter moving through that pipeline wins.

## Operating Context

- Long desktop sessions at a keyboard. Rebindable keys are how the editor work gets done, and the mouse is secondary.
- Pipeline: syosetu fetch, EPUB or TXT import, or a desktop `ta.db` import; then the editor, with one card per source
  line; then WordPress publishing, or TXT, Markdown, ZIP and EPUB export.
- Background work runs as jobs, including Ollama drafts in per-user night windows, and is reviewed in the editor later.
- The editor has a phone layout, but phone use is not a primary scene. Library and settings get only generic
  narrow-screen behaviour.

## Capabilities and Constraints

- Self-hosted on one server the owner runs (FastAPI, Postgres, React SPA, Caddy). Users bring their own MT, Ollama and
  WordPress credentials or servers.
- Terminology: series, volume, chapter, card (one source line in the editor), glossary, translation memory, suggestion
  (an Ollama draft for a line), job.
- Content is Japanese source text beside English translation, including author ruby and generated readings, so both
  scripts must stay legible together.
- Series can be large: lists run past 100 chapters and imports reach 900 chapters per book.

## Brand Commitments

Name: ta-web, the web port of Translation Assistant. There is no confirmed logo, voice guide or other brand asset.

## Evidence on Hand

- `README.md`: feature list. Its editor screenshot is still a placeholder.
- `docs/superpowers/specs/`: design specs for each feature, including the visual redesign and its mockup canvas.
- No testimonials, user numbers, benchmarks or press exist. Do not invent any.

## Product Principles

1. **Finish the pipeline here.** A step that forces the owner into another tool is a gap to close.
2. **The keyboard path comes first.** Editor actions must be reachable and fast without the mouse.
3. **Comfortable for hours.** The editor is a long-session workplace, so sustained focus outranks first impressions.
4. **Never lose the translator's work.** Saving, moves between chapters, restores and publishing state must be
   trustworthy and say plainly when they fail.
5. **Built for one expert.** Dense, precise tools are welcome. Don't simplify for a hypothetical newcomer.
