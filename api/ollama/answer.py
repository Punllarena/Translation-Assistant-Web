"""Check a model's JSON answer against the lines that were asked."""

from __future__ import annotations

import json

from api.ollama.chunks import Item


class AnswerError(ValueError):
    pass


def check(answer: str, asked: list[Item]) -> dict[int, str]:
    try:
        data = json.loads(answer)
    except ValueError as exc:
        raise AnswerError("not JSON") from exc
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list):
        raise AnswerError("no lines array")
    if len(lines) != len(asked):
        raise AnswerError(f"expected {len(asked)} lines, got {len(lines)}")
    out: dict[int, str] = {}
    for entry, item in zip(lines, asked, strict=True):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), int) \
                or isinstance(entry.get("id"), bool) or not isinstance(entry.get("text"), str):
            raise AnswerError("malformed line")
        if entry["id"] != item.line_number:
            raise AnswerError(f"expected id {item.line_number}, got {entry['id']}")
        text = entry["text"].strip()
        if not text and item.prefix != "$":
            raise AnswerError(f"line {item.line_number} is empty")
        out[item.line_number] = text
    return out


def halves(items: list[Item]) -> tuple[list[Item], list[Item]]:
    """Split at the `%` item nearest the middle (never the first); else at the middle."""
    mid = len(items) / 2
    heads = [n for n, i in enumerate(items) if n > 0 and i.prefix == "%"]
    at = min(heads, key=lambda n: abs(n - mid)) if heads else len(items) // 2
    return items[:at], items[at:]
