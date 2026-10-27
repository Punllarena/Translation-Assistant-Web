import asyncio
import json
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from api.config import get_settings
from api.models import ApiCredential, Line, UserSetting
from api.models.ollama import OllamaChunk, OllamaSuggestion
from api.ollama import endpoint
from api.ollama.lane import LANES
from api.ollama.prompt import steady_ctx
from api.routers import ollama_editor
from api.security import encrypt_secret

SHOW = json.loads(Path("tests/fixtures/mt/ollama_show.json").read_text(encoding="utf-8"))


def events(body: str):
    out = []
    for frame in body.strip().split("\n\n"):
        kind, data = frame.split("\n", 1)
        out.append((kind.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def _asked(body):
    section = body["messages"][1]["content"].split("Translate:\n")[1]
    return [int(ln[1:ln.index("]")]) for ln in section.splitlines() if ln.startswith("[")]


def _ndjson(content, thinking=None):
    out = [{"message": {"thinking": thinking}}] if thinking else []
    out += [{"message": {"content": content}}, {"done": True, "eval_count": 3}]
    return "\n".join(json.dumps(o) for o in out).encode()


@pytest.fixture
def wire(monkeypatch, db):
    """The router's own sessions join the test transaction; Ollama answers through a handler."""
    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(ollama_editor, "SessionLocal", session)
    monkeypatch.setattr(ollama_editor, "_RUNNING", {})
    monkeypatch.setattr(get_settings(), "mt_allow_private_urls", True)  # "ol" never resolves
    endpoint._INFO.clear()
    calls = []

    def install(prefix="T", thinking=None):
        def handle(request):
            calls.append(request.url.path)
            if request.url.path == "/api/show":
                return httpx.Response(200, json=SHOW)
            ids = _asked(json.loads(request.content))
            answer = json.dumps({"lines": [{"id": n, "text": f"{prefix}{n}"} for n in ids]})
            return httpx.Response(200, content=_ndjson(answer, thinking))
        monkeypatch.setattr(ollama_editor, "http_client",
                            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))

    install()
    return install, calls


def _set_up(db, user):
    db.add(ApiCredential(user_id=user.id, kind="ollama", name="",
                         secret_enc=encrypt_secret(""), endpoint_url="http://ol:11434"))
    for key, value in {"ollama_model": "m", "ollama_preset": "custom",
                       "ollama_chunk_lines": 2, "ollama_context_lines": 1}.items():
        db.add(UserSetting(user_id=user.id, key=key, value_json=value))
    db.flush()


def _suggested(db, doc):
    return dict(db.execute(
        select(Line.line_number, OllamaSuggestion.text)
        .join(OllamaSuggestion, OllamaSuggestion.line_id == Line.id)
        .where(Line.document_id == doc.id)
    ).all())


def _stream(client, doc, n, reroll=False):
    return client.get(f"/documents/{doc.id}/ollama/stream",
                      params={"line_number": n, "reroll": str(reroll).lower()})


def _chunk(db, user, doc, **extra):
    chunk = OllamaChunk(
        user_id=user.id, series_id=doc.series_id, document_id=doc.id, source="run", ok=True,
        clamped=False, depth=0, model="qwen3:14b", preset="small", chunk_lines=12,
        context_lines=5, first_line=0, last_line=1, asked=2, prompt_tokens=10,
        output_tokens=5, total_ms=900, reasoning="why", prompt="[]", **extra,
    )
    db.add(chunk)
    db.flush()
    return chunk


def test_suggestions_list_marks_stale(app_client, me, make_user, make_doc, db):
    doc = make_doc(me, ["a", "b", "c"], translated=False)
    chunk = _chunk(db, me, doc)
    q = select(Line).where(Line.document_id == doc.id)
    lines = {ln.line_number: ln for ln in db.scalars(q)}
    from api.ollama.work import raw_sha
    db.add_all([
        OllamaSuggestion(line_id=lines[0].id, chunk_id=chunk.id, text="A",
                         raw_sha=raw_sha(lines[0].raw_text)),
        OllamaSuggestion(line_id=lines[1].id, chunk_id=chunk.id, text="B",
                         raw_sha=raw_sha(lines[1].raw_text)),
        OllamaSuggestion(line_id=lines[2].id, chunk_id=chunk.id, text=None,  # flushed
                         raw_sha=raw_sha(lines[2].raw_text)),
    ])
    lines[1].raw_text = "%changed"
    db.flush()
    body = app_client.get(f"/documents/{doc.id}/ollama").json()
    assert [(s["line_number"], s["text"], s["stale"]) for s in body] == [
        (0, "A", False), (1, "B", True)]
    first = body[0]
    assert first["chunk_id"] == chunk.id and first["model"] == "qwen3:14b"
    assert (first["first_line"], first["last_line"]) == (0, 1) and first["created_at"]
    other = make_user(email="o@example.com")
    foreign = make_doc(other, ["x"])
    assert app_client.get(f"/documents/{foreign.id}/ollama").status_code == 404


def test_chunk_detail_scoped(app_client, me, make_user, make_doc, db):
    doc = make_doc(me, ["a", "b"], translated=False)
    chunk = _chunk(db, me, doc)
    body = app_client.get(f"/ollama/chunks/{chunk.id}").json()
    assert body["reasoning"] == "why" and body["prompt"] == "[]"
    assert body["prompt_tokens"] == 10 and body["total_ms"] == 900 and body["model"] == "qwen3:14b"
    assert (body["first_line"], body["last_line"], body["source"]) == (0, 1, "run")
    other = make_user(email="o@example.com")
    theirs = _chunk(db, other, make_doc(other, ["x"]))
    assert app_client.get(f"/ollama/chunks/{theirs.id}").status_code == 404
    assert app_client.get("/ollama/chunks/999999").status_code == 404


def test_stream_events_and_saves(app_client, me, make_doc, db, wire):
    _set_up(db, me)
    wire[0](thinking="Hmm.")
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)
    r = _stream(app_client, doc, 2)
    assert r.headers["content-type"].startswith("text/event-stream")
    ev = events(r.text)
    chunk = db.scalar(select(OllamaChunk).where(OllamaChunk.document_id == doc.id))
    assert ev == [
        ("plan", {"first_line": 2, "last_line": 3}),
        ("thinking", {"text": "Hmm."}),
        ("line", {"line_number": 2, "text": "T2"}),
        ("line", {"line_number": 3, "text": "T3"}),
        ("saved", {"chunk_ids": [chunk.id]}),
        ("done", {}),
    ]
    assert chunk.source == "manual" and chunk.job_id is None and chunk.reasoning == "Hmm."
    assert _suggested(db, doc) == {2: "T2", 3: "T3"}


def test_stream_sends_the_steady_num_ctx_for_the_prefs(app_client, me, make_doc, db, wire,
                                                       monkeypatch):
    _set_up(db, me)
    sent = []

    def handle(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW)
        body = json.loads(request.content)
        sent.append(body["options"]["num_ctx"])
        ids = _asked(body)
        answer = json.dumps({"lines": [{"id": n, "text": f"T{n}"} for n in ids]})
        return httpx.Response(200, content=_ndjson(answer))
    monkeypatch.setattr(ollama_editor, "http_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)
    _stream(app_client, doc, 2)
    ep, _ = endpoint.load(db, me.id)
    assert sent == [steady_ctx(ep.system_prompt, 2, 1)]  # what a run with these prefs sends


def test_stream_reroll_replaces(app_client, me, make_doc, db, wire):
    _set_up(db, me)
    install, calls = wire
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)
    _stream(app_client, doc, 0)
    install(prefix="R")
    ev = events(_stream(app_client, doc, 1, reroll=True).text)
    assert [e for e in ev if e[0] == "line"] == [
        ("line", {"line_number": 0, "text": "R0"}), ("line", {"line_number": 1, "text": "R1"})]
    assert ev[-1] == ("done", {})
    assert _suggested(db, doc) == {0: "R0", 1: "R1"}
    sources = db.scalars(select(OllamaChunk.source).order_by(OllamaChunk.id)).all()
    assert sources == ["manual", "reroll"]


def test_second_by_hand_request_reuses_saved_results(app_client, me, make_doc, db, wire):
    _set_up(db, me)
    _, calls = wire
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)
    _stream(app_client, doc, 0)
    assert calls.count("/api/chat") == 1
    ev = events(_stream(app_client, doc, 1).text)  # answered by the first request
    assert ev == [("plan", {"first_line": 0, "last_line": 1}),
                  ("line", {"line_number": 1, "text": "T1"}), ("done", {})]
    assert calls.count("/api/chat") == 1


async def test_request_waiting_for_the_lane_reuses_what_the_holder_saved(me, make_doc, db, wire):
    _set_up(db, me)
    _, calls = wire
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)
    prep = ollama_editor._prepare(db, me.id, doc.id, 0, False)
    release = asyncio.Event()

    async def holder():
        async with LANES.hold(me.id, priority=False):
            await release.wait()

    task = asyncio.create_task(holder())
    await asyncio.sleep(0)
    gen = ollama_editor._events(prep)
    assert await anext(gen) == ("plan", {"first_line": 0, "last_line": 1})
    assert await anext(gen) == ("waiting", {"reason": "run"})
    pending = asyncio.create_task(anext(gen))
    await asyncio.sleep(0.05)
    assert not pending.done()
    # meanwhile the holder answered the same chunk
    first = ollama_editor._prepare(db, me.id, doc.id, 0, False)
    from api.ollama.chunks import RequestStats
    from api.ollama.work import save
    stats = RequestStats(first_line=0, last_line=1, asked=2, ok=True, clamped=False, depth=0,
                         reasoning="", prompt="[]")
    save(db, me.id, first.plan, [stats], {0: "H0", 1: "H1"}, source="run", job_id=None,
         p=first.prefs, model="m")
    release.set()
    rest = [await pending] + [e async for e in gen]
    await task
    assert rest == [("line", {"line_number": 0, "text": "H0"}),
                    ("line", {"line_number": 1, "text": "H1"}), ("done", {})]
    assert "/api/chat" not in calls


def test_stream_blank_line_unset_and_errors(app_client, me, make_user, make_doc, db, wire,
                                           monkeypatch):
    doc = make_doc(me, ["a", ""], translated=False)
    ev = events(_stream(app_client, doc, 0).text)
    assert ev[0][0] == "needs_setup" and len(ev) == 1  # no credential yet
    _set_up(db, me)
    assert events(_stream(app_client, doc, 1).text) == [("done", {})]  # nothing to translate
    assert _stream(app_client, doc, 7).status_code == 404
    other = make_user(email="o@example.com")
    assert _stream(app_client, make_doc(other, ["x"]), 0).status_code == 404

    def down():
        def fail(request):
            raise httpx.ConnectError("no")
        return httpx.AsyncClient(transport=httpx.MockTransport(fail))
    monkeypatch.setattr(ollama_editor, "http_client", down)
    ev = events(_stream(app_client, doc, 0).text)
    assert ev[0][0] == "plan" and ev[-1][0] == "error" and "unreachable" in ev[-1][1]["message"]
    assert _suggested(db, doc) == {}


def test_rejected_answer_is_halved_and_only_the_checked_lines_are_saved(
        app_client, me, make_doc, db, wire, monkeypatch):
    _set_up(db, me)
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)

    def handle(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW)
        ids = _asked(json.loads(request.content))
        if len(ids) == 2:  # the whole chunk: line 3 is missing, so the check rejects it
            answer = {"lines": [{"id": ids[0], "text": "X"}]}
        else:
            answer = {"lines": [{"id": n, "text": f"H{n}"} for n in ids]}
        return httpx.Response(200, content=_ndjson(json.dumps(answer)))
    monkeypatch.setattr(ollama_editor, "http_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    ev = events(_stream(app_client, doc, 2).text)
    lines = [d for k, d in ev if k == "line"]
    assert lines[0] == {"line_number": 2, "text": "X"}  # shown live, then replaced
    assert lines[-2:] == [{"line_number": 2, "text": "H2"}, {"line_number": 3, "text": "H3"}]
    assert len(ev[-2][1]["chunk_ids"]) == 3 and ev[-1] == ("done", {})
    assert _suggested(db, doc) == {2: "H2", 3: "H3"}


async def _settle():
    await asyncio.gather(*list(ollama_editor._TASKS))


async def test_a_disconnect_leaves_the_chunk_running_to_its_save(me, make_doc, db, wire):
    _set_up(db, me)
    _, calls = wire
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)
    gen = ollama_editor._events(ollama_editor._prepare(db, me.id, doc.id, 2, False))
    assert await anext(gen) == ("plan", {"first_line": 2, "last_line": 3})
    assert (await anext(gen))[0] == "line"
    await gen.aclose()  # the card moved on
    await _settle()
    assert _suggested(db, doc) == {2: "T2", 3: "T3"}
    rest = [e async for e in ollama_editor._events(
        ollama_editor._prepare(db, me.id, doc.id, 3, False))]
    assert rest[1:] == [("line", {"line_number": 3, "text": "T3"}), ("done", {})]
    assert calls.count("/api/chat") == 1


async def test_a_request_for_another_line_follows_the_chunk_in_flight(
        me, make_doc, db, wire, monkeypatch):
    _set_up(db, me)
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)
    gate, chats = asyncio.Event(), []

    async def handle(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW)
        chats.append(request)
        await gate.wait()
        ids = _asked(json.loads(request.content))
        answer = json.dumps({"lines": [{"id": n, "text": f"T{n}"} for n in ids]})
        return httpx.Response(200, content=_ndjson(answer))
    monkeypatch.setattr(ollama_editor, "http_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    first = ollama_editor._events(ollama_editor._prepare(db, me.id, doc.id, 2, False))
    assert await anext(first) == ("plan", {"first_line": 2, "last_line": 3})
    reading = asyncio.create_task(anext(first))
    while not chats:
        await asyncio.sleep(0.01)
    second = ollama_editor._events(ollama_editor._prepare(db, me.id, doc.id, 3, False))
    assert await anext(second) == ("plan", {"first_line": 2, "last_line": 3})
    gate.set()
    a = [await reading] + [e async for e in first]
    b = [e async for e in second]
    assert a == b and a[-1] == ("done", {}) and a[-2][0] == "saved"
    assert len(chats) == 1 and _suggested(db, doc) == {2: "T2", 3: "T3"}
    assert ollama_editor._RUNNING == {}


def test_a_line_shown_live_then_failed_ends_with_null(
        app_client, me, make_doc, db, wire, monkeypatch):
    _set_up(db, me)
    doc = make_doc(me, ["a", "b", "c", "d"], translated=False)

    def handle(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json=SHOW)
        ids = _asked(json.loads(request.content))
        if ids == [2]:
            answer = {"lines": [{"id": 2, "text": "H2"}]}
        else:  # the whole chunk shows only line 3; alone, line 3 gets no answer
            answer = {"lines": [{"id": 3, "text": "X3"}] if len(ids) == 2 else []}
        return httpx.Response(200, content=_ndjson(json.dumps(answer)))
    monkeypatch.setattr(ollama_editor, "http_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    ev = events(_stream(app_client, doc, 2).text)
    lines = [d for k, d in ev if k == "line"]
    assert lines[0] == {"line_number": 3, "text": "X3"}
    assert lines[-1] == {"line_number": 3, "text": None}
    assert ev[-2][0] == "saved" and _suggested(db, doc) == {2: "H2"}
