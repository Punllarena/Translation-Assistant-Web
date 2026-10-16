"""Desktop ta.db builder shared by the importer tests."""

import sqlite3
from pathlib import Path

# Copied verbatim from the desktop app's source of truth,
# TranslationAssistant-PySide6-Port/translation_assistant/db.py: the `_DDL` constant
# (without its PRAGMAs, which SQLite applies per connection) ...
DESKTOP_DDL = """
CREATE TABLE IF NOT EXISTS profiles (
    id          INTEGER PRIMARY KEY,
    name        TEXT    UNIQUE NOT NULL,
    parse_chars TEXT    NOT NULL
                        DEFAULT '、 。 ？ ！ 「 」 …… ',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    is_default  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS glossary (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    phrase      TEXT    NOT NULL,
    translation TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(profile_id, phrase)
);

CREATE INDEX IF NOT EXISTS idx_glossary_profile ON glossary(profile_id, sort_order);

CREATE TABLE IF NOT EXISTS custom_words (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    word        TEXT    NOT NULL COLLATE NOCASE,
    UNIQUE(profile_id, word)
);

CREATE INDEX IF NOT EXISTS idx_words_profile ON custom_words(profile_id);

CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY,
    title           TEXT    NOT NULL,
    source_language TEXT    NOT NULL DEFAULT 'ja',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    last_position   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lines (
    id              INTEGER PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL,
    prefix          TEXT    NOT NULL DEFAULT '%',
    raw_text        TEXT    NOT NULL,
    translated_text TEXT    NOT NULL DEFAULT '',
    UNIQUE(document_id, line_number)
);

CREATE INDEX IF NOT EXISTS idx_lines_document ON lines(document_id, line_number);

CREATE TABLE IF NOT EXISTS document_images (
    id              INTEGER PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    anchor_position INTEGER NOT NULL DEFAULT 0,
    is_cover        INTEGER NOT NULL DEFAULT 0,
    src_path        TEXT    NOT NULL,
    data            BLOB    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_document_images_doc ON document_images(document_id, anchor_position);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS series_profiles (
    series_title TEXT PRIMARY KEY,
    profile_name TEXT NOT NULL DEFAULT ''
);
"""

# ... and the idempotent `ALTER TABLE` chain `Database._apply_schema` runs after it, in
# the same order. A ta.db written by an older desktop build has only a prefix of these,
# which is the tolerance `_get`/OPTIONAL_COLUMNS exists for.
DESKTOP_ALTERS = [
    "ALTER TABLE documents ADD COLUMN series_title TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN series_order INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE documents ADD COLUMN chapter_title TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_title TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_author TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_illustrator TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_publisher TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_identifier TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE series_profiles ADD COLUMN syosetu_url TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE series_profiles ADD COLUMN series_slug TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE series_profiles ADD COLUMN series_title_short TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE series_profiles ADD COLUMN wp_password_enabled TEXT DEFAULT NULL",
    "ALTER TABLE series_profiles ADD COLUMN wp_unlock_after INTEGER NOT NULL DEFAULT -1",
    "ALTER TABLE documents ADD COLUMN source_url TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN wp_status TEXT DEFAULT NULL",
    "ALTER TABLE documents ADD COLUMN wp_post_url TEXT DEFAULT NULL",
    "ALTER TABLE documents ADD COLUMN wp_date TEXT DEFAULT NULL",
    "ALTER TABLE documents ADD COLUMN wp_chapter_index INTEGER DEFAULT NULL",
    "ALTER TABLE lines ADD COLUMN translated_at TEXT DEFAULT NULL",
    "ALTER TABLE document_images ADD COLUMN exclude_export INTEGER NOT NULL DEFAULT 0",
]

# The columns an older build's file lacks, in the variant exercised below.
OLDER_BUILD_LACKS = ("translated_at", "volume_title", "exclude_export", "source_url")


def desktop_db(tmp_path: Path, *, with_optional_columns: bool = True) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "ta.db"
    conn = sqlite3.connect(path)
    conn.executescript(DESKTOP_DDL)
    alters = DESKTOP_ALTERS
    if not with_optional_columns:
        alters = [
            a for a in DESKTOP_ALTERS if not any(c in a for c in OLDER_BUILD_LACKS)
        ]
        assert len(alters) == len(DESKTOP_ALTERS) - len(OLDER_BUILD_LACKS)
    for statement in alters:
        conn.execute(statement)
    conn.execute("INSERT INTO profiles (name, parse_chars, is_default) VALUES ('wn', '。！', 1)")
    sp_cols = "series_title, profile_name, syosetu_url, series_slug, series_title_short"
    sp_vals = "('My Series', 'wn', 'https://ncode.syosetu.com/n0000a/', 'my-series', 'MS')"
    if with_optional_columns:
        sp_cols += ", wp_password_enabled, wp_unlock_after"
        sp_vals = (
            "('My Series', 'wn', 'https://ncode.syosetu.com/n0000a/', 'my-series', 'MS', '1', 3)"
        )
    conn.execute(f"INSERT INTO series_profiles ({sp_cols}) VALUES {sp_vals}")
    cols = (
        "title, series_title, series_order, chapter_title, wp_status, last_position, "
        "wp_post_url, wp_date, wp_chapter_index"
    )
    vals = (
        "('Chapter 1', 'My Series', 7, 'Chapter 1 - The Start', 'publish', 3, "
        "'https://blog/ch1', '2024-05-06T07:08:09Z', 11)"
    )
    if with_optional_columns:
        cols += ", volume_title, volume_author, volume_illustrator, volume_publisher, " \
                "volume_identifier, source_url"
        vals = vals[:-1] + (
            ", 'Volume 1', 'Author A', 'Illustrator A', 'Publisher A', 'urn:isbn:1', "
            "'https://src/1')"
        )
    conn.execute(f"INSERT INTO documents ({cols}) VALUES {vals}")
    line_cols = "document_id, line_number, prefix, raw_text, translated_text"
    stamp = ", translated_at" if with_optional_columns else ""
    sval = ", '2024-05-06 07:08:09'" if with_optional_columns else ""
    conn.execute(
        f"INSERT INTO lines ({line_cols}{stamp}) VALUES (1, 0, '%', '一行目', 'Line one'{sval})"
    )
    conn.execute(f"INSERT INTO lines ({line_cols}) VALUES (1, 1, '$', '二行目', '')")
    excl = ", exclude_export" if with_optional_columns else ""
    eval_ = ", 1" if with_optional_columns else ""
    conn.execute(
        f"INSERT INTO document_images (document_id, anchor_position, is_cover, src_path, data"
        f"{excl}) VALUES (1, 5, 1, 'cover.jpg', X'FFD8FF'{eval_})"
    )
    conn.commit()
    conn.close()
    return path


def add_chapter(path: Path, title: str, *, series: str = "My Series") -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO documents (title, series_title, series_order, volume_title) "
        "VALUES (?, ?, 9, 'Volume 1')",
        (title, series),
    )
    doc_id = conn.execute("SELECT id FROM documents WHERE title = ?", (title,)).fetchone()[0]
    conn.execute(
        "INSERT INTO lines (document_id, line_number, prefix, raw_text, translated_text) "
        "VALUES (?, 0, '%', '新しい行', 'A new line')",
        (doc_id,),
    )
    conn.commit()
    conn.close()
