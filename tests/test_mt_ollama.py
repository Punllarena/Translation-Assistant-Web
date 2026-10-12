import json
from pathlib import Path

import httpx
import pytest

from api.mt import ollama
from api.mt.base import BackendError, NeedsSetup

STREAM = (Path(__file__).parent / "fixtures" / "mt" / "ollama_stream.ndjson").read_bytes()


async def collect(agen):
    return [e async for e in agen]


async def test_stream_yields_thinking_then_chunks_and_sends_the_desktop_payload():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), body=json.loads(request.content),
                    auth=request.headers.get("authorization"))
        return httpx.Response(200, content=STREAM)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        events = await collect(ollama.stream(c, "http://ol.local:11434/", "tok", "qwen3",
                                             "From {src} to {dst}.", "一行目です。", "ja", "en"))
    assert events == [("thinking", {"text": "Consider tone."}),
                      ("chunk", {"text": "This is "}), ("chunk", {"text": "the first line."})]
    assert seen["url"] == "http://ol.local:11434/api/chat"
    assert seen["auth"] == "Bearer tok"
    assert seen["body"] == {
        "model": "qwen3", "stream": True, "think": True,
        "messages": [{"role": "system", "content": "From Japanese (ja) to English (en)."},
                     {"role": "user", "content": "一行目です。"}],
    }


async def test_no_model_needs_setup_and_http_errors_carry_ollamas_detail():
    def handler(request):
        return httpx.Response(404, json={"error": 'model "nope" not found'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(NeedsSetup):
            await collect(ollama.stream(c, "http://ol", "", "", "p", "x", "ja", "en"))
        with pytest.raises(BackendError, match='404.*model "nope" not found'):
            await collect(ollama.stream(c, "http://ol", "", "nope", "p", "x", "ja", "en"))


async def test_closing_the_stream_early_closes_the_upstream_response():
    closed = []

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            for line in STREAM.splitlines(keepends=True):
                yield line

        async def aclose(self):
            closed.append(True)

    def handler(request):
        return httpx.Response(200, stream=Body())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        agen = ollama.stream(c, "http://ol", "", "m", "p", "x", "ja", "en")
        await agen.__anext__()
        await agen.aclose()
    assert closed == [True]


async def test_available_pings_tags():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"models": []}))) as c:
        assert await ollama.available(c, "http://ol", "") is None
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("no")))) as c:
        assert "unreachable" in await ollama.available(c, "http://ol", "")


async def test_midstream_error_object_raises_instead_of_ending_cleanly():
    body = (b'{"model":"m","message":{"role":"assistant","content":"part"},"done":false}\n'
            b'{"error":"out of memory"}\n')

    def handler(request):
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(BackendError, match="out of memory"):
            await collect(ollama.stream(c, "http://ol", "", "m", "p", "x", "ja", "en"))


async def test_stream_that_ends_without_done_is_truncated():
    body = b"".join(STREAM.splitlines(keepends=True)[:-1])

    def handler(request):
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(BackendError, match="ended the stream early"):
            await collect(ollama.stream(c, "http://ol", "", "m", "p", "x", "ja", "en"))


async def test_malformed_ndjson_line_raises_backend_error():
    body = b'{"message":{"content":"a"},"done":false}\n{not json\n'

    def handler(request):
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(BackendError, match="unreadable"):
            await collect(ollama.stream(c, "http://ol", "", "m", "p", "x", "ja", "en"))


async def test_non_object_error_body_does_not_crash_the_status_path():
    def handler(request):
        return httpx.Response(500, json=["not", "an", "object"])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(BackendError, match="^Ollama answered HTTP 500$"):
            await collect(ollama.stream(c, "http://ol", "", "m", "p", "x", "ja", "en"))
