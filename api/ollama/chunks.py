"""Cut a chapter's lines into paragraph-aligned chunks for one Ollama request."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    """One chapter line. `known` is a translation or suggestion; None means the line is asked."""

    line_number: int
    prefix: str
    text: str
    known: str | None = None


@dataclass
class RequestStats:
    """One Ollama request's record: filled by the runner, saved by the store."""

    first_line: int
    last_line: int
    asked: int
    ok: bool
    clamped: bool
    depth: int
    reasoning: str
    prompt: str  # JSON of the messages
    error: str | None = None  # why check() rejected the answer; None when it was accepted
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    prompt_ms: int | None = None
    eval_ms: int | None = None
    load_ms: int | None = None
    total_ms: int | None = None
    first_token_ms: int | None = None


def paragraphs(items: Sequence[Item]) -> list[list[Item]]:
    """Empty lines are dropped and end a paragraph; `%` starts one, as does a `$` with none open."""
    out: list[list[Item]] = []
    current: list[Item] | None = None
    for item in items:
        if not item.text:
            current = None
            continue
        if current is None or item.prefix == "%":
            current = []
            out.append(current)
        current.append(item)
    return out


def cut(items: Sequence[Item], chunk_lines: int) -> list[list[Item]]:
    paras = paragraphs(items)
    if chunk_lines == 0:
        flat = [i for p in paras for i in p]
        return [flat] if flat else []
    chunks: list[list[Item]] = []
    current: list[Item] = []
    for para in paras:
        if current and len(current) + len(para) > chunk_lines:
            chunks.append(current)
            current = []
        current = current + para
    if current:
        chunks.append(current)
    return chunks


def chunk_index(chunks: list[list[Item]], line_number: int) -> int | None:
    for n, chunk in enumerate(chunks):
        if any(i.line_number == line_number for i in chunk):
            return n
    return None


def context_before(items: Sequence[Item], first_line: int, n: int) -> list[Item]:
    """The last `n` non-empty items before `first_line`."""
    if n <= 0:
        return []
    before = [i for i in items if i.line_number < first_line and i.text]
    return before[-n:]
