"""Ollama (desktop ta/translators/ollama.py): streams /api/chat tokens as they arrive."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from api.mt.base import BackendError, Event, NeedsSetup
from api.mt.languages import display

DEFAULT_SYSTEM_PROMPT = (
    # verbatim from the desktop ta/config/settings.py DEFAULT_OLLAMA_SYSTEM_PROMPT
    "You are a professional {src} to {dst} translator.\n\n"
    "Translate the following {src} text to {dst}.\n\n"
    "Requirements:\n"
    "* Preserve the original meaning, tone, nuance, and intent.\n"
    "* Produce natural, grammatically correct {dst}.\n"
    "* Return only the translation — no explanations, notes, or commentary."
)
# Model load + prompt eval can take minutes before the first token (desktop comment).
TIMEOUT = httpx.Timeout(10, read=300)
KEEP_ALIVE = "10m"


@dataclass(frozen=True)
class ModelInfo:
    thinking: bool
    context_length: int | None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _check_status(r: httpx.Response) -> None:
    """Raise BackendError carrying Ollama's own error text for a non-200 answer."""
    if r.status_code == 200:
        return
    await r.aread()
    try:
        body = r.json()
    except ValueError:
        body = None
    detail = body.get("error", "") if isinstance(body, dict) else ""
    raise BackendError(f"Ollama answered HTTP {r.status_code}" + (f": {detail}" if detail else ""))


def _ms(ns) -> int | None:
    return round(ns / 1_000_000) if isinstance(ns, (int, float)) else None


async def show(client: httpx.AsyncClient, url: str, token: str, model: str) -> ModelInfo:
    try:
        r = await client.post(f"{url.rstrip('/')}/api/show", json={"model": model},
                              headers=_headers(token), timeout=10)
        await _check_status(r)
        body = r.json()
    except httpx.HTTPError as exc:
        raise BackendError(f"Ollama is unreachable ({type(exc).__name__})") from exc
    except ValueError as exc:
        raise BackendError("Ollama sent an unreadable response") from exc
    if not isinstance(body, dict):
        raise BackendError("Ollama sent an unreadable response")
    caps = body.get("capabilities")
    info = body.get("model_info")
    ctx = None
    if isinstance(info, dict):
        ctx = next((v for k, v in info.items()
                    if k.endswith(".context_length") and isinstance(v, int)), None)
    return ModelInfo(thinking=isinstance(caps, list) and "thinking" in caps, context_length=ctx)


async def chat(
    client: httpx.AsyncClient, url: str, token: str, model: str, messages: list[dict], *,
    schema: dict, options: dict, think: bool, keep_alive: str,
) -> AsyncIterator[Event]:
    """Stream /api/chat as JSON: thinking and content deltas, then one stats event."""
    payload = {"model": model, "stream": True, "messages": messages, "format": schema,
               "options": options, "keep_alive": keep_alive}
    if think:
        payload["think"] = True
    try:
        async with client.stream("POST", f"{url.rstrip('/')}/api/chat", json=payload,
                                 headers=_headers(token), timeout=TIMEOUT) as r:
            await _check_status(r)
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise BackendError("Ollama sent an unreadable response") from exc
                if not isinstance(obj, dict):
                    raise BackendError("Ollama sent an unreadable response")
                if obj.get("error"):
                    raise BackendError(f"Ollama failed: {obj['error']}")
                message = obj.get("message") or {}
                if message.get("thinking"):
                    yield ("thinking", {"text": message["thinking"]})
                if message.get("content"):
                    yield ("content", {"text": message["content"]})
                if obj.get("done"):
                    yield ("stats", {
                        "prompt_tokens": obj.get("prompt_eval_count"),
                        "output_tokens": obj.get("eval_count"),
                        "prompt_ms": _ms(obj.get("prompt_eval_duration")),
                        "eval_ms": _ms(obj.get("eval_duration")),
                        "load_ms": _ms(obj.get("load_duration")),
                        "total_ms": _ms(obj.get("total_duration")),
                    })
                    return
            raise BackendError("Ollama ended the stream early")
    except httpx.HTTPError as exc:
        raise BackendError(f"Ollama is unreachable ({type(exc).__name__})") from exc


async def available(client: httpx.AsyncClient, url: str, token: str) -> str | None:
    try:
        r = await client.get(f"{url.rstrip('/')}/api/tags", headers=_headers(token), timeout=3)
    except httpx.HTTPError:
        return f"Ollama is unreachable at {url}."
    return None if r.status_code == 200 else f"Ollama answered HTTP {r.status_code}."


async def stream(
    client: httpx.AsyncClient, url: str, token: str, model: str, system_prompt: str,
    text: str, src: str, dst: str,
) -> AsyncIterator[Event]:
    if not model:
        raise NeedsSetup("Choose an Ollama model under Settings → Machine translation.")
    system = system_prompt.replace("{src}", display(src)).replace("{dst}", display(dst))
    payload = {
        "model": model, "stream": True, "think": True,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
    }
    try:
        async with client.stream("POST", f"{url.rstrip('/')}/api/chat", json=payload,
                                 headers=_headers(token), timeout=TIMEOUT) as r:
            await _check_status(r)
            async for line in r.aiter_lines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except ValueError as exc:
                    raise BackendError("Ollama sent an unreadable response") from exc
                if not isinstance(obj, dict):
                    raise BackendError("Ollama sent an unreadable response")
                if obj.get("error"):
                    raise BackendError(f"Ollama failed: {obj['error']}")
                if obj.get("done"):
                    return
                message = obj.get("message", {})
                if message.get("thinking"):
                    yield ("thinking", {"text": message["thinking"]})
                if message.get("content"):
                    yield ("chunk", {"text": message["content"]})
            # Ended without a done object: truncated, so the caller must not cache it.
            raise BackendError("Ollama ended the stream early")
    except httpx.HTTPError as exc:
        raise BackendError(f"Ollama is unreachable ({type(exc).__name__})") from exc
