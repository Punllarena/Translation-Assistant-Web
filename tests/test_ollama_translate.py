import json

import httpx
import pytest

from api.mt.base import BackendError
from api.mt.ollama import ModelInfo
from api.ollama import translate as tr
from api.ollama.chunks import Item
from api.ollama.translate import Endpoint, translate


def ep(**kw):
    info = kw.pop("info", ModelInfo(thinking=False, context_length=None))
    return Endpoint("http://ol", "", "m", "sys {src} {dst}", "ja", "en",
                    kw.pop("num_thread", None), info)


def items(*nums, known=()):
    return [Item(n, "%" if n == nums[0] else "", f"orig{n}", f"K{n}" if n in known else None)
            for n in nums]


def ndjson(content, done=True, thinking=""):
    out = []
    if thinking:
        out.append({"message": {"thinking": thinking}})
    for i in range(0, len(content), 7):
        out.append({"message": {"content": content[i:i + 7]}})
    if done:
        out.append({"done": True, "eval_count": 3})
    return "\n".join(json.dumps(o) for o in out).encode()


def answer(*nums):
    return json.dumps({"lines": [{"id": n, "text": f"T{n}"} for n in nums]})


def client(handler, seen=None):
    def wrapped(request):
        body = json.loads(request.content)
        if seen is not None:
            seen.append(body)
        return handler(body)
    return httpx.AsyncClient(transport=httpx.MockTransport(wrapped))


def asked_ids(body):
    section = body["messages"][1]["content"].split("Translate:\n")[1]
    return [int(line[1:line.index("]")]) for line in section.splitlines() if line.startswith("[")]


def by_ids(body):
    return httpx.Response(200, content=ndjson(answer(*asked_ids(body))))


async def test_good_answer_one_request():
    seen = []
    async with client(by_ids, seen) as c:
        r = await translate(c, ep(num_thread=4), [], items(1, 2, 3))
    assert r.lines == {1: "T1", 2: "T2", 3: "T3"} and r.failed == []
    assert len(r.requests) == 1 and r.requests[0].ok and r.requests[0].depth == 0
    assert r.requests[0].output_tokens == 3 and r.requests[0].first_token_ms is not None
    assert seen[0]["options"]["num_thread"] == 4 and "think" not in seen[0]


async def test_bad_answer_halves_then_succeeds():
    def handler(body):
        ids = asked_ids(body)
        if len(ids) == 4:
            return httpx.Response(200, content=ndjson("not json"))
        return httpx.Response(200, content=ndjson(answer(*ids)))

    seen = []
    async with client(handler, seen) as c:
        r = await translate(c, ep(), [], items(1, 2, 3, 4))
    assert r.lines == {1: "T1", 2: "T2", 3: "T3", 4: "T4"}
    assert [q.ok for q in r.requests] == [False, True, True]
    assert [q.depth for q in r.requests] == [0, 1, 1]
    # the second half sees the first half's answers as context
    assert "[2] orig2 => T2" in seen[2]["messages"][1]["content"]


async def test_single_line_failure_is_recorded_not_raised():
    def handler(body):
        return httpx.Response(200, content=ndjson('{"lines": []}'))

    async with client(handler) as c:
        r = await translate(c, ep(), [], items(5))
    assert r.lines == {} and r.failed == [5]
    assert len(r.requests) == 1 and not r.requests[0].ok


async def test_clamped_when_over_model_context():
    seen = []
    async with client(by_ids, seen) as c:
        r = await translate(c, ep(info=ModelInfo(False, 1)), [], items(1, 2))
    assert r.lines == {1: "T1", 2: "T2"}
    assert [q.clamped for q in r.requests] == [True, True]
    assert [len(asked_ids(b)) for b in seen] == [1, 1]  # single lines are sent anyway


async def test_truncated_stream_counts_as_failed_answer():
    def cut(body):
        ids = asked_ids(body)
        if len(ids) == 2:
            return httpx.Response(200, content=ndjson(answer(*ids)[:20]))
        return httpx.Response(200, content=ndjson(answer(*ids)))

    async with client(cut) as c:
        r = await translate(c, ep(), [], items(1, 2))
    assert r.lines == {1: "T1", 2: "T2"} and r.requests[0].ok is False

    def no_done(body):
        return httpx.Response(200, content=ndjson(answer(*asked_ids(body)), done=False))

    async with client(no_done) as c:
        with pytest.raises(BackendError):
            await translate(c, ep(), [], items(1, 2))


async def test_on_line_called_for_asked_lines_only():
    got, thoughts = [], []

    async def on_line(n, t):
        got.append((n, t))

    async def on_thinking(t):
        thoughts.append(t)

    def handler(body):
        return httpx.Response(200, content=ndjson(answer(1, 3), thinking="hmm"))

    async with client(handler) as c:
        r = await translate(c, ep(info=ModelInfo(True, None)), [], items(1, 2, 3, known=(2,)),
                            on_line=on_line, on_thinking=on_thinking)
    assert got == [(1, "T1"), (3, "T3")] and thoughts == ["hmm"]
    assert r.requests[0].reasoning == "hmm"


async def test_nothing_asked_makes_no_request():
    def boom(body):
        raise AssertionError("called")

    async with client(boom) as c:
        r = await translate(c, ep(), [], items(1, known=(1,)))
    assert r.lines == {} and r.requests == []


def test_clock_seam_exists():
    assert callable(tr._now)
