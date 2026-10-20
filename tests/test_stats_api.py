from datetime import UTC, datetime, timedelta

from api.models import Line


def stamp(db, doc, when, text=None):
    for line in db.query(Line).filter_by(document_id=doc.id):
        line.translated_at = when
        if text is not None:
            line.translated_text = text
    db.flush()


def test_days_bucket_in_the_viewers_zone(app_client, me, make_doc, db):
    doc = make_doc(me, ["一"])
    stamp(db, doc, datetime(2026, 1, 1, 23, 30, tzinfo=UTC))
    utc = app_client.get("/stats", params={"tz": "UTC"}).json()
    tokyo = app_client.get("/stats", params={"tz": "Asia/Tokyo"}).json()
    assert [d["date"] for d in utc["daily"]] == ["2026-01-01"]
    assert [d["date"] for d in tokyo["daily"]] == ["2026-01-02"]


def test_metrics_follow_the_desktop_sql(app_client, me, make_doc, db):
    doc = make_doc(me, ["一二三", "四五"])
    stamp(db, doc, datetime(2026, 1, 1, tzinfo=UTC), text="  two words  ")
    day = app_client.get("/stats").json()["daily"][0]
    assert day == {"date": "2026-01-01", "paragraphs": 2, "chars": 5, "en_words": 4}


def test_untranslated_and_other_users_lines_are_not_counted(
    app_client, me, make_doc, make_user, db,
):
    make_doc(me, ["一"])  # translated_at NULL
    theirs = make_doc(make_user(email="o@example.com"), ["一"])
    stamp(db, theirs, datetime(2026, 1, 1, tzinfo=UTC))
    body = app_client.get("/stats").json()
    assert body["daily"] == [] and body["series"] == []
    assert body["streaks"]["current_streak"] == 0


def test_today_streaks_summary_and_comparisons(app_client, me, make_doc, db):
    now = datetime.now(UTC)
    stamp(db, make_doc(me, ["一", "二"]), now)
    stamp(db, make_doc(me, ["三"]), now - timedelta(days=1))
    body = app_client.get("/stats").json()
    assert body["today"] == now.date().isoformat()
    assert body["streaks"]["current_streak"] == 2
    assert body["summary"]["today"]["paragraphs"] == 2
    assert body["summary"]["week"]["paragraphs"] == 3
    assert body["comparisons"]["paragraphs"]["periods"]["today"]["pct_change"] == 100.0
    assert set(body["comparisons"]) == {"paragraphs", "chars", "en_words"}


def test_series_breakdown_counts_a_series_chapters(app_client, me, make_doc, make_series, db):
    s = make_series(me, "Sword")
    stamp(db, make_doc(me, ["一", "二"], series=s, order=1), datetime(2026, 1, 1, tzinfo=UTC))
    stamp(db, make_doc(me, ["三"], series=s, order=2), datetime(2026, 1, 2, tzinfo=UTC))
    assert app_client.get("/stats").json()["series"] == [{
        "series_id": s.id, "series": "Sword", "paragraphs": 3, "chars": 3,
        "en_words": 3, "chapters": 2}]


def test_bad_zone_is_422(app_client, me):
    assert app_client.get("/stats", params={"tz": "Mars/Base"}).status_code == 422
