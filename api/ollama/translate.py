"""Translate one chunk through Ollama: labelled JSON answer, checked, halved on failure."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace

import httpx

from api.mt import ollama
from api.mt.ollama import ModelInfo
from api.ollama.answer import AnswerError, check, halves
from api.ollama.chunks import Item, RequestStats, context_before
from api.ollama.json_lines import LineScanner
from api.ollama.prompt import FORMAT_SCHEMA, build_messages, num_ctx, request_ctx

_now = time.monotonic  # test seam


@dataclass
class Endpoint:
    url: str
    token: str
    model: str
    system_prompt: str
    src: str
    dst: str
    num_thread: int | None
    info: ModelInfo


@dataclass
class ChunkResult:
    lines: dict[int, str] = field(default_factory=dict)
    failed: list[int] = field(default_factory=list)
    requests: list[RequestStats] = field(default_factory=list)
    num_ctx: int = 0  # the largest window sent; a run keeps it so the window never steps down


async def translate(
    client: httpx.AsyncClient, ep: Endpoint, before: list[Item], chunk: list[Item], *,
    on_line: Callable[[int, str], Awaitable[None]] | None = None,
    on_thinking: Callable[[str], Awaitable[None]] | None = None,
    ctx: int = 0, should_stop: Callable[[], Awaitable[bool]] | None = None,
    depth: int = 0, clamped: bool = False,
) -> ChunkResult:
    """``ctx`` is the steady window (``prompt.steady_ctx``); a request needing more gets the
    next power of two. ``should_stop`` is asked before each sub-request of a halving cascade:
    when it says stop, what was checked so far is returned and the lines not yet asked are
    neither answered nor failed. BackendError (transport, HTTP, truncated stream) propagates;
    the caller retries."""
    asked = [i for i in chunk if i.known is None]
    if not asked:
        return ChunkResult()
    messages = build_messages(ep.system_prompt, ep.src, ep.dst, before, chunk)
    need = num_ctx(messages, len(asked))
    limit = ep.info.context_length
    if len(asked) > 1 and limit is not None and need > limit:
        return await _split(client, ep, before, chunk, ChunkResult(), on_line, on_thinking,
                            should_stop, ctx, depth + 1, True)

    sent = request_ctx(ctx, need, limit)
    options: dict = {"num_ctx": sent}
    if ep.num_thread:
        options["num_thread"] = ep.num_thread
    stats = RequestStats(
        first_line=asked[0].line_number, last_line=asked[-1].line_number, asked=len(asked),
        ok=False, clamped=clamped, depth=depth, reasoning="",
        prompt=json.dumps(messages, ensure_ascii=False),
    )
    wanted = {i.line_number for i in asked}
    scanner = LineScanner()
    thinking: list[str] = []
    content: list[str] = []
    started = _now()
    async for kind, data in ollama.chat(
        client, ep.url, ep.token, ep.model, messages, schema=FORMAT_SCHEMA, options=options,
        think=ep.info.thinking, keep_alive=ollama.KEEP_ALIVE,
    ):
        if kind == "thinking":
            thinking.append(data["text"])
            if on_thinking:
                await on_thinking(data["text"])
        elif kind == "content":
            if stats.first_token_ms is None:
                stats.first_token_ms = round((_now() - started) * 1000)
            content.append(data["text"])
            for number, text in scanner.feed(data["text"]):
                if on_line and number in wanted:
                    await on_line(number, text)
        elif kind == "stats":
            for key, value in data.items():
                setattr(stats, key, value)
    stats.reasoning = "".join(thinking)

    try:
        lines = check("".join(content), asked)
    except AnswerError:
        result = ChunkResult(requests=[stats], num_ctx=sent)
        if len(asked) == 1:
            result.failed.append(asked[0].line_number)
            return result
        # the halves keep the window just sent, so the model is not reloaded for them
        return await _split(client, ep, before, chunk, result, on_line, on_thinking,
                            should_stop, sent, depth + 1, clamped)
    stats.ok = True
    return ChunkResult(lines=lines, requests=[stats], num_ctx=sent)


async def _split(client, ep, before, chunk, result, on_line, on_thinking, should_stop, ctx,
                 depth, clamped):
    """Translate both halves; the second one sees the first's answers as context."""
    first, second = halves(chunk)
    if should_stop and await should_stop():
        return result
    a = await translate(client, ep, before, first, on_line=on_line, on_thinking=on_thinking,
                        ctx=ctx, should_stop=should_stop, depth=depth, clamped=clamped)
    result.lines.update(a.lines)
    result.failed += a.failed
    result.requests += a.requests
    result.num_ctx = max(result.num_ctx, a.num_ctx)
    if should_stop and await should_stop():
        return result
    filled = [replace(i, known=a.lines[i.line_number]) if i.line_number in a.lines else i
              for i in first]
    # at least the original context count, plus the first half so its answers show
    context = context_before(before + filled, second[0].line_number,
                             len(before) + len(first))
    b = await translate(client, ep, context, second, on_line=on_line, on_thinking=on_thinking,
                        ctx=max(ctx, a.num_ctx), should_stop=should_stop, depth=depth,
                        clamped=clamped)
    result.lines.update(b.lines)
    result.failed += b.failed
    result.requests += b.requests
    result.num_ctx = max(result.num_ctx, b.num_ctx)
    return result
