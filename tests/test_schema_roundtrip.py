from sqlalchemy import inspect, text

from api.models import Document, Line, Profile, User


def test_migration_created_every_table(db):
    names = set(inspect(db.get_bind()).get_table_names())
    assert {"users", "sessions", "invites", "profiles", "documents", "lines"} <= names


def test_insert_and_read_back_a_document_tree(db):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, name="default", is_default=True))
    doc = Document(user_id=user.id, title="Chapter 1")
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
    doc = Document(user_id=user.id, title="Chapter 2")
    db.add(doc)
    db.flush()
    db.add(Line(document_id=doc.id, line_number=0, prefix="%", raw_text="x"))
    db.flush()
    db.execute(text("DELETE FROM documents WHERE id = :i"), {"i": doc.id})
    assert db.query(Line).filter_by(document_id=doc.id).count() == 0
