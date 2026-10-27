"""The admission gate and maintenance mode: no out-of-request writer starts during a restore."""

import asyncio
import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from api import jobs
from api.backup import state
from api.config import get_settings
from api.models import ApiCredential, Job, UserSetting
from api.models.ollama import OllamaQueueItem
from api.ollama import endpoint, runner, schedule
from api.routers import mt as mt_router
from api.routers import ollama_editor
from api.security import encrypt_secret

SHOW = json.loads(Path("tests/fixtures/mt/ollama_show.json").read_text(encoding="utf-8"))


@contextmanager
def _same_session(db):
    """Point a worker's own SessionLocal at the test transaction."""
    yield db


def test_gate_refuses_work_while_maintenance(db):
    assert state.try_begin(db) is None
    with pytest.raises(state.Maintenance):
        with state.work():
            pass


def test_try_begin_refuses_with_work_in_flight(db):
    with state.work():
        assert state.try_begin(db) == state.BUSY
    assert state.try_begin(db) is None


def test_try_begin_twice_refuses(db):
    assert state.try_begin(db) is None
    assert state.try_begin(db) == state.RESTORING


def test_try_begin_refuses_with_a_queued_job(db, make_user):
    user = make_user()
    jobs.enqueue(db, user.id, "tadb_import", {})
    assert state.try_begin(db) == state.BUSY
    assert state.snapshot().phase == "idle"


def test_maintenance_blocks_everything_but_status_and_health(app_client, db):
    state.try_begin(db)
    assert app_client.get("/series").status_code == 503
    assert app_client.get("/series").json() == {"detail": state.IN_PROGRESS}
    assert app_client.get("/healthz").status_code == 200


def test_worker_claims_nothing_while_restoring(db, make_user, monkeypatch):
    monkeypatch.setattr(jobs, "SessionLocal", lambda: _same_session(db))
    user = make_user()
    state.try_begin(db)
    job = jobs.enqueue(db, user.id, "echo", {})
    assert jobs.run_next() is False
    db.refresh(job)
    assert job.state == "queued"


def test_running_job_counts_as_work(db, make_user, monkeypatch):
    monkeypatch.setattr(jobs, "SessionLocal", lambda: _same_session(db))
    answers = []

    def probe(ctx):
        answers.append(state.try_begin(ctx.db))
        return {}

    monkeypatch.setitem(jobs.HANDLERS, "probe", probe)
    user = make_user()
    jobs.enqueue(db, user.id, "probe", {})
    assert jobs.run_next() is True
    assert answers == [state.BUSY]


async def test_runner_claims_nothing_while_restoring(db, make_user, monkeypatch):
    monkeypatch.setattr(runner, "SessionLocal", lambda: _same_session(db))
    user = make_user()
    state.try_begin(db)
    job = jobs.enqueue(db, user.id, runner.KIND, {})
    stop = asyncio.Event()
    task = asyncio.create_task(runner.runner(stop, idle=0.01))
    await asyncio.sleep(0.05)
    stop.set()
    await task
    db.refresh(job)
    assert job.state == "queued"


def test_tick_enqueues_nothing_while_restoring(db, make_user, make_doc, monkeypatch):
    monkeypatch.setattr(schedule, "SessionLocal", lambda: _same_session(db))
    user = make_user(email="sched@example.com")
    now = datetime.now(UTC)
    night = {
        "enabled": True,
        "days": list(range(7)),
        "tz": "UTC",
        "start": (now - timedelta(hours=1)).strftime("%H:%M"),
        "end": (now + timedelta(hours=1)).strftime("%H:%M"),
    }
    db.add(UserSetting(user_id=user.id, key=schedule.KEY, value_json=night))
    doc = make_doc(user, ["a"], translated=False)
    db.add(OllamaQueueItem(user_id=user.id, kind="documents", series_id=doc.series_id,
                           document_ids=[doc.id], position=0))
    db.flush()

    state.try_begin(db)
    schedule._tick_once()

    assert db.scalars(select(Job)).all() == []


def _ndjson(content):
    out = [{"message": {"content": content}}, {"done": True, "eval_count": 3}]
    return "\n".join(json.dumps(o) for o in out).encode()


def _asked(body):
    section = body["messages"][1]["content"].split("Translate:\n")[1]
    return [int(ln[1:ln.index("]")]) for ln in section.splitlines() if ln.startswith("[")]


def _set_up_ollama(db, user):
    db.add(ApiCredential(user_id=user.id, kind="ollama", name="",
                         secret_enc=encrypt_secret(""), endpoint_url="http://ol:11434"))
    for key, value in {"ollama_model": "m", "ollama_preset": "custom",
                       "ollama_chunk_lines": 2, "ollama_context_lines": 1}.items():
        db.add(UserSetting(user_id=user.id, key=key, value_json=value))
    db.flush()


@pytest.fixture
def ollama_wire(monkeypatch, db):
    """The editor's own sessions join the test transaction; Ollama answers through a handler."""
    monkeypatch.setattr(ollama_editor, "SessionLocal", lambda: _same_session(db))
    monkeypatch.setattr(ollama_editor, "_RUNNING", {})
    monkeypatch.setattr(get_settings(), "mt_allow_private_urls", True)  # "ol" never resolves
    endpoint._INFO.clear()

    def handle(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW)
        ids = _asked(json.loads(request.content))
        answer = json.dumps({"lines": [{"id": n, "text": f"T{n}"} for n in ids]})
        return httpx.Response(200, content=_ndjson(answer))

    monkeypatch.setattr(ollama_editor, "http_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))


def test_by_hand_chunk_counts_as_work(app_client, me, make_doc, db, ollama_wire, monkeypatch):
    _set_up_ollama(db, me)
    entered, release = threading.Event(), threading.Event()
    real_save = ollama_editor._save

    def blocking_save(prep, plan, result):
        entered.set()
        release.wait(10)
        return real_save(prep, plan, result)

    monkeypatch.setattr(ollama_editor, "_save", blocking_save)
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)
    answer = {}

    def ask():
        answer["r"] = app_client.get(f"/documents/{doc.id}/ollama/stream",
                                     params={"line_number": 0})

    thread = threading.Thread(target=ask)
    thread.start()
    try:
        assert entered.wait(10)
        assert state.try_begin(db) == state.BUSY
    finally:
        release.set()
        thread.join(10)

    assert answer["r"].status_code == 200
    assert state.try_begin(db) is None  # the gate opened again once the chunk saved


@contextmanager
def _joined_session(db):
    """The stream's cache session joins the test transaction (its commit is a flush)."""
    real = db.commit
    db.commit = db.flush
    try:
        yield db
    finally:
        db.commit = real


def test_mt_stream_counts_as_work(app_client, me, make_doc, db, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def handle(request):
        entered.set()
        release.wait(10)
        return httpx.Response(200, json={"translations": [{"text": "ok"}]})

    monkeypatch.setattr(mt_router, "http_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(mt_router, "SessionLocal", lambda: _joined_session(db))
    app_client.post("/credentials", json={"kind": "deepl", "secret": "abc:fx"})
    doc = make_doc(me, ["%一行目です。"], translated=False)
    answer = {}

    def translate():
        answer["r"] = app_client.get("/mt/stream", params={
            "backend": "deepl", "document_id": doc.id, "line_number": 0})

    thread = threading.Thread(target=translate)
    thread.start()
    try:
        assert entered.wait(10)
        assert state.try_begin(db) == state.BUSY
    finally:
        release.set()
        thread.join(10)

    assert answer["r"].status_code == 200
    assert state.try_begin(db) is None


def test_mt_stream_during_maintenance_writes_no_cache(me, make_doc, db, monkeypatch):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"translations": [{"text": "ok"}]})

    monkeypatch.setattr(mt_router, "http_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    from api.models import MtCache

    doc = make_doc(me, ["%一行目です。"], translated=False)
    job = mt_router._prepare(db, me.id, "deepl", doc.id, 0)
    state.try_begin(db)

    async def drain():
        return [event async for event in mt_router._events(job)]

    assert asyncio.run(drain()) == [("error", {"message": state.IN_PROGRESS})]
    assert calls == []
    assert db.query(MtCache).count() == 0
