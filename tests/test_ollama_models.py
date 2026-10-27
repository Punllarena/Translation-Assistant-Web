import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from api.models import Job, Line
from api.models.ollama import OllamaChunk, OllamaSuggestion


def test_one_active_ollama_run_per_user(db, make_user):
    u = make_user()
    db.add(Job(user_id=u.id, kind="ollama_run", params_json={}))
    db.flush()
    db.add(Job(user_id=u.id, kind="ollama_run", params_json={}))
    with pytest.raises(IntegrityError):
        db.flush()


def test_finished_ollama_run_does_not_block_a_new_one(db, make_user):
    u = make_user()
    db.add(Job(user_id=u.id, kind="ollama_run", params_json={}, state="done"))
    db.add(Job(user_id=u.id, kind="ollama_run", params_json={}))
    db.flush()


def _chunk(db, user, doc):
    chunk = OllamaChunk(
        user_id=user.id, document_id=doc.id, series_id=doc.series_id, source="run", ok=True,
        clamped=False, depth=0, model="m", preset="balanced", chunk_lines=2, context_lines=0,
        first_line=0, last_line=1, asked=2, prompt_tokens=1, output_tokens=1,
    )
    db.add(chunk)
    db.flush()
    return chunk


def test_one_suggestion_per_line(db, make_user, make_doc):
    u = make_user()
    doc = make_doc(u, ["a", "b"])
    line = db.scalar(select(Line).where(Line.document_id == doc.id))
    chunk = _chunk(db, u, doc)
    db.add(OllamaSuggestion(line_id=line.id, chunk_id=chunk.id, text="x", raw_sha="0" * 64))
    db.flush()
    db.add(OllamaSuggestion(line_id=line.id, chunk_id=chunk.id, text="y", raw_sha="0" * 64))
    with pytest.raises(IntegrityError):
        db.flush()


def test_suggestions_cascade_with_document(db, make_user, make_doc):
    u = make_user()
    doc = make_doc(u, ["a", "b"])
    lines = db.scalars(select(Line).where(Line.document_id == doc.id)).all()
    chunk = _chunk(db, u, doc)
    db.add_all(
        OllamaSuggestion(line_id=ln.id, chunk_id=chunk.id, text="x", raw_sha="0" * 64)
        for ln in lines
    )
    db.flush()
    assert db.scalar(select(OllamaSuggestion.id).limit(1)) is not None
    db.delete(doc)
    db.flush()
    assert db.scalars(select(OllamaSuggestion)).all() == []
    # The chunk row outlives its document (SET NULL) so statistics keep it.
    db.refresh(chunk)
    assert chunk.document_id is None
