"""DeepL (desktop ta/translators/deepl.py), over its REST API instead of the SDK."""

import httpx

from api.mt.base import BackendError, NeedsSetup
from api.mt.languages import deepl_code

TIMEOUT = 15  # seconds, as the desktop


async def translate(client: httpx.AsyncClient, key: str, text: str, src: str, dst: str) -> str:
    if not key:
        raise NeedsSetup("Add your DeepL API key under Settings → Machine translation.")
    target = deepl_code(dst)
    if not target:
        raise NeedsSetup(f"DeepL cannot translate into {dst}.")
    host = "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"
    body: dict = {"text": [text], "target_lang": target}
    source = deepl_code(src).split("-")[0]  # source codes have no regional variant
    if source:
        body["source_lang"] = source
    try:
        r = await client.post(f"{host}/v2/translate", json=body, timeout=TIMEOUT,
                              headers={"Authorization": f"DeepL-Auth-Key {key}"})
    except httpx.HTTPError as exc:
        raise BackendError(f"DeepL is unreachable ({type(exc).__name__})") from exc
    if r.status_code != 200:
        raise BackendError(f"DeepL answered HTTP {r.status_code}")
    return r.json()["translations"][0]["text"]
