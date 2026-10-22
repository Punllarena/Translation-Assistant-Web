# Yomitan Dictionaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admins upload Yomitan dictionary zips; JParser and MeCab glosses look words up in them, in one admin-set order alongside EDICT2, as the same one-line entries as today.

**Architecture:** A pure reader (`api/core/yomitan_read.py` + `yomitan_gloss.py`) turns a zip into one flattened entry per lookup key. A job stores them in one Postgres table (`dictionary_terms`, one row per dictionary + key) in a single transaction. At analysis time JParser collects every candidate key of the line (substrings plus deconjugation bases), fetches them in one query, and layers the results with EDICT2's in-memory index in the admin's order (`api/mt/lookup.py`).

**Tech Stack:** FastAPI, SQLAlchemy 2 + Alembic, Postgres, pytest; React + TanStack Query, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-22-yomitan-dictionaries-design.md`

**Branch:** start from `main` on a new branch `claude/yomitan-dictionaries` (the current branch belongs to the open new-series PR). Task 1's first commit adds the spec and this plan.

## Global Constraints

- Only Yomitan format 3; zip upload cap 64 MiB (Caddy already allows it on `/api/admin/dictionary/*`).
- Admin-only; one order for every user; EDICT2 is in the order as token `"edict"`, Yomitan dictionaries as `"yomitan:<id>"`.
- Stored gloss: first two meanings joined with `"; "`, capped at 160 characters at a `"; "` boundary, ending in `…` when cut.
- Yomitan entries with an empty POS set are used for direct matches only, never deconjugated ones; EDICT2 keeps today's behaviour.
- JParser output shape unchanged: `surface, reading, lemma, pos, gloss, tense, base_form, matched`.
- Handlers only `flush()`; build routers with `api_router()`; no Python module over ~400 lines (`api/mt/jparser.py` is already ~430: it must not grow, so new lookup code goes in `api/mt/lookup.py`).
- Never commit 新和英 content. JMdict rows may be committed (CC BY-SA, attributed in the fixture README).
- Refusal messages (exact copy):
  - not a zip: `This is not a zip file; upload the Yomitan dictionary .zip.`
  - no `index.json`: `This zip has no index.json; it is not a Yomitan dictionary.`
  - wrong format: `Only Yomitan format 3 dictionaries are supported.`
  - no term banks: `This dictionary has no word definitions (kanji, frequency or pitch-accent dictionaries are not supported); use it in Yomitan instead.`
- Admin hint (exact copy): `JParser shows a one-line meaning. For full entries, install the Yomitan browser extension and import the same dictionaries there.` with a link to `https://yomitan.wiki`.

## Review Focus

1. A term bank with malformed rows (wrong field count, non-string expression, non-list glossary): the bad rows are skipped and counted (`skipped_rows` in the job result); the import still succeeds. Test in Task 2.
2. Hostile nesting in structured content (thousands of levels): no `RecursionError`; nodes below depth 64 are ignored. Test in Task 1.
3. The same zip uploaded twice: the second upload replaces the first (same id, same position), never a duplicate. Test in Task 3.
4. Yomitan dictionaries installed but no EDICT2 (and no Conjugations file): JParser works with direct matches; `NeedsSetup` only when neither EDICT2 nor any Yomitan dictionary exists. Test in Task 4.
5. Removing the dictionary at the top of the order: the stored order is normalised on read (unknown tokens dropped, missing ones appended, `"edict"` put first if absent). Test in Task 3.

---

### Task 1: Gloss flattening

**Files:**
- Create: `api/core/yomitan_gloss.py`
- Test: `tests/test_core_yomitan_gloss.py`
- Also commit: the spec and this plan

**Interfaces:**
- Produces: `meanings(glossary: list) -> list[str]`, `short_gloss(items: list[str], limit: int = 160) -> str`, `MAX_DEPTH = 64`.

- [ ] **Step 1: Commit the spec and plan on the new branch**

```bash
git switch main && git switch -c claude/yomitan-dictionaries
git add docs/superpowers/specs/2026-10-22-yomitan-dictionaries-design.md docs/superpowers/plans/2026-10-22-yomitan-dictionaries.md
git commit -m "docs: yomitan dictionaries design and plan"
```

- [ ] **Step 2: Write the failing tests**

Each test builds its glossary inline. Cases and expected results:

```python
def test_plain_and_text_items_images_and_deinflections_skipped():
    assert meanings(["cat", {"type": "text", "text": "feline"},
                     {"type": "image", "path": "x.png"}, ["食べる", ["v1"]]]) == ["cat", "feline"]

def test_structured_content_takes_only_glossary_marked_li():
    # the real JMdict 食べる sense-2 row's glossary, plus a references ul that must be ignored
    assert meanings(JMDICT_TABERU_2) == ["to live on (e.g. a salary)", "to live off", "to subsist on"]

def test_structured_content_without_markers_takes_li_and_skips_tables_ruby_and_notes():
    # ul > li "to eat" ; li with ruby 食<rt>た</rt> "べる" ; table ; div data.content=notes
    assert meanings(UNMARKED) == ["to eat", "食べる"]

def test_info_glossary_only_falls_back_to_all_text():
    assert meanings(JMDICT_VOICED_REPETITION) == ["voiced repetition mark in katakana"]

def test_multiline_string_drops_headword_xref_phrase_and_label_lines():
    text = ("ねこ【猫】 [ローマ字](neko)\n1 〔動物〕 a cat; 《口》 a puss.\n"
            "2 〔芸者〕 a geisha. [⇒げいしゃ]\n13 【俗】\n猫の手も借りたい　be extremely busy.\n")
    assert meanings([text]) == ["〔動物〕 a cat; 《口》 a puss.", "〔芸者〕 a geisha."]

def test_deep_nesting_is_cut_at_max_depth():
    node = "deep"
    for _ in range(5000):
        node = {"tag": "span", "content": node}
    assert meanings([{"type": "structured-content", "content": node}]) == []

def test_short_gloss_first_two_joined_and_capped_at_a_boundary():
    assert short_gloss(["to eat", "to live on", "third"]) == "to eat; to live on"
    long = "; ".join(f"word{i}" for i in range(60))
    out = short_gloss([long])
    assert len(out) <= 160 and out.endswith("…") and not out[:-1].endswith(";")
```

(The 新和英-shaped string above is invented look-alike text; keep it that way.)

- [ ] **Step 3: Run to verify they fail**

Run: `pytest tests/test_core_yomitan_gloss.py -v` → FAIL (module missing).

- [ ] **Step 4: Implement `api/core/yomitan_gloss.py`**

Rules exactly as spec §"Flattening one row" step 1. Skipped tags: `table`, `img`, `rt`, `rp`. Skipped `data.content` values: `forms`, `formsTable`, `references`, `example-sentence`, `examples`, `notes`, `attribution`. Headword line: contains `【` or `[ローマ字]`. Phrase line: contains U+3000. Cross-refs: remove `\[⇒[^\]]*\]` then drop the line if nothing Latin remains. Sense number: `^\d+\s+`. Iterative or depth-counted walk; anything deeper than `MAX_DEPTH` is ignored. Collapse whitespace; drop empties.

- [ ] **Step 5: Run to verify they pass**, then `ruff check api/core/yomitan_gloss.py tests/test_core_yomitan_gloss.py`.

- [ ] **Step 6: Commit** `feat: flatten yomitan glossaries to short meanings`

---

### Task 2: Reading a Yomitan zip

**Files:**
- Create: `api/core/yomitan_read.py`, `tests/fixtures/yomitan.py` (zip builder + the JMdict rows), `tests/fixtures/yomitan_README.md` (JMdict CC BY-SA attribution: EDRDG, edrdg.org)
- Test: `tests/test_core_yomitan_read.py`

**Interfaces:**
- Consumes: `meanings`, `short_gloss` (Task 1).
- Produces:
  - `class YomitanError(ValueError)`
  - `@dataclass(frozen=True) class Meta: title: str; revision: str; attribution: str; author: str; url: str; identity_key: str`
  - `@dataclass(frozen=True) class FlatEntry: headwords: tuple[str, ...]; reading: str; pos: frozenset[str]; gloss: str`
  - `@dataclass class Parsed: meta: Meta; terms: dict[str, FlatEntry]; entry_count: int; skipped_rows: int` (`terms` = lookup key → the winning entry for that key)
  - `identity_key(index: dict) -> str` → `"url:<indexUrl>"` when `indexUrl` is a non-empty string, else `"title:<title minus one trailing [..] part, stripped>"`
  - `read(path: str, on_bank: Callable[[int, int, str], None] | None = None) -> Parsed` (`on_bank(done, total, bank_name)` is called before each term bank; exceptions it raises propagate, which is how the job cancels)
  - limits: `MAX_MEMBERS = 2000`, `MAX_UNPACKED = 512 MiB`, `MAX_BANK = 64 MiB`, `MAX_ROWS = 3_000_000`
- `tests/fixtures/yomitan.py`: `make_zip(path, index: dict, banks: dict[str, list], extra: dict[str, bytes] | None = None) -> Path` and `JMDICT_ROWS` (the two real `食べる` rows, its `forms` row, the `ヾ` row) plus `JMDICT_TAGS` (only the tag-bank rows those use: `v1`, `vt`, `forms` with their real categories).

- [ ] **Step 1: Write the failing tests**

```python
def test_jmdict_rows_group_by_sequence_and_skip_forms(tmp_path):
    p = make_zip(tmp_path / "j.zip", JMDICT_INDEX, {"term_bank_1.json": JMDICT_ROWS, "tag_bank_1.json": JMDICT_TAGS})
    d = read(str(p))
    e = d.terms["食べる"]
    assert d.terms["たべる"] is e
    assert (e.reading, e.pos, e.gloss) == ("たべる", frozenset({"v1", "vt"}), "to eat; to live on (e.g. a salary)")
    assert d.meta.identity_key == "url:https://github.com/yomidevs/jmdict-yomitan/releases/latest/download/JMdict_english.json"

def test_shinwaei_shape_no_tags_rules_become_pos_and_untagged_rows_have_empty_pos(tmp_path): ...
    # index {"title":"新和英","format":3,"revision":"Shinwaei1","sequenced":true}, invented rows:
    # ["走る","はしる","","v5 v1",0,[<multi-line string>],1,""] and ["猫","ねこ","","",0,[...],2,""]
    # → pos {"v5","v1"} and frozenset(); identity "title:新和英"

def test_identity_strips_trailing_bracket(): assert identity_key({"title": "JMdict [2026-10-21]"}) == "title:JMdict"

def test_key_collision_prefers_score_then_popular_then_earlier_sequence(tmp_path): ...
def test_unsequenced_rows_group_by_expression_and_reading(tmp_path): ...
def test_malformed_rows_are_skipped_and_counted(tmp_path):  # Review Focus 1
    # rows: [1,2,3], ["猫","ねこ","","",0,"notalist",1,""], one good row → terms has the good one, skipped_rows == 2

@pytest.mark.parametrize("case,message", [
    ("not_zip", "This is not a zip file"), ("no_index", "has no index.json"),
    ("format2", "Only Yomitan format 3"), ("kanji_only", "has no word definitions"),
    ("meta_only", "has no word definitions"), ("traversal", "unsafe path"),
    ("too_big", "expands to more than"),
])
def test_refusals(tmp_path, case, message): ...  # each raises YomitanError matching message

def test_on_bank_reports_each_term_bank(tmp_path): ...  # two banks → calls (0,2,…), (1,2,…)
```

- [ ] **Step 2: Run to verify they fail:** `pytest tests/test_core_yomitan_read.py -v`

- [ ] **Step 3: Implement `api/core/yomitan_read.py`**

- Archive checks before reading anything, in the style of `api/core/epub_safety.py`: member count, absolute or `..` names (`unsafe path in dictionary: …`), summed `file_size`, each bank's `file_size`. Zip-level errors (`BadZipFile`, `zlib.error`, `UnicodeDecodeError`, `json` errors in `index.json`) become `YomitanError`. Read members by name; never extract.
- Banks are read one at a time with `json.loads(zf.read(name))`. Order: `tag_bank_*` first (POS names = rows whose category is `partOfSpeech`), then `term_bank_*` in numeric order.
- Row → group key: `("seq", sequence)` when `index.sequenced` and the sequence is a non-zero int, else `("form", expression, reading)`. Skip rows whose definition tags include `forms` (not counted as skipped) and rows that fail the shape check (counted).
- Group accumulates: `(score, file_order, meanings)` per row, headwords in first-seen order, first non-empty reading, POS = POS tags ∪ rule classes, `max_score`, `popular` (`⭐` or `P` in term tags).
- After all banks: build each entry (rows sorted by score desc, then file order; `gloss = short_gloss(all meanings)`; drop it if the gloss is empty). Keys = headwords + reading (reading defaults to the first headword). Per key, keep the entry with the best `(-max_score, not popular, first sequence/file order)`. `entry_count` = number of kept entries.
- `MAX_ROWS` exceeded → `YomitanError("The dictionary has more than 3,000,000 rows.")`.

- [ ] **Step 4: Run to verify they pass**; `ruff check .` on the new files.

- [ ] **Step 5: Commit** `feat: read and flatten yomitan dictionary zips`

---

### Task 3: Storage, order and fetch

**Files:**
- Create: `api/models/dictionaries.py`, `api/yomitan_store.py`, migration (autogenerate: `alembic revision --autogenerate -m "yomitan dictionaries"`)
- Modify: `api/models/__init__.py` (import + `__all__`), `api/mt/jparser.py` (`DictEntry` gains `deconj: bool = True` as its last field; no other change in this task)
- Test: `tests/test_yomitan_store.py`

**Interfaces:**
- Consumes: `Parsed`, `FlatEntry`, `Meta` (Task 2); `jparser.DictEntry`.
- Produces:
  - Models: `Dictionary` (`dictionaries`: `id`, `identity_key` String(600) unique, `title` String(256), `revision` String(256), `attribution` Text, `author` String(256), `url` String(1024), `entry_count` Integer, `installed_at` DateTime tz server_default now, `updated_at` DateTime tz). `DictionaryTerm` (`dictionary_terms`: `dictionary_id` FK `dictionaries.id` ondelete CASCADE, `key` Text, PK `(dictionary_id, key)`, `headwords` ARRAY(Text), `reading` Text, `pos` ARRAY(Text), `gloss` Text, index `ix_dictionary_terms_key` on `key`).
  - `ORDER_KEY = "dictionary_order"`, `EDICT = "edict"`, `token(dictionary_id: int) -> str` (`"yomitan:<id>"`)
  - `@dataclass class Installed: dictionary: Dictionary; replaced_revision: str | None`
  - `install(db: Session, parsed: Parsed) -> Installed` — insert or replace by `identity_key` (replace keeps the id, deletes its terms, updates the row's fields); terms inserted with Core `insert(DictionaryTerm)` in batches of 1,000; `flush()` only.
  - `installed(db) -> list[Dictionary]`
  - `order(db) -> list[str]` — the `server_settings` row `dictionary_order` (a JSON list of strings), normalised: drop tokens not installed, append installed ids missing from it (by id), put `"edict"` first if absent. Never writes.
  - `set_order(db, tokens: list[str], user_id: int) -> list[str]` — `ValueError("The order must list every dictionary exactly once.")` unless it's a permutation of `order(db)`; upserts the row like `server_settings.put` but without its validators (this key is not in `server_settings.KEYS`, so the admin settings list and reset never see it).
  - `remove(db, dictionary_id: int) -> bool`
  - `fetch(db, keys: Collection[str]) -> dict[str, dict[str, DictEntry]]` — token → key → `DictEntry(headwords, reading, frozenset(pos), gloss, common=False, deconj=bool(pos))`; one `SELECT … WHERE key = ANY(:keys)`; empty `keys` → `{}` without querying.

- [ ] **Step 1: Write the failing tests** (use the `db` fixture; build `Parsed` objects directly)

```python
def test_install_then_fetch_returns_entries_by_token(db): ...
    # fetch(db, {"食べる", "nope"}) == {"yomitan:<id>": {"食べる": DictEntry(..., deconj=True)}}
def test_entry_without_pos_cannot_deconjugate(db): ...   # deconj is False
def test_same_identity_replaces_in_place_and_keeps_position(db):  # Review Focus 3
    # install A, install B, set_order(["yomitan:B","edict","yomitan:A"]), reinstall A (new revision)
    # → same A id, old terms gone, replaced_revision == old, order unchanged
def test_order_normalises_after_removal_and_for_new_installs(db):  # Review Focus 5
    # set_order with A first; remove(A) → order == ["edict", "yomitan:B"]; install C → appended last
def test_set_order_rejects_non_permutations(db): ...       # missing, duplicate, unknown → ValueError
def test_order_row_is_not_an_admin_setting(db):
    # after set_order, server_settings.listing(db) has no "dictionary_order" key
```

- [ ] **Step 2: Run to verify they fail:** `pytest tests/test_yomitan_store.py -v`

- [ ] **Step 3: Add the models, register them in `api/models/__init__.py`, autogenerate the migration, `alembic upgrade head`**

Check the generated migration has both tables, the unique constraint, the PK and `ix_dictionary_terms_key`. If anything is missing, fix the model and regenerate (never hand-patch).

- [ ] **Step 4: Implement `api/yomitan_store.py`** and the `DictEntry.deconj` field.

- [ ] **Step 5: Run** `pytest tests/test_yomitan_store.py tests/test_mt_jparser.py tests/test_models.py tests/test_schema_roundtrip.py -v` → PASS.

- [ ] **Step 6: Commit** `feat: store yomitan dictionaries and their order`

---

### Task 4: Layered lookup in JParser and MeCab

**Files:**
- Create: `api/mt/lookup.py`
- Modify: `api/mt/jparser.py` (`deconjugate`, `run`; net size must not grow — move `_edict_path`/`_conj_path` into `lookup.py` if needed and update `api/mt/mecab.py` and `api/dictionary.py` callers), `api/mt/mecab.py`
- Test: `tests/test_mt_lookup.py`; update `tests/test_mt_jparser.py`, `tests/test_mt_mecab.py` where they assume the old `run`

**Interfaces:**
- Consumes: `yomitan_store.order`, `yomitan_store.fetch`, `EDICT` (Task 3); `jparser.load_index`, `load_rules`, `analyze`, `DeconjRule`, `DictEntry`.
- Produces:
  - `class Lookup(Mapping[str, DictEntry])`: `__init__(self, layers: list[Mapping[str, DictEntry]])`; `__getitem__`/`get` = first layer that has the key; `all(key) -> list[DictEntry]` in layer order.
  - `candidate_keys(text: str, rules: list[DeconjRule], max_len: int = 12) -> set[str]`: every substring of length 1..`max_len` that contains no whitespace, plus for substrings of length ≥ 2 each `stem + rule.base_suffix` where the substring ends with `rule.suffix`.
  - `session = SessionLocal` (seam the tests swap, like `api.jobs.SessionLocal`).
  - `layered(keys: set[str], edict: Mapping[str, DictEntry] | None) -> Lookup | None`: one session, `order()` then `fetch(keys)`; layers in order (EDICT2's index for `"edict"` when it isn't None); `None` when EDICT2 is None and no Yomitan dictionary is installed.
  - `jparser.deconjugate(word, rules, index)`: for a candidate base, try `index.all(base)` when `index` has `all`, else `[index.get(base)]`. Skip entries with `deconj=False`; take the first that passes the existing POS filter.
  - `jparser.run(text)`: `edict = load_index(...)`, `rules = load_rules(...)`, `lk = lookup.layered(candidate_keys(text, rules), edict)`; `None` → `NeedsSetup("JParser needs a dictionary. An admin can download EDICT2 or upload a Yomitan dictionary from Admin → Dictionary.")`; otherwise `analyze(text, lk, rules)`.
  - `mecab.run`: keys = each word's surface and lemma; `layered(keys, edict)`; gloss from `lk.get(...)` as today (empty gloss when `None`).

- [ ] **Step 1: Write the failing tests**

```python
def test_lookup_first_layer_wins_and_all_lists_in_order(): ...
def test_candidate_keys_include_substrings_and_deconjugation_bases():
    rules = jparser.load_rules(str(FX / "conjugations_sample.json"))
    keys = candidate_keys("行った猫", rules)
    assert {"行った", "猫", "行く"} <= keys and " " not in "".join(keys)

def test_order_decides_which_gloss_jparser_shows(db, lookup_session):
    # yomitan dict with 猫 → "cat (yomitan)"; EDICT2 sample says "cat"
    # order edict first → "cat"; set_order yomitan first → "cat (yomitan)"
def test_deconjugation_through_a_yomitan_v1_entry(db, lookup_session):
    # yomitan 食べる pos {"v1","vt"}, no EDICT2 entry for it → analyze("食べた") base_form 食べる, tense Past
def test_posless_yomitan_entry_does_not_hide_edict_for_deconjugation(db, lookup_session):
    # yomitan (first) has 行く with pos {} ; EDICT2 has 行く v5k-s → 行った resolves with EDICT2's gloss
def test_yomitan_only_without_edict_or_conjugations_works(db, lookup_session, monkeypatch):  # Review Focus 4
    # _edict_path/_conj_path → "" ; one yomitan dict → run("猫") matched; with none installed → NeedsSetup
def test_mecab_gloss_from_a_yomitan_only_word(db, lookup_session): ...  # skip if MeCab unavailable, like test_mt_mecab
```

`lookup_session` fixture: monkeypatch `api.mt.lookup.session` with a context manager yielding the test `db`.

- [ ] **Step 2: Run to verify they fail:** `pytest tests/test_mt_lookup.py -v`

- [ ] **Step 3: Implement** `api/mt/lookup.py` and the `jparser`/`mecab` changes.

- [ ] **Step 4: Run** `pytest tests/test_mt_lookup.py tests/test_mt_jparser.py tests/test_mt_mecab.py tests/test_mt_router.py tests/test_dictionary.py -v` → PASS. Check `wc -l api/mt/jparser.py` ≤ its size before this task.

- [ ] **Step 5: Commit** `feat: jparser and mecab look words up in yomitan dictionaries`

---

### Task 5: Upload job and admin API

**Files:**
- Create: `api/yomitan_job.py`
- Modify: `api/routers/dictionary.py`, `api/schemas/dictionary.py`, `api/main.py` (lifespan: also call `yomitan_job.sweep`)
- Test: `tests/test_yomitan_api.py`

**Interfaces:**
- Consumes: `read`, `YomitanError` (Task 2); `install`, `installed`, `order`, `set_order`, `remove`, `token` (Task 3); `jobs.handler`, `JobContext.report`, `JobError`.
- Produces:
  - `yomitan_job.MAX_UPLOAD = 64 * 1024 * 1024`; `upload_dir() -> Path` (`TA_DATA_DIR/uploads/yomitan`); `save_upload(file: UploadFile) -> str` (streams to `<hex>.zip`, 413 past the cap, 422 `This is not a zip file; upload the Yomitan dictionary .zip.` unless it starts with `PK\x03\x04`); `sweep(max_age=timedelta(hours=24)) -> int`.
  - Handler `yomitan_import`, params `{"upload": "<hex>"}`: `read(path, on_bank=lambda d, t, n: ctx.report(d, t, f"Reading {n}"))`, then `ctx.report(t, t, "Saving")` and `install(ctx.db, parsed)`. `YomitanError` → `JobError(str(exc))`. The zip is deleted in `finally`. Uses `report`, never `progress` (progress commits, and the install must stay one transaction). Result: `{"dictionary_id", "title", "revision", "entries", "skipped_rows", "message"}`, where message is `Installed <title> (<n:,> entries)` or `Updated <title> from <old> to <new>`.
  - Schemas: `YomitanDictOut(id, title, revision, attribution, author, url, entries, installed_at)`; `DictionaryOut` gains `yomitan: list[YomitanDictOut]` and `order: list[str]`; `OrderIn(order: list[str])`.
  - Routes (declared **before** the existing `/{kind}` routes so `yomitan`/`order` aren't parsed as a `Kind`):
    - `GET /admin/dictionary` now takes `db` and fills `yomitan` and `order`.
    - `POST /admin/dictionary/yomitan` → 202 `JobOut`; 409 `a dictionary upload is already running` when a `yomitan_import` job is queued or running.
    - `PUT /admin/dictionary/order` (`OrderIn`) → `{"order": [...]}`; 422 on `ValueError`.
    - `DELETE /admin/dictionary/yomitan/{dictionary_id}` → 204; 404 if unknown.

- [ ] **Step 1: Write the failing tests** (pattern: `tests/test_dict_job.py`'s `env` fixture — swap `jobs.SessionLocal` for the test `db`, `data_dir` to `tmp_path`; zips from `tests/fixtures/yomitan.make_zip`)

```python
def test_upload_installs_and_lists_with_order(app_client, env, tmp_path): ...
    # 202 → run_next() → job done, result.message "Installed JMdict [2026-10-21] (1 entries)"
    # GET → yomitan[0].title, order == ["edict", "yomitan:<id>"]; upload dir empty afterwards
def test_second_upload_of_same_dictionary_updates(app_client, env): ...  # message "Updated … from … to …"
def test_kanji_zip_fails_with_the_refusal_message(app_client, env): ...
def test_not_a_zip_is_422_before_any_job(app_client, env): ...
def test_cancel_leaves_nothing_installed(app_client, env, monkeypatch): ...
    # on_bank raises jobs.Cancelled on the second bank → job cancelled, installed(db) == []
def test_one_upload_at_a_time(app_client, env): ...   # second POST while queued → 409
def test_order_put_and_validation(app_client, env): ...  # good permutation 200; missing token 422
def test_delete_unknown_is_404_and_non_admin_is_refused(app_client, env, make_user, login): ...
def test_sweep_removes_old_uploads(tmp_path, monkeypatch): ...
```

- [ ] **Step 2: Run to verify they fail:** `pytest tests/test_yomitan_api.py -v`
- [ ] **Step 3: Implement** the job, schemas, routes and the lifespan sweep.
- [ ] **Step 4: Run** `pytest tests/test_yomitan_api.py tests/test_dict_job.py tests/test_dictionary.py tests/test_commit_boundary.py -v` → PASS; `ruff check .`
- [ ] **Step 5: Regenerate the client types:** `cd web && npm run gen:api`, and commit `web/src/api/schema.d.ts` with this task.
- [ ] **Step 6: Commit** `feat: admin upload, order and removal of yomitan dictionaries`

---

### Task 6: Admin panel and end-to-end flow

**Files:**
- Create: `web/src/admin/YomitanDictionaries.tsx`, `web/e2e/dictionaries.spec.ts`, `web/e2e/fixtures/yomitan-e2e.zip`
- Modify: `web/src/admin/DictionaryPanel.tsx` (render `<YomitanDictionaries />` below the EDICT2/Conjugations rows), `tools/e2e_seed.py` (this spec's own series and chapter)

**Interfaces:**
- Consumes: the Task 5 routes via the generated client; `JobProgress`, `postForm`, `ConfirmDialog` (`web/src/ui/Dialog.tsx`).

UI decisions:
- Heading "Yomitan dictionaries"; the hint copy from Global Constraints with a link to `https://yomitan.wiki`.
- File input `aria-label="Upload Yomitan dictionary"`, `accept=".zip"`; posts with `postForm`, then shows `JobProgress` for the returned job; resumes a running `yomitan_import` from `GET /jobs?active=true` (same pattern as the EDICT2 download). On a failed job, show its message in `role="alert"`; on done, show `result.message` in `role="status"` and refetch `["admin","dictionary"]`.
- An ordered list (`<ol aria-label="Dictionary order">`), one `<li>` per `order` token. EDICT2 shows "EDICT2" (plus "not installed" when absent). A Yomitan item shows title, revision, entry count and attribution. Each item has buttons `Move <name> up` / `Move <name> down` (disabled at the ends), which send the whole new order with `PUT /admin/dictionary/order`. Yomitan items also have `Remove <title>`, confirmed with `ConfirmDialog`.

- [ ] **Step 1: Build the e2e fixture zip** with `tests/fixtures/yomitan.make_zip`: index `{"title":"E2E Yomitan","format":3,"revision":"1"}`, one row `["ゆもたん語","ゆもたんご","","",0,["yomitan e2e gloss"],1,""]`. Write it to `web/e2e/fixtures/yomitan-e2e.zip`.
- [ ] **Step 2: Seed** a series "Yomitan spec" with one chapter whose first line is `ゆもたん語です` (the word occurs only in this spec's chapter).
- [ ] **Step 3: Write the failing e2e test** `an admin uploads a Yomitan dictionary and JParser uses it`:
  - upload the zip;
  - expect the status `Installed E2E Yomitan (1 entries)`;
  - expect the list to contain `E2E Yomitan` after `EDICT2`;
  - click `Move E2E Yomitan up` and expect it first;
  - open the seeded chapter and expect the JParser region to contain `yomitan e2e gloss`;
  - back in Admin, remove it and confirm; expect it gone.
- [ ] **Step 4: Run** `cd web && npx playwright test e2e/dictionaries.spec.ts` → FAIL.
- [ ] **Step 5: Implement** `YomitanDictionaries.tsx` and wire it into `DictionaryPanel.tsx`.
- [ ] **Step 6: Run** `cd web && npm test && npx tsc --noEmit && npx playwright test e2e/dictionaries.spec.ts e2e/admin.spec.ts e2e/mt.spec.ts` → PASS.
- [ ] **Step 7: Commit** `feat(web): manage yomitan dictionaries in Admin`

---

### Task 7: Real-dictionary check and docs

**Files:**
- Create: `tools/yomitan_check.py` (local only; reads zips by path, prints sample lines and timings, never writes)
- Modify: `CLAUDE.md` (one paragraph after the Phase 5 paragraph), `docs/TODO.md` (deferred: kanji, pitch accent, frequency, full entries)

- [ ] **Step 1: Write `tools/yomitan_check.py`**: `python -m tools.yomitan_check <zip>... [--line TEXT]`.
  - For each zip, print the `read()` stats (`entry_count`, `skipped_rows`, seconds).
  - Print 15 sample `(key, pos, gloss)` triples, including `食べる`, `取る`, `気`, `猫` when present.
  - With a database (`TA_DATABASE_URL`), install every zip into it and time `jparser.run(line)` over 20 runs. Print the median and the max.
- [ ] **Step 2: Run it** on `C:/Users/Pun The Bread/Downloads/JMdict_english.zip` and `C:/Users/Pun The Bread/Downloads/[Bilingual] 新和英.zip` against a scratch database with a ≈60-character line of novel text.
  - Expected: both read without errors, KANJIDIC is refused, the 新和英 glosses read like `〔…〕 eat; take; have; …` with no headword lines or `[⇒…]`, and the median line time is under 100 ms.
  - If a gloss looks wrong, adjust the Task 1 rules and add a look-alike test case for it (never real 新和英 text).
  - Record the numbers for the PR description.
- [ ] **Step 3: Update `CLAUDE.md`.** Add a paragraph covering:
  - the `dictionary_terms` table, `api/core/yomitan_read.py` and `yomitan_gloss.py`, `api/yomitan_store.py`, `api/mt/lookup.py`;
  - the `dictionary_order` server_settings row (tokens `edict` / `yomitan:<id>`), and that it is not an admin setting;
  - the `yomitan_import` job;
  - the rule that a POS-less Yomitan entry is direct-only;
  - the 64 MiB upload cap.

  Then add the deferred items to `docs/TODO.md`.
- [ ] **Step 4: Full check.**
  - Python: `ruff check . && pytest`.
  - Web: `cd web && npm test && npm run e2e`.
  - All of it must pass.
- [ ] **Step 5: Commit** `docs: yomitan dictionaries; local check tool`
