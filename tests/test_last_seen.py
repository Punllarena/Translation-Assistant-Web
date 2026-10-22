from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from api.models import Session as SessionRow


def _last_seen(db):
    db.expire_all()
    return db.scalar(select(SessionRow)).last_seen_at


def test_last_seen_is_not_rewritten_on_every_request(app_client, db, me):
    app_client.get("/words")
    first = _last_seen(db)
    assert first is not None
    app_client.get("/words")
    assert _last_seen(db) == first


def test_stale_last_seen_is_refreshed(app_client, db, me):
    row = db.scalar(select(SessionRow))
    old = datetime.now(UTC) - timedelta(minutes=2)
    row.last_seen_at = old
    db.flush()
    app_client.get("/words")
    assert _last_seen(db) > old + timedelta(minutes=1)
