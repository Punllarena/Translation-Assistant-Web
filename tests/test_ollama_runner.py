import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from api import jobs
from api.config import get_settings
from api.models import ApiCredential, Line, UserSetting
from api.models.ollama import OllamaChunk, OllamaQueueItem, OllamaSuggestion
from api.ollama import endpoint, runner
from api.ollama.prompt import steady_ctx
from api.security import encrypt_secret

SHOW = json.loads(Path("tests/fixtures/mt/ollama_show.json").read_text(encoding="utf-8"))


@pytest.fixture
def in_test_db(monkeypatch, db):
    """Both workers' sessions join the test transaction (their commits release savepoints)."""
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    monkeypatch.setattr(runner, "SessionLocal", session)
    monkeypatch.setattr(runner, "PAUSES", (0, 0, 0))
    monkeypatch.setattr(get_settings(), "mt_allow_private_urls", True)  # "ol" never resolves
    endpoint._INFO.clear()
    return db


def _asked(body):
    section = body["messages"][1]["content"].split("Translate:\n")[1]
    return [int(ln[1:ln.index("]")]) for ln in section.splitlines() if ln.startswith("[")]


def _ndjson(content):
    out = [{"message": {"content": content}}, {"done": True, "eval_count": 3}]
    return "\n".join(json.dumps(o) for o in out).encode()


def ollama(on_chat=None, calls=None):
    """A client factory answering /api/show and every /api/chat with T<n> per asked line."""
    def handle(request):
        if calls is not None:
            calls.append(request.url.path)
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW)
        body = json.loads(request.content)
        if on_chat:
            on_chat(body)
        ids = _asked(body)
        answer = json.dumps({"lines": [{"id": n, "text": f"T{n}"} for n in ids]})
        return httpx.Response(200, content=_ndjson(answer))
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle))


@pytest.fixture
def setup(in_test_db, make_user, make_doc):
    def _make(params=None):
        db = in_test_db
        u = make_user(email="run@example.com")
        db.add(ApiCredential(user_id=u.id, kind="ollama", name="",
                             secret_enc=encrypt_secret(""), endpoint_url="http://ol:11434"))
        for key, value in {"ollama_model": "m", "ollama_preset": "custom",
                           "ollama_chunk_lines": 2, "ollama_context_lines": 1}.items():
            db.add(UserSetting(user_id=u.id, key=key, value_json=value))
        doc = make_doc(u, ["a", "b", "c", "d"], translated=False)
        db.add(OllamaQueueItem(user_id=u.id, kind="documents", series_id=doc.series_id,
                               document_ids=[doc.id], position=0))
        job = jobs.enqueue(db, u.id, "ollama_run", params or {})
        db.flush()
        return u, doc, job
    return _make


def _suggested(db, doc):
    return dict(db.execute(
        select(Line.line_number, OllamaSuggestion.text)
        .join(OllamaSuggestion, OllamaSuggestion.line_id == Line.id)
        .where(Line.document_id == doc.id)
    ).all())


def test_general_worker_never_claims_ollama_run(setup, in_test_db):
    _, _, job = setup()
    assert jobs.run_next() is False
    in_test_db.refresh(job)
    assert job.state == "queued"


def test_claim_takes_the_queued_run(setup, in_test_db):
    _, _, job = setup()
    claimed = runner.claim(in_test_db)
    assert claimed.id == job.id and claimed.state == "running" and claimed.started_at
    assert runner.claim(in_test_db) is None


async def test_run_one_saves_chunks_and_finishes(setup, in_test_db):
    u, doc, job = setup()
    runner.claim(in_test_db)
    calls = []
    await runner.run_one(job.id, ollama(calls=calls))
    in_test_db.refresh(job)
    assert job.state == "done" and job.finished_at and job.progress == 4
    assert job.result_json == {"lines": 4, "failed": 0, "chunks": 2, "retries": 0,
                               "clamped": 0, "reason": "finished"}
    assert _suggested(in_test_db, doc) == {0: "T0", 1: "T1", 2: "T2", 3: "T3"}
    chunks = in_test_db.scalars(select(OllamaChunk).where(OllamaChunk.job_id == job.id)).all()
    assert len(chunks) == 2 and {c.source for c in chunks} == {"run"}
    assert calls.count("/api/show") == 1  # model info is cached per (url, model)
    # a documents item with nothing left to ask leaves the queue
    items = select(OllamaQueueItem).where(OllamaQueueItem.user_id == u.id)
    assert in_test_db.scalars(items).all() == []


async def test_run_stops_when_until_passed(setup, in_test_db):
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    _, doc, job = setup({"until": past})
    runner.claim(in_test_db)
    calls = []
    await runner.run_one(job.id, ollama(calls=calls))
    in_test_db.refresh(job)
    assert job.state == "done" and job.result_json["reason"] == "window closed"
    assert calls == [] and _suggested(in_test_db, doc) == {}


async def test_run_cancel_keeps_saved_chunks(setup, in_test_db):
    _, doc, job = setup()
    runner.claim(in_test_db)

    def cancel(_body):
        job.cancel_requested = True  # what POST /jobs/{id}/cancel does, from another session

    await runner.run_one(job.id, ollama(on_chat=cancel))
    in_test_db.refresh(job)
    assert job.state == "cancelled" and job.result_json["reason"] == "cancelled"
    assert job.result_json["lines"] == 2 and job.progress == 2
    assert _suggested(in_test_db, doc) == {0: "T0", 1: "T1"}


async def test_unreachable_server_fails_after_retries(setup, in_test_db):
    _, doc, job = setup()
    runner.claim(in_test_db)
    calls = []

    def down(request):
        calls.append(request.url.path)
        raise httpx.ConnectError("refused")

    await runner.run_one(job.id, lambda: httpx.AsyncClient(transport=httpx.MockTransport(down)))
    in_test_db.refresh(job)
    assert job.state == "failed" and "unreachable" in job.message
    assert job.result_json["reason"] == "server unreachable"
    assert job.result_json["retries"] == runner.RETRIES == 3
    assert len(calls) == 4 and _suggested(in_test_db, doc) == {}


async def test_a_line_that_keeps_failing_is_not_asked_again_in_the_same_run(setup, in_test_db):
    _, doc, job = setup()
    runner.claim(in_test_db)
    seen = []

    def handle(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW)
        ids = _asked(json.loads(request.content))
        seen.append(ids)
        lines = [{"id": n, "text": f"T{n}"} for n in ids if n != 1]  # line 1 never answered
        if len(ids) == 1 and ids[0] == 1:
            lines = [{"id": 1, "text": ""}]
        return httpx.Response(200, content=_ndjson(json.dumps({"lines": lines})))

    await runner.run_one(job.id, lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    in_test_db.refresh(job)
    assert job.state == "done" and job.result_json["failed"] >= 1
    assert 1 not in _suggested(in_test_db, doc) and 3 in _suggested(in_test_db, doc)
    assert len(seen) < 10


async def test_num_ctx_is_steady_for_the_preset(setup, in_test_db):
    u, _, job = setup()
    runner.claim(in_test_db)
    sent = []
    await runner.run_one(job.id, ollama(on_chat=lambda b: sent.append(b["options"]["num_ctx"])))
    ep, _ = endpoint.load(in_test_db, u.id)
    assert sent == [steady_ctx(ep.system_prompt, 2, 1)] * 2


async def test_whole_chapter_num_ctx_never_steps_down(setup, in_test_db, make_doc):
    u, doc, job = setup()
    setting = in_test_db.get(UserSetting, (u.id, "ollama_preset"))
    setting.value_json = "large"
    long = make_doc(u, [f"line {n} " + "x" * 80 for n in range(40)], order=-1,
                    translated=False)
    item = in_test_db.scalar(select(OllamaQueueItem).where(OllamaQueueItem.user_id == u.id))
    item.document_ids = [long.id, doc.id]  # the long chapter first, then the short one
    in_test_db.flush()
    runner.claim(in_test_db)
    sent = []
    await runner.run_one(job.id, ollama(on_chat=lambda b: sent.append(b["options"]["num_ctx"])))
    assert len(sent) == 2 and sent[0] > 2048 and sent[1] == sent[0]


async def test_lines_asked_but_not_answered_are_not_asked_again(setup, in_test_db, monkeypatch):
    """Not only failed lines: any asked line missing from the result is skipped for the run,
    so the same chunk can never be asked forever."""
    _, doc, job = setup()
    runner.claim(in_test_db)
    asked = []

    async def nothing(client, ep, before, chunk, **kw):
        asked.append([i.line_number for i in chunk if i.known is None])
        return runner.ChunkResult()  # neither answered nor failed

    monkeypatch.setattr(runner, "translate", nothing)
    await asyncio.wait_for(runner.run_one(job.id, ollama()), 60)  # it used to loop forever
    in_test_db.refresh(job)
    assert job.state == "done" and asked == [[0, 1], [2, 3]]
    assert _suggested(in_test_db, doc) == {}
