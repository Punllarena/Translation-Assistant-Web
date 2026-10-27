from sqlalchemy.orm import configure_mappers

from api.db import Base
from api.models import CustomWord, Document, GlossaryEntry, Line, Series


def test_every_spec_table_is_mapped():
    expected = {
        "users", "sessions", "invites", "user_settings", "shortcuts",
        "api_credentials", "series", "volumes", "documents", "lines",
        "document_images", "mt_cache", "work_sessions", "glossary", "custom_words",
    }
    assert expected <= set(Base.metadata.tables)
    assert "profiles" not in Base.metadata.tables


def test_user_owned_tables_carry_user_id():
    for table in ("custom_words", "series", "documents", "work_sessions", "api_credentials"):
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
    assert Series.glossary.property.mapper.class_ is GlossaryEntry
    assert Series.custom_words.property.mapper.class_ is CustomWord


def _fks_by_table_column(table_name):
    return {fk.parent.name: fk for fk in Base.metadata.tables[table_name].foreign_keys}


def test_user_referencing_foreign_keys_cascade_on_delete():
    tables = (
        "sessions", "invites", "user_settings", "shortcuts", "custom_words",
        "api_credentials", "series", "documents", "work_sessions",
    )
    for table in tables:
        fks = [
            fk for fk in Base.metadata.tables[table].foreign_keys
            if fk.column.table.name == "users"
        ]
        assert fks, f"{table} has no foreign key to users"
        for fk in fks:
            assert fk.ondelete == "CASCADE", f"{table}.{fk.parent.name} ondelete={fk.ondelete}"


def test_set_null_foreign_keys_are_exactly_the_expected():
    set_null = {
        (table.name, fk.parent.name)
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
        if fk.ondelete == "SET NULL"
    }
    assert set_null == {
        ("documents", "volume_id"),
        ("server_settings", "updated_by"),
        # Chunk rows outlive what they were made from, so usage statistics keep them.
        ("ollama_chunks", "series_id"),
        ("ollama_chunks", "document_id"),
        ("ollama_chunks", "job_id"),
    }


def test_set_null_targets_are_indexed():
    for table, column in (("documents", "volume_id"),):
        indexed = {
            tuple(c.name for c in idx.columns) for idx in Base.metadata.tables[table].indexes
        }
        assert (column,) in indexed, f"{table}.{column} is not indexed"


def test_mappers_configure_cleanly():
    configure_mappers()


def test_desktop_only_fields_have_a_destination_column():
    """Fields the desktop ta.db carries that phases 2 and 6 need (see the importer)."""
    documents = Base.metadata.tables["documents"].columns
    for name in ("chapter_title", "wp_post_url", "wp_chapter_index"):
        assert name in documents
    volumes = Base.metadata.tables["volumes"].columns
    for name in ("epub_author", "epub_illustrator", "epub_publisher", "epub_identifier"):
        assert name in volumes
