"""LibreTranslate (desktop ta/translators/libretranslate.py), async."""

import httpx

from api.mt.base import BackendError, NeedsSetup

TIMEOUT = 15


async def translate(
    client: httpx.AsyncClient, url: str, key: str, text: str, src: str, dst: str
) -> str:
    if not url:
        raise NeedsSetup("Set a LibreTranslate URL under Settings → Machine translation.")
    payload: dict = {"q": text, "source": src or "auto", "target": dst, "format": "text"}
    if key:
        payload["api_key"] = key
    try:
        r = await client.post(f"{url.rstrip('/')}/translate", json=payload, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise BackendError(f"LibreTranslate is unreachable ({type(exc).__name__})") from exc
    if r.status_code != 200:
        raise BackendError(f"LibreTranslate answered HTTP {r.status_code}")
    return r.json()["translatedText"]
