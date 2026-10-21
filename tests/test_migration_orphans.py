"""The data step of 5a1e0c2d7b94 (documents.series_id NOT NULL), run inside the test
transaction against a re-loosened column; the db fixture rolls everything back."""

import importlib.util
from pathlib import Path

from sqlalchemy import func, select, text

from api.models import Document, Series, Volume

_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations" / "versions" / "5a1e0c2d7b94_documents_series_required.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location("mig_5a1e0c2d7b94", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_each_orphan_gets_its_own_series_with_a_free_title(db, make_user, make_series):
    a = make_user(email="a@example.com")
    b = make_user(email="b@example.com")
    story = make_series(a, "Story")
    vol = Volume(series_id=story.id, subtitle="V", volume_order=1)
    db.add(vol)
    db.flush()
    db.execute(text("ALTER TABLE documents ALTER COLUMN series_id DROP NOT NULL"))
    orphans = [
        Document(user_id=a.id, title="Story", series_id=None, series_order=7, volume_id=vol.id),
        Document(user_id=a.id, title="Story", series_id=None, series_order=4),
        Document(user_id=b.id, title="Story", series_id=None, series_order=9),
    ]
    db.add_all(orphans)
    db.flush()

    _migration()._give_orphans_a_series(db.connection())
    db.expire_all()

    def placed(doc):
        doc = db.get(Document, doc.id)
        series = db.get(Series, doc.series_id)
        return series.user_id, series.title, doc.series_order, doc.volume_id

    assert [placed(d) for d in orphans] == [
        (a.id, "Story (2)", 1, None),
        (a.id, "Story (3)", 1, None),
        (b.id, "Story", 1, None),
    ]
    orphans_left = select(func.count()).select_from(Document).where(Document.series_id.is_(None))
    assert db.scalar(orphans_left) == 0
