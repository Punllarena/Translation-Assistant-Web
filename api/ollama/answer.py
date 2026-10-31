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
    """The asked lines from the model's JSON answer, keyed by line number.

    Only the asked lines matter: an entry for any other line (a model that returns the whole
    chunk, `(done)` lines included) is ignored. Each asked line must come back exactly once,
    in the order asked, and must not be empty, malformed or its own source.
    """
    try:
        data = json.loads(answer)
    except ValueError as exc:
        raise AnswerError(f"not JSON, got: {_excerpt(answer)}") from exc
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list):
        raise AnswerError("no lines array")
    wanted = {item.line_number for item in asked}
    found: dict[int, str] = {}
    order: list[int] = []
    for entry in lines:
        if not isinstance(entry, dict):
            continue  # an extra of no use: the ids of the asked lines are what we read
        number = entry.get("id")
        if not isinstance(number, int) or isinstance(number, bool) or number not in wanted:
            continue  # not one of ours, e.g. a line that was already translated
        if number in found:
            raise AnswerError(f"line {number} was returned twice")
        text = entry.get("text")
        if not isinstance(text, str):
            raise AnswerError(f"line {number} is malformed")
        found[number] = text
        order.append(number)
    expected = [item.line_number for item in asked]
    if len(found) != len(expected):
        missing = [n for n in expected if n not in found]
        names = ", ".join(str(n) for n in missing[:5]) + ("…" if len(missing) > 5 else "")
        raise AnswerError(f"missing {len(missing)} of {len(expected)} lines: {names}")
    if order != expected:
        raise AnswerError("asked lines came back out of order")
    out: dict[int, str] = {}
    for item in asked:
        text = found[item.line_number].strip()
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
