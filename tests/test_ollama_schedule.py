from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from api import jobs
from api.models import Job, Line, UserSetting
from api.models.ollama import OllamaChunk, OllamaQueueItem, OllamaSuggestion
from api.ollama import schedule

LONDON = ZoneInfo("Europe/London")
NIGHT = {"enabled": True, "start": "23:00", "end": "06:00", "days": [0, 1, 2, 3, 4, 5, 6],
         "tz": "Europe/London"}


def test_parse_rejects_bad_values():
    assert schedule.parse(None) is None
    assert schedule.parse({**NIGHT, "tz": "Nowhere/Land"}) is None
    assert schedule.parse({**NIGHT, "start": "25:00"}) is None
    s = schedule.parse(NIGHT)
    assert s and s.start == time(23, 0) and s.end == time(6, 0) and 6 in s.days


def test_window_across_midnight_and_dst():
    s = schedule.parse(NIGHT)
    at = datetime(2026, 10, 24, 23, 30, tzinfo=LONDON)  # BST, Saturday
    key, end = schedule.window_at(s, at.astimezone(UTC))
    assert key == "2026-10-24T23:00:00"
    assert end == datetime(2026, 10, 25, 6, 0, tzinfo=UTC)  # 06:00 GMT after the clocks go back
    again = datetime(2026, 10, 25, 5, 59, tzinfo=UTC)
    assert schedule.window_at(s, again)[0] == key
    assert schedule.window_at(s, datetime(2026, 10, 25, 6, 0, tzinfo=UTC)) is None


def test_closed_day_has_no_window():
    s = schedule.parse({**NIGHT, "days": [0]})  # Mondays only
    sat = datetime(2026, 10, 24, 23, 30, tzinfo=LONDON).astimezone(UTC)
    assert schedule.window_at(s, sat) is None
    # 02:00 Monday belongs to the window that started on Sunday, which is closed
    mon = datetime(2026, 10, 26, 2, 0, tzinfo=LONDON).astimezone(UTC)
    assert schedule.window_at(s, mon) is None
    mon_night = datetime(2026, 10, 26, 23, 30, tzinfo=LONDON).astimezone(UTC)
    assert schedule.window_at(s, mon_night) is not None


@pytest.fixture
def user(db, make_user, make_doc):
    u = make_user(email="sched@example.com")
    db.add(UserSetting(user_id=u.id, key=schedule.KEY, value_json=NIGHT))
    doc = make_doc(u, ["a"], translated=False)
    db.add(OllamaQueueItem(user_id=u.id, kind="documents", series_id=doc.series_id,
                           document_ids=[doc.id], position=0))
    db.flush()
    return u


NOW = datetime(2026, 10, 24, 23, 30, tzinfo=LONDON).astimezone(UTC)


def _runs(db, user):
    return db.scalars(select(Job).where(Job.user_id == user.id, Job.kind == "ollama_run")).all()


def test_tick_starts_one_run_per_window(db, user):
    schedule.tick(db, NOW)
    schedule.tick(db, NOW)
    (job,) = _runs(db, user)
    assert job.params_json == {"window": "2026-10-24T23:00:00",
                               "until": "2026-10-25T06:00:00+00:00"}
    job.state = "done"
    db.flush()
    schedule.tick(db, NOW)
    assert len(_runs(db, user)) == 1


def test_tick_restarts_a_window_run_a_restart_interrupted(db, user):
    schedule.tick(db, NOW)
    (job,) = _runs(db, user)
    job.state, job.message = "failed", jobs.INTERRUPTED
    db.flush()
    schedule.tick(db, NOW)
    runs = _runs(db, user)
    assert len(runs) == 2
    assert runs[-1].state == "queued"
    assert runs[-1].params_json["window"] == "2026-10-24T23:00:00"
    # a run that failed for another reason ends the window
    runs[-1].state, runs[-1].message = "failed", "Ollama is not set up"
    db.flush()
    schedule.tick(db, NOW)
    assert len(_runs(db, user)) == 2


def test_tick_skips_empty_queue(db, user):
    for item in db.scalars(select(OllamaQueueItem)):
        db.delete(item)
    db.flush()
    schedule.tick(db, NOW)
    assert _runs(db, user) == []


def test_tick_skips_closed_window_and_disabled(db, user):
    schedule.tick(db, datetime(2026, 10, 24, 12, 0, tzinfo=UTC))
    assert _runs(db, user) == []
    setting = db.get(UserSetting, (user.id, schedule.KEY))
    setting.value_json = {**NIGHT, "enabled": False}
    db.flush()
    schedule.tick(db, NOW)
    assert _runs(db, user) == []


def test_tick_survives_an_active_run(db, user):
    jobs.enqueue(db, user.id, "ollama_run", {})  # e.g. a manual run
    schedule.tick(db, NOW)
    assert len(_runs(db, user)) == 1
    assert db.is_active  # the session was not poisoned


def test_tick_enqueues_cleanup_once_per_utc_day(db, user, make_doc):
    doc = make_doc(user, ["z"])
    chunk = OllamaChunk(
        user_id=user.id, document_id=doc.id, source="run", ok=True, clamped=False, depth=0,
        model="m", preset="custom", chunk_lines=1, context_lines=0, first_line=0, last_line=0,
        asked=1, prompt_tokens=1, output_tokens=1)
    db.add(chunk)
    db.flush()
    line = db.scalar(select(Line).where(Line.document_id == doc.id))
    db.add(OllamaSuggestion(line_id=line.id, chunk_id=chunk.id, text="x", raw_sha="s"))
    db.flush()
    day = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)  # outside the window

    def cleanups():
        kinds = [j.kind for j in db.scalars(select(Job).where(Job.user_id == user.id))]
        return kinds.count("ollama_cleanup")

    line.translated_at = day - timedelta(days=10)
    db.flush()
    schedule.tick(db, day)
    assert cleanups() == 0  # held, but nothing is past retention: no empty job in History
    line.translated_at = day - timedelta(days=100)
    db.flush()
    schedule.tick(db, day)
    schedule.tick(db, day)
    assert cleanups() == 1
