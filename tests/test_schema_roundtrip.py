from sqlalchemy import inspect, text

from api.models import Document, Line, Profile, Series, User


def test_migration_created_every_table(db):
    names = set(inspect(db.get_bind()).get_table_names())
    assert {"users", "sessions", "invites", "profiles", "documents", "lines"} <= names


def test_insert_and_read_back_a_document_tree(db):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, name="default", is_default=True))
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


def test_custom_words_are_unique_case_insensitively_per_profile(db):
    import pytest
    from sqlalchemy.exc import IntegrityError

    from api.models import CustomWord

    user = User(email="c@example.com", password_hash="x")
    db.add(user)
    db.flush()
    p1 = Profile(user_id=user.id, name="p1")
    p2 = Profile(user_id=user.id, name="p2")
    db.add_all([p1, p2])
    db.flush()
    db.add_all([
        CustomWord(profile_id=p1.id, word="Apple"),
        CustomWord(profile_id=p2.id, word="apple"),
    ])
    db.flush()
    db.add(CustomWord(profile_id=p1.id, word="apple"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_models_match_migration_head(db):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from api.db import Base

    ctx = MigrationContext.configure(db.connection(), opts={"compare_type": True})
    assert compare_metadata(ctx, Base.metadata) == []
