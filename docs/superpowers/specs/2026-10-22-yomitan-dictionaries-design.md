# Yomitan dictionaries — design

## Intent

JParser (and MeCab's glosses) can only read EDICT2 today. The Yomitan community already publishes
many dictionaries in one well-documented format, so instead of writing an importer per dictionary,
the admin uploads Yomitan `.zip` files and JParser looks words up in them alongside EDICT2.

The app keeps its inline view: one short line per word (surface, reading, part of speech, first two
meanings). Anyone who wants full entries — example sentences, grammar notes, pitch accent, kanji
details — uses the Yomitan browser extension next to the app; the admin page says so.

Dictionaries the user plans to load first: [Bilingual] JMdict, [Bilingual] 新和英. (KANJIDIC, the
Dictionary of Japanese Grammar and アクセント辞典v2 are also on their list; see Non-goals.)

## Goals

- Admin uploads a Yomitan dictionary zip; it is validated, flattened into short entries and stored.
- Admin sees installed dictionaries (title, revision, entry count, attribution), can delete them, and
  sets one priority order that includes EDICT2. The order applies to every user.
- JParser lookups (direct and deconjugated) and MeCab glosses use every installed dictionary: for a
  given key, the first dictionary in the order that has it supplies the entry.
- JParser output shape is unchanged (`surface, reading, lemma, pos, gloss, tense, base_form, matched`).

## Non-goals

- Full entries, popups, example sentences, images, formatting.
- Kanji dictionaries (`kanji_bank_*`), frequency / pitch-accent metadata (`term_meta_bank_*`,
  `kanji_meta_bank_*`). A zip with no `term_bank_*.json` is refused with
  "This dictionary has no word definitions (kanji, frequency or pitch-accent dictionaries are not
  supported); use it in Yomitan instead." Meta and kanji banks inside a zip that also has term
  banks are ignored.
- Per-user dictionaries, per-user enable/disable or ordering.
- Detecting "long-form" dictionaries such as the grammar dictionary: anything with term banks is
  accepted; if it gives clipped lines the admin deletes it. (Decided with the user.)
- Downloading dictionaries from a URL (Yomitan's `downloadUrl` / `indexUrl` are ignored).
- Replacing EDICT2 or the Conjugations file; both keep working exactly as now.

## The Yomitan format (what is parsed)

Reference: the Yomitan dictionary schemas (`dictionary-index-schema.json`,
`dictionary-term-bank-v3-schema.json`, `dictionary-tag-bank-v3-schema.json`) in
github.com/yomidevs/yomitan, `ext/data/schemas/`.

- `index.json`: `title` (required), `revision` (required), `format` (or legacy `version`),
  `sequenced`, `attribution`, `author`, `url`, `description`. Only format 3 is accepted
  (422 otherwise: "Only Yomitan format 3 dictionaries are supported").
- `tag_bank_N.json`: rows `[name, category, order, notes, score]`. Used to decide which definition
  tags are parts of speech (`category == "partOfSpeech"`).
- `term_bank_N.json`: rows of 8 fields
  `[expression, reading, definitionTags, rules, score, glossary, sequence, termTags]`, e.g.
  `["食べる","たべる","1 v1 vt","v1",1999800,[…],1358280,"⭐ ichi news13k"]`.
  - `rules`: space-separated deinflection classes. Yomitan's set is `v1 v5 vk vs vz adj-i`
    (all that occur in JMdict); others may appear in other dictionaries and are kept as-is.
  - `glossary`: array of items, each a plain string, `{"type":"text","text":…}`,
    `{"type":"image",…}`, `{"type":"structured-content","content":…}`, or a
    `[uninflected, [rules…]]` deinflection pair.
  - `reading` may be `""`, meaning the reading equals the expression.

### Flattening one row

1. **Gloss text** from `glossary`, item by item: plain strings and `text` items as-is; images and
   deinflection pairs skipped; structured content walked as a tree (`content` is a string, a node,
   or a list) collecting text. Inside structured content:
   - If the tree contains nodes with `data.content == "glossary"`, take only the text of their
     `li` children (one meaning per `li`); everything else in the tree is ignored.
   - Otherwise take the text of every `li`, or the whole text if there are no `li`s, skipping
     `table`, `img`, `rt`/`rp` (furigana) and nodes whose `data.content` is one of
     `forms`, `formsTable`, `references`, `example-sentence`, `examples`, `notes`, `attribution`.
   - Whitespace is collapsed; empty meanings are dropped.
   - **Multi-line plain strings** (the 新和英 shape, see below) are split into lines and each line
     is a candidate meaning: drop the first line when it is a headword line (contains `【` or
     `[ローマ字]`); drop cross-reference lines and trailing cross-references (`[⇒…]`); drop
     phrase lines (a Japanese phrase, U+3000, then its English); drop lines with no Latin letters
     (bare field labels such as `13 【数】`); strip a leading sense number (`1 `, `2 `). Keep
     `〔…〕` sense labels and `《…》` usage notes; they help a translator pick the sense.
   - The stored gloss is capped at 160 characters, cut at a `; ` boundary (ending in `…` when cut),
     because one 新和英 sense line can list many equivalents.
2. Rows whose definition tags contain `forms` (JMdict's spelling-table rows) are skipped; so is a row
   whose gloss ends up empty.
3. **Grouping into one entry:** rows with the same `sequence` (when `index.sequenced` is true and the
   sequence is non-zero) are one entry; otherwise rows with the same `(expression, reading)` are.
   Within an entry, rows are ordered by `score` descending, then file order. The entry's meanings are
   the concatenation of its rows' meanings; the stored gloss is the first two joined with `"; "`,
   matching `_clean_gloss` in `api/mt/jparser.py`. An entry's headwords are all distinct expressions
   in the group; its reading is the first non-empty reading (or the expression).
4. **Part of speech:** definition tags of the entry's rows whose tag-bank category is
   `partOfSpeech`, plus the `rules` classes. Numeric sense tags (`1`, `2`) and unknown tags are
   dropped. Stored as the same frozenset JParser keeps for EDICT2.
5. **Priority within a dictionary** (two entries share a key): higher max `score` wins, then a `⭐`
   or `P` term tag, then earlier sequence. This replaces EDICT2's `(P)` rule for Yomitan entries.

### What the two target dictionaries look like (checked 2026-10-22)

| | JMdict (`JMdict [2026-10-21]`) | 新和英 (`新和英`, revision `Shinwaei1`) |
|---|---|---|
| Zip / unpacked | 15.6 MB / ~170 MB | 8.1 MB / 26 MB |
| Rows | 527,474 (≈147k `forms` rows) | 152,202 |
| Tag bank | 91 `partOfSpeech` tags, plus others | none |
| Definition tags | POS, sense numbers, notes | none |
| `rules` | `v1 v5 vk vs vz adj-i` | `v5 v1 adj-i vs vz` on ~11k rows; verbs carry both `v5 v1`; ~141k rows have neither tags nor rules |
| Glossary | structured content with `data.content` markers | one plain multi-line string per row: headword line, numbered sense lines with `〔…〕` labels and `《…》` notes, phrase lines, `[⇒…]` cross-refs |
| `indexUrl` | yes | no |
| Sequenced | yes, never 0 | yes |

Consequences: most 新和英 entries have no part of speech, so under the rule below they serve
direct matches only; its verbs take part in deconjugation loosely (both `v5` and `v1` pass the
filter). The 64 MiB upload cap and the zip limits above fit both. KANJIDIC (`kanji_bank` +
`tag_bank`, no `term_bank`) is refused, as intended.

Example: the two `食べる` rows (sequence 1358280, `v1 vt`) become one entry: headwords `食べる`,
reading `たべる`, pos `{v1, vt}`, gloss `to eat; to live on (e.g. a salary)`.

### Deconjugation

The Conjugations file stays the source of deconjugation rules. `deconjugate()` filters candidates by
part of speech with a prefix match (`v5` matches rule type `v5k`); for Yomitan entries the `rules`
classes are part of the POS set, so that filter works without change. No Yomitan-specific
deinflector is added.

Entries with no part of speech (decision: designer's call). `deconjugate()` today lets an EDICT2
entry with no POS tags match every rule; EDICT2 keeps that. A Yomitan entry whose POS set is empty
(no POS-category tags and no `rules`) is used for direct matches only, never for deconjugated
ones. For a deconjugation candidate base, the merged view tries each dictionary in order and takes
the first entry that passes the POS filter, so a POS-less or mismatched entry higher in the order
does not hide a matching one lower down. Direct matches stay first-hit-wins.

## Upload and storage

- `POST /admin/dictionary/yomitan` (admin, multipart `file`) saves the zip under
  `TA_DATA_DIR/uploads/` and enqueues a `yomitan_import` job (`api/yomitan_job.py`), returning the
  job (202). One `yomitan_import` job at a time (409 otherwise), like `dict_download`.
- Caddy already allows 64 MiB on `/api/admin/dictionary/*`; the API caps the upload at the same
  64 MiB (both target zips are well under it).
- Zip safety, in the style of `api/core/epub_safety.py`: cap entry count, per-entry and total
  uncompressed size (well above JMdict's ~170 MB unpacked; e.g. 512 MiB total, 64 MiB per bank),
  refuse paths with `..` or absolute names, read banks one at a time (never extract to disk).
- The job validates `index.json`, then flattens bank by bank, reporting progress per bank through
  `JobContext.progress`, and writes entries in batches. Cancel or failure leaves nothing installed
  (one transaction for the dictionary's rows, or a `ready` flag flipped at the end). The uploaded
  zip is deleted when the job ends; stale uploads go with the existing 24 h sweep.
- **Same dictionary, newer release** (decision: designer's call). Titles carry the release date
  (`"JMdict [2026-10-21]"`), so the title alone can't identify a dictionary. Its identity key is:
  `indexUrl` when present (stable across releases of updatable dictionaries), otherwise the title
  with one trailing bracketed part removed and whitespace trimmed (`"JMdict"`). An upload whose key
  matches an installed dictionary replaces it in place and keeps its position in the order (the
  result message says "Updated <title> from <old revision> to <new revision>"); otherwise it is
  added at the end of the order.

Tables (autogenerated migration, models in `api/models/`):

- `dictionaries`: id, identity_key (unique), title, revision, attribution, author, url, entry_count,
  installed_at, updated_at.
- `dictionary_terms`: one row per dictionary + lookup key (PK `(dictionary_id, key)`, index on
  `key`), holding the winning entry for that key (step 5): headwords, reading, pos, gloss.
  Denormalised on purpose so a lookup is one indexed query with no join.

EDICT2 is not a row in `dictionaries` (it stays a file, possibly env-provided). The order is one
`server_settings` row, `dictionary_order`: a JSON list of tokens `"edict"` and `"yomitan:<id>"`.
It isn't one of the admin settings (`server_settings.KEYS`), and it's normalised on read: unknown
tokens are dropped, installed dictionaries missing from it are appended, and `"edict"` goes first
when absent.

API (all admin-only, `api/routers/dictionary.py`):

- `GET /admin/dictionary` gains `yomitan: [...]` and `order: [...]` (EDICT2 included).
- `PUT /admin/dictionary/order` with the full ordered list (422 if it is not a permutation of the
  installed set).
- `DELETE /admin/dictionary/yomitan/{id}` (404 for an unknown id).

## Lookup

JParser's `analyze()` and `deconjugate()` take something that answers `get(key) -> DictEntry | None`
and `key in index`; today that is a `dict` from `load_index()`. It becomes a merged view over the
order: EDICT2's index plus each Yomitan dictionary, first hit wins.

Storage shape (decision: designer's call): Yomitan entries are looked up in Postgres, not loaded into
memory. JMdict alone is ~164 MB of JSON (~380k rows after `forms` rows are skipped) and 新和英 is
larger; holding them in the API process the way EDICT2 is held would multiply its memory. EDICT2
stays in memory exactly as today.

- A `dictionary_keys` table (or equivalent) maps each lookup key — every headword and the reading
  of each entry — to its entry, indexed on `(key)`.
- `analyze()` first collects every candidate key for the text: all substrings of up to 12
  characters, plus the deconjugation bases the Conjugations rules produce for them. One
  `key = ANY(:keys)` query (joined to `dictionaries` for position) fetches the matches. The greedy
  match then runs against that prefetched map merged with EDICT2's index, so `analyze()` and
  `deconjugate()` keep their current shape (they see a mapping).
- Analysing a typical line (≈60 characters) must stay well under 100 ms with JMdict and 新和英
  installed; measure it and record the number in the PR. If the single query is too slow, batch by
  position, but keep it to a small fixed number of queries per line.
- Uploads, deletes and reorders are visible to the next lookup with no cache to invalidate.

MeCab's gloss lookup (`api/mt/mecab.py`) uses the same prefetch over its lemmas and surfaces.

JParser with no EDICT2 but at least one Yomitan dictionary works; `NeedsSetup` only when neither is
installed (message updated to mention Yomitan dictionaries).

## Admin UI (`web/src/admin/DictionaryPanel.tsx`)

- New "Yomitan dictionaries" part under the EDICT2/Conjugations rows: an upload input (`.zip`), job
  progress via `JobProgress` (resumed from `GET /jobs?active=true` like the EDICT2 download), and the
  ordered list: title, revision, entry count, attribution (shown, since licences require it), Move
  up / Move down, Remove (through `ConfirmDialog`). EDICT2 appears in the same list for ordering.
- A hint: "JParser shows a one-line meaning. For full entries, install the Yomitan browser extension
  and import the same dictionaries there." with a link to yomitan.wiki.
- Refusals (no term banks, wrong format, too large, malformed) show the job's or request's message.

If the panel module grows past ~150 lines, split the Yomitan part into its own component.

## Testing

- Unit: flattening (strings, text items, structured content with and without `data.content`
  markers, forms rows skipped, grouping by sequence and by expression/reading, POS from tag bank,
  priority), using small hand-made banks under `tests/fixtures/yomitan/` plus trimmed real rows from
  JMdict and 新和英.
- Zip safety: path traversal, oversize entry, too many entries, missing `index.json`, format 2,
  kanji-only and meta-only zips refused with the messages above.
- Job: dry install of a tiny zip via `jobs.run_next()`; cancel leaves nothing; same-title replace
  keeps position.
- Lookup: merged order (EDICT2 first vs Yomitan first changes the gloss), deconjugation through a
  Yomitan `v1` entry (`食べた` → `食べる`), MeCab gloss from a Yomitan-only word.
- API: admin-only, order validation, delete 404.
- E2E: one Playwright flow uploading a tiny fixture zip, reordering, and seeing JParser use it.

Fixtures: trimmed real JMdict rows may be committed (CC BY-SA, attribute in the fixture's
README). 新和英 is commercial Kenkyusha content, so no rows of it are committed: its fixtures are
hand-made look-alikes with the same tree structure, and the check against the real zip happens
locally, outside the test suite.

## Left to the builder

- How EDICT2's position is stored.
- Exact zip limits; fine-tuning the skip rules after running them over both real zips locally
  (the user has them in their Downloads folder; never commit 新和英 content).
- Module boundaries (`api/core/yomitan.py` for parsing, keeping every module under ~400 lines).
