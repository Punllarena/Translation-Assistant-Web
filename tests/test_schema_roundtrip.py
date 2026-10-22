import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from api.models import CustomWord, Document, Line, Series, User


def test_migration_created_every_table(db):
    names = set(inspect(db.get_bind()).get_table_names())
    assert {"users", "sessions", "invites", "glossary", "custom_words", "documents",
            "lines"} <= names
    assert "profiles" not in names


def test_insert_and_read_back_a_document_tree(db):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()
    series = Series(user_id=user.id, title="S1")
    db.add(series)
    db.flush()
    doc = Document(user_id=user.id, series_id=series.id, title="Chapter 1")
    db.add(doc)
    db.flush()
    db.add_all([
        Line(document_id=doc.id, line_number=0, prefix="%", raw_text="一行目"),
        Line(document_id=doc.id, line_number=1, prefix="$", raw_text="二行目"),
    ])
    db.flush()
    rows = db.query(Line).filter_by(document_id=doc.id).order_by(Line.line_number).all()
    assert [r.raw_text for r in rows] == ["一行目", "二行目"]
    assert rows[0].translated_text == ""


def test_deleting_a_document_cascades_to_lines(db):
    user = User(email="b@example.com", password_hash="x")
    db.add(user)
    db.flush()
    series = Series(user_id=user.id, title="S2")
    db.add(series)
    db.flush()
    doc = Document(user_id=user.id, series_id=series.id, title="Chapter 2")
    db.add(doc)
    db.flush()
    db.add(Line(document_id=doc.id, line_number=0, prefix="%", raw_text="x"))
    db.flush()
    db.execute(text("DELETE FROM documents WHERE id = :i"), {"i": doc.id})
    assert db.query(Line).filter_by(document_id=doc.id).count() == 0


@pytest.mark.parametrize("dupe_in_series", [True, False])
def test_custom_words_unique_per_list(db, dupe_in_series):
    user = User(email="c@example.com", password_hash="x")
    db.add(user)
    db.flush()
    s1, s2 = Series(user_id=user.id, title="S1"), Series(user_id=user.id, title="S2")
    db.add_all([s1, s2])
    db.flush()
    db.add_all([
        CustomWord(user_id=user.id, series_id=s1.id, word="Apple"),
        CustomWord(user_id=user.id, series_id=s2.id, word="apple"),
        CustomWord(user_id=user.id, series_id=None, word="apple"),
    ])
    db.flush()
    db.add(CustomWord(user_id=user.id, series_id=s1.id if dupe_in_series else None,
                      word="APPLE"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_deleting_a_series_takes_its_glossary_and_words(db):
    from api.models import GlossaryEntry

    user = User(email="d@example.com", password_hash="x")
    db.add(user)
    db.flush()
    series = Series(user_id=user.id, title="S")
    db.add(series)
    db.flush()
    db.add_all([
        GlossaryEntry(series_id=series.id, phrase="太郎", translation="Taro"),
        CustomWord(user_id=user.id, series_id=series.id, word="Rimuru"),
        CustomWord(user_id=user.id, word="senpai"),
    ])
    db.flush()
    db.delete(series)
    db.flush()
    assert db.query(GlossaryEntry).count() == 0
    assert [w.word for w in db.query(CustomWord)] == ["senpai"]


def test_models_match_migration_head(db):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from api.db import Base

    ctx = MigrationContext.configure(db.connection(), opts={"compare_type": True})
    assert compare_metadata(ctx, Base.metadata) == []
