from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from api import jobs
from api.models import Line
from api.models.ollama import OllamaChunk, OllamaSuggestion
from api.ollama import store

NOW = datetime(2026, 10, 26, tzinfo=UTC)


def _chunk(db, user, doc):
    chunk = OllamaChunk(
        user_id=user.id, document_id=doc.id, series_id=doc.series_id, source="run", ok=True,
        clamped=False, depth=0, model="m", preset="custom", chunk_lines=1, context_lines=0,
        first_line=0, last_line=0, asked=1, prompt_tokens=7, output_tokens=3,
        reasoning="why", prompt="p")
    db.add(chunk)
    db.flush()
    return chunk


def _suggest(db, user, doc, text="sug"):
    chunk = _chunk(db, user, doc)
    for ln in db.scalars(select(Line).where(Line.document_id == doc.id)):
        db.add(OllamaSuggestion(line_id=ln.id, chunk_id=chunk.id, text=text, raw_sha="s"))
    db.flush()
    return chunk


def _age(db, doc, when):
    for ln in db.scalars(select(Line).where(Line.document_id == doc.id)):
        ln.translated_at = when
    db.flush()


def _texts(db, doc):
    return db.scalars(
        select(OllamaSuggestion.text).join(Line, Line.id == OllamaSuggestion.line_id)
        .where(Line.document_id == doc.id)).all()


@pytest.fixture
def u(make_user):
    return make_user(email="store@example.com")


def test_cleanup_waits_three_months(db, u, make_doc):
    old, recent = make_doc(u, ["a", "b"]), make_doc(u, ["c"])
    _suggest(db, u, old)
    _suggest(db, u, recent)
    _age(db, old, NOW - timedelta(days=92))
    _age(db, recent, NOW - timedelta(days=30))
    assert store.cleanup(db, u.id, NOW) == 1
    assert _texts(db, old) == [None, None] and _texts(db, recent) == ["sug"]


def test_cleanup_skips_incomplete_chapters(db, u, make_doc):
    doc = make_doc(u, ["a", "b"])
    _suggest(db, u, doc)
    _age(db, doc, NOW - timedelta(days=200))
    db.scalars(select(Line).where(Line.document_id == doc.id)).first().translated_text = ""
    db.flush()
    assert store.cleanup(db, u.id, NOW) == 0
    assert _texts(db, doc) == ["sug", "sug"]


def test_flush_scopes(db, u, make_user, make_doc):
    other = make_user(email="other@example.com")
    a, b, c = make_doc(u, ["a"]), make_doc(u, ["b"]), make_doc(other, ["c"])
    for d, user in ((a, u), (b, u), (c, other)):
        _suggest(db, user, d)
    assert store.flush(db, u.id, document_ids=[a.id]) == 1
    assert _texts(db, a) == [None] and _texts(db, b) == ["sug"]
    assert store.flush(db, u.id) == 1  # everything left of mine
    assert _texts(db, c) == ["sug"]  # never another user's
    assert store.flush(db, u.id, series_id=a.series_id) == 0


def test_flush_keeps_chunk_stats(db, u, make_doc):
    doc = make_doc(u, ["a"])
    chunk = _suggest(db, u, doc)
    chunk.used_count = 4
    db.flush()
    store.flush(db, u.id, document_ids=[doc.id])
    db.refresh(chunk)
    assert chunk.reasoning is None and chunk.prompt is None
    assert chunk.used_count == 4 and chunk.prompt_tokens == 7


def test_record_outcomes_counts_once(db, u, make_doc):
    doc = make_doc(u, ["a", "b", "c"], translated=False)
    chunk = _suggest(db, u, doc, text="hello there")
    store.record_outcomes(db, doc.id, {0: "hello there", 1: "completely different words", 2: ""})
    store.record_outcomes(db, doc.id, {0: "hello there"})
    db.refresh(chunk)
    assert (chunk.used_count, chunk.edited_count, chunk.ignored_count) == (1, 0, 1)
    scored = db.scalars(select(OllamaSuggestion.scored).order_by(OllamaSuggestion.id)).all()
    assert scored == [True, True, False]


def test_cleanup_handler(db, u, make_doc):
    doc = make_doc(u, ["a"])
    _suggest(db, u, doc)
    _age(db, doc, datetime.now(UTC) - timedelta(days=100))
    job = jobs.enqueue(db, u.id, "ollama_cleanup", {})
    assert jobs.HANDLERS["ollama_cleanup"](jobs.JobContext(db, job)) == {"chapters": 1}
