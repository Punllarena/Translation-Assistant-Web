from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from api import jobs
from api.models import Line, UserSetting, Volume
from api.models.ollama import OllamaChunk, OllamaQueueItem, OllamaSuggestion
from api.ollama import runlog


@pytest.fixture
def ready(monkeypatch):
    """The user's Ollama endpoint counts as configured."""
    monkeypatch.setattr("api.ollama.endpoint.load", lambda db, user_id: (object(), None))


def _add(client, **body):
    return client.post("/ollama/queue", json=body)


def _chunk(db, user, doc, *, model="m", size=12, asked=2, total_ms=4000, ok=True, age=0):
    chunk = OllamaChunk(
        user_id=user.id, document_id=doc.id, series_id=doc.series_id, source="run", ok=ok,
        clamped=False, depth=0, model=model, preset="small", chunk_lines=size, context_lines=0,
        first_line=0, last_line=1, asked=asked, prompt_tokens=1, output_tokens=1,
        total_ms=total_ms, reasoning="why", prompt="p",
        created_at=datetime.now(UTC) - timedelta(days=age),
    )
    db.add(chunk)
    db.flush()
    return chunk


def test_queue_lists_labels_and_lines_left(app_client, db, me, make_series, make_doc):
    s = make_series(me, "Novel")
    vol = Volume(series_id=s.id, kind="Volume", volume_index=Decimal(2), subtitle="")
    db.add(vol)
    db.flush()
    doc = make_doc(me, ["a", "", "c"], series=s, volume=vol, translated=False, title="One")
    assert _add(app_client, kind="series", series_id=s.id).status_code == 201
    assert _add(app_client, kind="volume", series_id=s.id, volume_id=vol.id).status_code == 201
    body = dict(kind="documents", series_id=s.id, document_ids=[doc.id])
    assert _add(app_client, **body).status_code == 201
    rows = app_client.get("/ollama/queue").json()
    assert [r["kind"] for r in rows] == ["series", "volume", "documents"]
    assert rows[0]["label"] == "Novel" and rows[0]["series_title"] == "Novel"
    assert rows[1]["volume_label"] == vol.label and rows[1]["label"] == vol.label
    assert rows[2]["label"] == "One" and rows[2]["document_ids"] == [doc.id]
    assert [r["lines_left"] for r in rows] == [2, 2, 2]
    assert all(r["estimate_seconds"] is None for r in rows)


def test_queue_estimate_uses_recent_ok_chunks_of_this_model_and_size(
    app_client, db, me, make_series, make_doc
):
    s = make_series(me)
    doc = make_doc(me, ["a", "b", "c"], series=s, translated=False)
    db.add(UserSetting(user_id=me.id, key="ollama_model", value_json="m"))
    _chunk(db, me, doc)  # 2000 ms per line
    _chunk(db, me, doc, model="other", total_ms=40000)
    _chunk(db, me, doc, size=25, total_ms=40000)
    _chunk(db, me, doc, ok=False, total_ms=40000)
    _chunk(db, me, doc, age=31, total_ms=40000)
    _add(app_client, kind="series", series_id=s.id)
    assert app_client.get("/ollama/queue").json()[0]["estimate_seconds"] == 6


def test_queue_add_foreign_targets_404(app_client, me, make_user, make_series, make_doc):
    other = make_user(email="other@example.com")
    theirs = make_series(other, "Theirs")
    their_doc = make_doc(other, ["a"], series=theirs)
    mine = make_series(me)
    assert _add(app_client, kind="series", series_id=theirs.id).status_code == 404
    assert _add(app_client, kind="volume", series_id=mine.id, volume_id=99999).status_code == 404
    body = dict(kind="documents", series_id=mine.id, document_ids=[their_doc.id])
    assert _add(app_client, **body).status_code == 404


def test_queue_is_capped_at_100(app_client, db, me, make_series):
    s = make_series(me)
    db.add_all(
        OllamaQueueItem(user_id=me.id, kind="series", series_id=s.id, document_ids=[], position=i)
        for i in range(100)
    )
    db.flush()
    r = _add(app_client, kind="series", series_id=make_series(me, "Other").id)
    assert (r.status_code, r.json()["detail"]) == (409, "The queue holds at most 100 items.")


def test_queue_duplicate_returns_existing(app_client, me, make_series, make_doc):
    s = make_series(me)
    a, b = make_doc(me, ["x"], series=s), make_doc(me, ["y"], series=s)
    first = _add(app_client, kind="documents", series_id=s.id, document_ids=[a.id, b.id])
    again = _add(app_client, kind="documents", series_id=s.id, document_ids=[b.id, a.id])
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    assert len(app_client.get("/ollama/queue").json()) == 1


def test_queue_order(app_client, me, make_series):
    ids = [
        _add(app_client, kind="series", series_id=make_series(me, f"S{i}").id).json()["id"]
        for i in range(3)
    ]
    r = app_client.put("/ollama/queue/order", json={"ids": ids[::-1]})
    assert r.status_code == 200 and [x["id"] for x in r.json()] == ids[::-1]
    assert [x["id"] for x in app_client.get("/ollama/queue").json()] == ids[::-1]
    for bad in (ids[:2], ids + [99999], [ids[0], ids[0], ids[1]]):
        assert app_client.put("/ollama/queue/order", json={"ids": bad}).status_code == 422


def test_queue_order_racing_the_runner_is_409(app_client, db, me, make_series, monkeypatch):
    from sqlalchemy import delete

    from api.routers import ollama as router

    ids = [
        _add(app_client, kind="series", series_id=make_series(me, f"S{i}").id).json()["id"]
        for i in range(2)
    ]
    real = router._items

    def items_then_gone(db, user_id):
        loaded = real(db, user_id)
        # the runner deletes a finished item between the read and the write
        db.execute(delete(OllamaQueueItem).where(OllamaQueueItem.id == ids[0]),
                   execution_options={"synchronize_session": False})
        return loaded

    monkeypatch.setattr(router, "_items", items_then_gone)
    r = app_client.put("/ollama/queue/order", json={"ids": ids[::-1]})
    assert r.status_code == 409


def test_queue_delete(app_client, me, make_user, make_series, db):
    mine = _add(app_client, kind="series", series_id=make_series(me).id).json()["id"]
    other = make_user(email="other@example.com")
    theirs = OllamaQueueItem(
        user_id=other.id, kind="series", series_id=make_series(other).id, document_ids=[],
        position=0,
    )
    db.add(theirs)
    db.flush()
    assert app_client.delete(f"/ollama/queue/{theirs.id}").status_code == 404
    assert app_client.delete(f"/ollama/queue/{mine}").status_code == 204
    assert app_client.delete(f"/ollama/queue/{mine}").status_code == 404
    assert app_client.get("/ollama/queue").json() == []


def test_run_enqueues_a_job_once(app_client, me, make_series, ready):
    _add(app_client, kind="series", series_id=make_series(me).id)
    r = app_client.post("/ollama/run")
    assert r.status_code == 201
    assert (r.json()["kind"], r.json()["state"], r.json()["params"]) == (
        "ollama_run", "queued", {}
    )
    again = app_client.post("/ollama/run")
    assert (again.status_code, again.json()["detail"]) == (
        409, "An Ollama run is already active."
    )
    # The savepoint kept the request session usable.
    assert app_client.get("/ollama/queue").status_code == 200


def test_run_refuses_an_empty_queue(app_client, me, ready):
    r = app_client.post("/ollama/run")
    assert (r.status_code, r.json()["detail"]) == (409, "The queue is empty.")


def test_run_reports_the_setup_message(app_client, me, make_series, monkeypatch):
    monkeypatch.setattr("api.ollama.endpoint.load", lambda db, user_id: (None, "Set it up."))
    _add(app_client, kind="series", series_id=make_series(me).id)
    r = app_client.post("/ollama/run")
    assert (r.status_code, r.json()["detail"]) == (409, "Set it up.")


def test_flush_clears_held_suggestions(app_client, db, me, make_series, make_doc):
    s = make_series(me)
    a, b = make_doc(me, ["x"], series=s, translated=False), make_doc(
        me, ["y"], series=s, translated=False
    )
    for doc in (a, b):
        chunk = _chunk(db, me, doc)
        line = db.scalar(select(Line).where(Line.document_id == doc.id))
        db.add(OllamaSuggestion(line_id=line.id, chunk_id=chunk.id, text="sug", raw_sha="s"))
    db.flush()

    def held():
        db.expire_all()
        return db.scalars(select(OllamaSuggestion.text)).all()

    assert app_client.post("/ollama/flush", json={"document_ids": [a.id]}).json() == {"cleared": 1}
    assert sorted(t for t in held() if t) == ["sug"]
    assert app_client.post("/ollama/flush", json={}).json() == {"cleared": 1}
    assert held() == [None, None]


def test_flush_404s_for_another_users_scope(app_client, db, me, make_user, make_series,
                                            make_doc):
    other = make_user(email="other-flush@example.com")
    s = make_series(other)
    vol = Volume(series_id=s.id, subtitle="V", volume_order=1)
    db.add(vol)
    db.flush()
    doc = make_doc(other, ["x"], series=s, translated=False)
    for body in ({"series_id": s.id}, {"volume_id": vol.id}, {"document_ids": [doc.id]},
                 {"series_id": 999999}, {"volume_id": 999999}, {"document_ids": [999999]}):
        assert app_client.post("/ollama/flush", json=body).status_code == 404, body


def test_saving_a_line_scores_its_suggestion(app_client, db, me, make_doc):
    doc = make_doc(me, ["x", "y"], translated=False)
    chunk = _chunk(db, me, doc)
    line = db.scalar(select(Line).where(Line.document_id == doc.id, Line.line_number == 0))
    db.add(OllamaSuggestion(line_id=line.id, chunk_id=chunk.id, text="Hello", raw_sha="s"))
    db.flush()
    body = {"lines": [{"line_number": 0, "translated_text": "Hello"}]}
    assert app_client.patch(f"/documents/{doc.id}/lines", json=body).status_code == 200
    db.expire_all()
    assert db.get(OllamaChunk, chunk.id).used_count == 1
    assert db.scalar(select(OllamaSuggestion.scored)) is True



def test_id_lists_are_capped(app_client, me):
    ids = list(range(1, 1002))
    assert app_client.put("/ollama/queue/order", json={"ids": ids}).status_code == 422
    assert app_client.post("/ollama/flush", json={"document_ids": ids}).status_code == 422


def test_run_log_route(app_client, db, me, make_user):
    runlog.clear()
    job = jobs.enqueue(db, me.id, "ollama_run", {})
    other = jobs.enqueue(db, make_user(email="other@example.com").id, "ollama_run", {})
    fetch = jobs.enqueue(db, me.id, "syosetu_fetch", {})
    db.flush()
    r = app_client.get(f"/ollama/runs/{job.id}/log").json()
    assert r == {"kept": False, "entries": [], "now": None, "ended": True, "next": 0}
    runlog.add(job.id, "Run started")
    runlog.add(job.id, "Got 2 of 2 lines", "warn")
    runlog.doing(job.id, "Thinking… 10 characters so far")
    r = app_client.get(f"/ollama/runs/{job.id}/log", params={"after": 1}).json()
    assert [(e["text"], e["level"]) for e in r["entries"]] == [("Got 2 of 2 lines", "warn")]
    assert r["now"] == "Thinking… 10 characters so far" and r["next"] == 2 and not r["ended"]
    assert app_client.get(f"/ollama/runs/{other.id}/log").status_code == 404
    assert app_client.get(f"/ollama/runs/{fetch.id}/log").status_code == 404
