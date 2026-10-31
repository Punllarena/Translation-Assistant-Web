"""Check a model's JSON answer against the lines that were asked."""

from __future__ import annotations

import json
import unicodedata

from api.ollama.chunks import Item


class AnswerError(ValueError):
    pass


def _excerpt(text: str, limit: int = 120) -> str:
    """The start of an answer, whitespace collapsed, for the error message: enough to tell a
    markdown fence from a thinking preamble when a run is diagnosed later."""
    flat = " ".join(text.split())
    if not flat:
        return "(empty answer)"
    return flat[:limit] + ("…" if len(flat) > limit else "")


def _letters(text: str) -> str:
    """The text's letters only: punctuation, digits and spacing are ignored, so a model
    echo (the source with its punctuation stripped, say) still reads as the source."""
    return "".join(c for c in text if unicodedata.category(c).startswith("L"))


def echoes_source(item: Item, text: str) -> bool:
    """The answer is the line it was asked to translate: the model copied the source.
    A line with no letters (a scene break like ■) may legitimately come back unchanged."""
    source = _letters(item.text)
    return bool(source) and source == _letters(text)


def check(answer: str, asked: list[Item]) -> dict[int, str]:
    try:
        data = json.loads(answer)
    except ValueError as exc:
        raise AnswerError(f"not JSON, got: {_excerpt(answer)}") from exc
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
        if echoes_source(item, text):
            raise AnswerError(f"line {item.line_number} was returned as its source")
        out[item.line_number] = text
    return out


def halves(items: list[Item]) -> tuple[list[Item], list[Item]]:
    """Split at the `%` item nearest the middle (never the first); else at the middle."""
    mid = len(items) / 2
    heads = [n for n, i in enumerate(items) if n > 0 and i.prefix == "%"]
    at = min(heads, key=lambda n: abs(n - mid)) if heads else len(items) // 2
    return items[:at], items[at:]
