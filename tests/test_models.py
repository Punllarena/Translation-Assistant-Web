from api.db import Base
from api.models import Document, Line, Profile, Series, User


def test_every_spec_table_is_mapped():
    expected = {
        "users", "sessions", "invites", "profiles", "user_settings", "shortcuts",
        "api_credentials", "series", "volumes", "documents", "lines",
        "document_images", "mt_cache", "work_sessions",
    }
    assert expected <= set(Base.metadata.tables)


def test_user_owned_tables_carry_user_id():
    for table in ("profiles", "series", "documents", "work_sessions", "api_credentials"):
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
    assert Profile.user.property.mapper.class_ is User
