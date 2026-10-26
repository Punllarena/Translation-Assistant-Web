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


FIXTURES = Path(__file__).parent / "fixtures" / "mt"


async def test_show_reads_capabilities_and_context_length():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), body=json.loads(request.content))
        return httpx.Response(200, content=(FIXTURES / "ollama_show.json").read_bytes())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        info = await ollama.show(c, "http://ol/", "", "gemma3")
    assert info == ollama.ModelInfo(thinking=True, context_length=32768)
    assert seen["url"] == "http://ol/api/show"
    assert seen["body"] == {"model": "gemma3"}


async def test_show_without_thinking_or_context_length_and_http_error():
    body = {"capabilities": ["completion"], "model_info": {}}
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=body))) as c:
        assert await ollama.show(c, "http://ol", "", "m") == ollama.ModelInfo(False, None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(404, json={"error": "model not found"}))) as c:
        with pytest.raises(BackendError, match="404.*model not found"):
            await ollama.show(c, "http://ol", "", "m")


async def test_chat_sends_format_options_and_omits_think():
    from api.ollama.prompt import FORMAT_SCHEMA

    seen = {}

    def handler(request):
        seen.update(body=json.loads(request.content), auth=request.headers.get("authorization"))
        return httpx.Response(200, content=(FIXTURES / "ollama_chunk_stream.ndjson").read_bytes())

    msgs = [{"role": "user", "content": "x"}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await collect(ollama.chat(c, "http://ol", "tok", "m", msgs, schema=FORMAT_SCHEMA,
                                  options={"num_ctx": 4096}, think=False, keep_alive="10m"))
    body = seen["body"]
    assert body["format"] == FORMAT_SCHEMA
    assert body["options"]["num_ctx"] == 4096
    assert "think" not in body
    assert body["stream"] is True and body["keep_alive"] == "10m" and body["messages"] == msgs
    assert seen["auth"] == "Bearer tok"


async def test_chat_sends_think_true_when_asked():
    seen = {}

    def handler(request):
        seen.update(body=json.loads(request.content))
        return httpx.Response(200, content=(FIXTURES / "ollama_chunk_stream.ndjson").read_bytes())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await collect(ollama.chat(c, "http://ol", "", "m", [], schema={}, options={},
                                  think=True, keep_alive="10m"))
    assert seen["body"]["think"] is True


async def test_chat_yields_content_then_stats():
    data = (FIXTURES / "ollama_chunk_stream.ndjson").read_bytes()
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=data))) as c:
        events = await collect(ollama.chat(c, "http://ol", "", "m", [], schema={}, options={},
                                           think=True, keep_alive="10m"))
    assert events[0] == ("thinking", {"text": "Weigh it."})
    assert events[1:3] == [("content", {"text": '{"lines":'}), ("content", {"text": "[]}"})]
    kind, stats = events[3]
    assert kind == "stats" and len(events) == 4
    assert stats == {"prompt_tokens": 412, "output_tokens": 30, "prompt_ms": 1500,
                     "eval_ms": 9200, "load_ms": 250, "total_ms": 11000}


async def test_chat_stats_missing_fields_are_none_and_truncation_raises():
    done = b'{"message":{"content":""},"done":true}\n'
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=done))) as c:
        events = await collect(ollama.chat(c, "http://ol", "", "m", [], schema={}, options={},
                                           think=False, keep_alive="10m"))
    assert events == [("stats", dict.fromkeys(
        ("prompt_tokens", "output_tokens", "prompt_ms", "eval_ms", "load_ms", "total_ms")))]
    part = b'{"message":{"content":"a"},"done":false}\n'
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=part))) as c:
        with pytest.raises(BackendError, match="ended the stream early"):
            await collect(ollama.chat(c, "http://ol", "", "m", [], schema={}, options={},
                                      think=False, keep_alive="10m"))
