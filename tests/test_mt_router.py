import json
import socket
from contextlib import contextmanager

import httpx
import pytest

from api.config import get_settings
from api.models import MtCache
from api.mt import prefs
from api.routers import mt as mt_router


def events(body: str):
    out = []
    for frame in body.strip().split("\n\n"):
        kind, data = frame.split("\n", 1)
        out.append((kind.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


@pytest.fixture
def wire(monkeypatch, db):
    """Route MT HTTP through a handler; route the stream's cache session to the test db."""
    calls = []

    def install(handler):
        def http_client():
            return httpx.AsyncClient(transport=httpx.MockTransport(
                lambda r: (calls.append(r), handler(r))[1]))
        monkeypatch.setattr(mt_router, "http_client", http_client)

    @contextmanager
    def session():
        original = db.commit
        db.commit = db.flush
        try:
            yield db
        finally:
            db.commit = original

    monkeypatch.setattr(mt_router, "SessionLocal", session)
    return install, calls


@pytest.fixture
def resolve_to(monkeypatch):
    """Make the SSRF guard resolve user hosts (only) to the given address."""
    real = socket.getaddrinfo

    def install(address, host="mine"):
        def fake(h, *args, **kwargs):
            if h == host:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]
            return real(h, *args, **kwargs)
        monkeypatch.setattr(socket, "getaddrinfo", fake)

    return install


def stream(client, doc, backend, n=0, **extra):
    return client.get("/mt/stream", params={"backend": backend, "document_id": doc.id,
                                            "line_number": n, **extra})


def deepl_ok(r):
    return httpx.Response(200, json={"translations": [{"text": "This is the first line."}]})


def test_deepl_result_is_streamed_then_cached(app_client, me, make_doc, wire, db):
    install, calls = wire
    install(deepl_ok)
    app_client.post("/credentials", json={"kind": "deepl", "secret": "abc:fx"})
    doc = make_doc(me, ["%一行目です。"], translated=False)
    first = events(stream(app_client, doc, "deepl").text)
    assert first == [("result", {"text": "This is the first line."}), ("done", {"cached": False})]
    second = events(stream(app_client, doc, "deepl").text)
    assert second[-1] == ("done", {"cached": True}) and len(calls) == 1
    assert db.query(MtCache).one().backend == "deepl"


def test_glossary_applied_text_is_what_gets_translated(
    app_client, db, me, make_doc, make_series, wire
):
    from api.models import GlossaryEntry
    install, calls = wire
    install(deepl_ok)
    series, other = make_series(me, "S"), make_series(me, "Other")
    db.add(GlossaryEntry(series_id=other.id, phrase="一行目", translation="wrong_line"))
    db.flush()  # the other series' row first: a leak would apply it
    db.add(GlossaryEntry(series_id=series.id, phrase="一行目", translation="first_line"))
    db.flush()
    app_client.post("/credentials", json={"kind": "deepl", "secret": "k:fx"})
    doc = make_doc(me, ["一行目です。"], series=series, translated=False)
    stream(app_client, doc, "deepl")  # no profile_id: the chapter's series glossary
    assert json.loads(calls[0].content)["text"] == ["first_lineです。"]


def test_blank_line_makes_no_call(app_client, me, make_doc, wire):
    install, calls = wire
    install(deepl_ok)
    app_client.post("/credentials", json={"kind": "deepl", "secret": "k:fx"})
    doc = make_doc(me, ["  "], translated=False)
    assert events(stream(app_client, doc, "deepl").text) == [("done", {"cached": False})]
    assert calls == []


def test_missing_key_is_needs_setup_not_500(app_client, me, make_doc, wire):
    wire[0](deepl_ok)
    doc = make_doc(me, ["猫"], translated=False)
    r = stream(app_client, doc, "deepl")
    assert r.status_code == 200 and events(r.text)[0][0] == "needs_setup"


def test_backend_error_is_an_event_names_status_and_caches_nothing(
        app_client, me, make_doc, wire, db):
    wire[0](lambda r: httpx.Response(403, json={"message": "bad"}))
    app_client.post("/credentials", json={"kind": "deepl", "secret": "secret-key-xyz"})
    doc = make_doc(me, ["猫"], translated=False)
    body = stream(app_client, doc, "deepl").text
    assert events(body) == [("error", {"message": "DeepL answered HTTP 403"})]
    assert "secret-key-xyz" not in body and db.query(MtCache).count() == 0


def test_ollama_streams_chunks_and_caches_only_the_completed_text(
        app_client, me, make_doc, wire, db):
    ndjson = (b'{"message":{"content":"a\\n\\nb"},"done":false}\n'
              b'{"message":{"content":"!"},"done":false}\n{"done":true}\n')
    wire[0](lambda r: httpx.Response(200, content=ndjson))
    app_client.put("/settings", json={"ollama_model": "qwen3"})
    doc = make_doc(me, ["猫"], translated=False)
    ev = events(stream(app_client, doc, "ollama").text)
    assert ev == [("chunk", {"text": "a\n\nb"}), ("chunk", {"text": "!"}),
                  ("done", {"cached": False})]
    row = db.query(MtCache).one()
    assert row.result_text == "a\n\nb!" and row.backend.startswith("ollama:qwen3:")


def test_ollama_failure_mid_stream_caches_nothing(app_client, me, make_doc, wire, db):
    def handler(r):
        return httpx.Response(
            200, content=b'{"message":{"content":"half"},"done":false}\nnot json\n')
    wire[0](handler)
    app_client.put("/settings", json={"ollama_model": "m"})
    doc = make_doc(me, ["猫"], translated=False)
    ev = events(stream(app_client, doc, "ollama").text)
    assert ev[0] == ("chunk", {"text": "half"}) and ev[-1][0] == "error"
    assert db.query(MtCache).count() == 0


def test_analyzers_send_one_analysis_event(app_client, me, make_doc, monkeypatch):
    monkeypatch.setattr(mt_router.jparser, "run", lambda text: [{"surface": text}])
    doc = make_doc(me, ["猫"], translated=False)
    assert events(stream(app_client, doc, "jparser").text) == [
        ("analysis", {"entries": [{"surface": "猫"}]}), ("done", {"cached": False})]


def test_users_own_endpoint_overrides_the_server_default(app_client, me, make_doc, wire,
                                                          resolve_to):
    install, calls = wire
    install(lambda r: httpx.Response(200, json={"translatedText": "ok"}))
    resolve_to("93.184.216.34")
    app_client.post("/credentials", json={"kind": "libretranslate", "endpoint_url": "http://mine:5000"})
    doc = make_doc(me, ["猫"], translated=False)
    stream(app_client, doc, "libretranslate")
    assert str(calls[0].url) == "http://mine:5000/translate"


def test_unknown_backend_and_bad_ids(app_client, me, make_user, make_doc):
    doc = make_doc(me, ["猫"], translated=False)
    assert stream(app_client, doc, "google").status_code == 422
    theirs = make_doc(make_user(email="o@example.com"), ["猫"])
    assert stream(app_client, theirs, "jparser").status_code == 404
    assert stream(app_client, doc, "jparser", n=9).status_code == 404


def test_backends_report_availability_and_languages(app_client, me, wire, monkeypatch):
    wire[0](lambda r: httpx.Response(200, json={"models": []}))
    body = app_client.get("/mt/backends").json()
    assert body["target"] == "en" and body["enabled"] == ["mecab", "jparser"]
    assert body["languages"]["ja"] == "Japanese"
    assert "{src}" in body["ollama_default_prompt"]
    by = {b["name"]: b for b in body["backends"]}
    assert set(by) == {"deepl", "libretranslate", "ollama", "mecab", "jparser"}
    assert by["deepl"]["available"] is False and "DeepL" in by["deepl"]["message"]
    assert by["ollama"]["available"] is False and "model" in by["ollama"]["message"]


def test_malformed_200_body_is_one_error_event_and_caches_nothing(app_client, me, make_doc,
                                                                  wire, db):
    wire[0](lambda r: httpx.Response(200, json={}))
    app_client.post("/credentials", json={"kind": "deepl", "secret": "k:fx"})
    doc = make_doc(me, ["猫"], translated=False)
    assert events(stream(app_client, doc, "deepl").text) == [
        ("error", {"message": "DeepL failed"})]
    assert db.query(MtCache).count() == 0


def test_user_url_to_a_loopback_address_is_needs_setup_without_a_call(
        app_client, me, make_doc, wire, resolve_to):
    install, calls = wire
    install(lambda r: httpx.Response(200, json={"translatedText": "ok"}))
    resolve_to("127.0.0.1")
    app_client.post("/credentials", json={"kind": "libretranslate", "endpoint_url": "http://mine:5000"})
    doc = make_doc(me, ["猫"], translated=False)
    ev = events(stream(app_client, doc, "libretranslate").text)
    assert ev[0][0] == "needs_setup" and "private or local" in ev[0][1]["message"]
    assert len(ev) == 1 and calls == []


def test_private_user_urls_are_allowed_when_the_server_says_so(
        app_client, me, make_doc, wire, resolve_to, monkeypatch):
    install, calls = wire
    install(lambda r: httpx.Response(200, json={"translatedText": "ok"}))
    resolve_to("127.0.0.1")
    monkeypatch.setattr(get_settings(), "mt_allow_private_urls", True)
    app_client.post("/credentials", json={"kind": "libretranslate", "endpoint_url": "http://mine:5000"})
    doc = make_doc(me, ["猫"], translated=False)
    assert events(stream(app_client, doc, "libretranslate").text)[0] == ("result", {"text": "ok"})
    assert len(calls) == 1


def test_ollama_cache_key_fits_the_column_and_keeps_the_hash():
    key = prefs.ollama_cache_key("http://o", "m" * 60, "prompt")
    assert len(key) == prefs.CACHE_BACKEND_MAX and key.startswith("ollama:mmm")


def test_ollama_cache_key_separates_models_endpoints_and_prompts():
    base = ("http://o", "qwen2.5:32b-instruct-q4_K_M", "p")
    keys = {prefs.ollama_cache_key(*base),
            prefs.ollama_cache_key("http://o", "qwen2.5:32b-instruct-q8_0", "p"),
            prefs.ollama_cache_key("http://other", *base[1:]),
            prefs.ollama_cache_key(*base[:2], "q")}
    assert len(keys) == 4 and all(len(k) <= prefs.CACHE_BACKEND_MAX for k in keys)


def test_users_on_different_libretranslate_servers_never_share_results(
        app_client, me, make_user, login, make_doc, wire, db, monkeypatch):
    install, calls = wire
    install(lambda r: httpx.Response(200, json={"translatedText": f"from {r.url.host}"}))
    monkeypatch.setattr(get_settings(), "mt_allow_private_urls", True)
    results = []
    for user, host in ((me, "one"), (make_user(email="two@example.com"), "two")):
        login(app_client, user.email)
        app_client.post("/credentials", json={"kind": "libretranslate",
                                              "endpoint_url": f"http://{host}:5000"})
        doc = make_doc(user, ["猫"], translated=False)
        results.append(events(stream(app_client, doc, "libretranslate").text)[0])
    assert results == [("result", {"text": "from one"}), ("result", {"text": "from two"})]
    assert len(calls) == 2 and db.query(MtCache).count() == 2


def test_users_never_send_each_others_deepl_key_or_ollama_url(
        app_client, me, make_user, login, make_doc, wire, monkeypatch):
    install, calls = wire
    install(lambda r: httpx.Response(200, json={"translations": [{"text": "ok"}]}
                                     if r.url.host != "ollama-a" else {}))
    monkeypatch.setattr(get_settings(), "mt_allow_private_urls", True)
    b = make_user(email="b@example.com")
    app_client.post("/credentials", json={"kind": "deepl", "secret": "key-of-a"})
    app_client.post("/credentials", json={"kind": "ollama", "endpoint_url": "http://ollama-a:11434"})
    app_client.put("/settings", json={"ollama_model": "m"})
    login(app_client, b.email)
    app_client.post("/credentials", json={"kind": "deepl", "secret": "key-of-b"})
    app_client.put("/settings", json={"ollama_model": "m"})
    doc = make_doc(b, ["猫"], translated=False)
    stream(app_client, doc, "deepl")
    stream(app_client, doc, "ollama")
    assert calls[0].headers["Authorization"] == "DeepL-Auth-Key key-of-b"
    assert all(c.url.host != "ollama-a" for c in calls)
    assert all("key-of-a" not in str(c.headers) for c in calls)


def test_disconnect_mid_ollama_stream_closes_upstream_and_caches_nothing(wire, db):
    import asyncio

    closed = []

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'{"message":{"content":"half"},"done":false}\n'
            await asyncio.sleep(10)  # the model is still thinking when the reader leaves
            yield b'{"done":true}\n'

        async def aclose(self):
            closed.append(True)

    wire[0](lambda r: httpx.Response(200, stream=Body()))
    job = mt_router.Job(backend="ollama", text="猫", src="ja", dst="en", url="http://o",
                        model="m", prompt="p", cache_key="ollama:m:x")

    async def read_one_then_leave():
        events = mt_router._events(job)
        first = await anext(events)
        await events.aclose()
        return first

    assert asyncio.run(read_one_then_leave()) == ("chunk", {"text": "half"})
    assert closed and db.query(MtCache).count() == 0


def test_bad_settings_fall_back_to_defaults(app_client, me, wire):
    wire[0](lambda r: httpx.Response(200, json={"models": []}))
    app_client.put("/settings", json={"mt_target": "xx", "mt_enabled": ["deepl", "google", 3]})
    body = app_client.get("/mt/backends").json()
    assert body["target"] == "en" and body["enabled"] == ["deepl"]
