import json
from pathlib import Path

import httpx
import pytest

from api.mt import deepl, libretranslate
from api.mt.base import BackendError, NeedsSetup

FIXTURES = Path(__file__).parent / "fixtures" / "mt"


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def recorded(name, status=200):
    body = json.loads((FIXTURES / name).read_text())
    return lambda request: httpx.Response(status, json=body)


async def test_deepl_free_key_uses_free_host_and_auth_header():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), auth=request.headers["authorization"],
                    body=json.loads(request.content))
        return recorded("deepl_ok.json")(request)

    async with client_for(handler) as c:
        out = await deepl.translate(c, "abc:fx", "一行目です。", "ja", "en")
    assert out == "This is the first line."
    assert seen["url"] == "https://api-free.deepl.com/v2/translate"
    assert seen["auth"] == "DeepL-Auth-Key abc:fx"
    assert seen["body"] == {"text": ["一行目です。"], "target_lang": "EN-US", "source_lang": "JA"}


async def test_deepl_pro_key_uses_pro_host():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return recorded("deepl_ok.json")(request)

    async with client_for(handler) as c:
        await deepl.translate(c, "pro-key", "x", "ja", "en")
    assert urls == ["https://api.deepl.com/v2/translate"]


async def test_deepl_needs_a_key_and_a_supported_target():
    async with client_for(recorded("deepl_ok.json")) as c:
        with pytest.raises(NeedsSetup):
            await deepl.translate(c, "", "x", "ja", "en")
        with pytest.raises(NeedsSetup):
            await deepl.translate(c, "k", "x", "ja", "la")  # Latin: no DeepL target


async def test_deepl_rejection_names_the_status_not_the_key():
    async with client_for(lambda r: httpx.Response(403, json={"message": "Wrong key"})) as c:
        with pytest.raises(BackendError) as exc:
            await deepl.translate(c, "secret-key-123", "x", "ja", "en")
    assert "403" in str(exc.value) and "secret-key-123" not in str(exc.value)


async def test_libretranslate_posts_the_desktop_payload():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), body=json.loads(request.content))
        return recorded("libretranslate_ok.json")(request)

    async with client_for(handler) as c:
        out = await libretranslate.translate(
            c, "http://lt.local:5000/", "k1", "一行目です。", "ja", "en"
        )
    assert out == "This is the first line."
    assert seen["url"] == "http://lt.local:5000/translate"
    assert seen["body"] == {"q": "一行目です。", "source": "ja", "target": "en",
                            "format": "text", "api_key": "k1"}


async def test_libretranslate_without_url_needs_setup_and_errors_carry_status():
    async with client_for(lambda r: httpx.Response(500, text="boom")) as c:
        with pytest.raises(NeedsSetup):
            await libretranslate.translate(c, "", "", "x", "ja", "en")
        with pytest.raises(BackendError, match="500"):
            await libretranslate.translate(c, "http://lt.local", "", "x", "ja", "en")
