"""Build the chat messages for one chunk and size the context window."""

from __future__ import annotations

import math

from api.mt.languages import display
from api.ollama.chunks import Item

FORMAT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["id", "text"],
            },
        }
    },
    "required": ["lines"],
}

FORMAT_RULES = (
    "Each line is labelled with its line number in square brackets. Translate only the lines under "
    '"Translate:". Lines under "Context:" and lines marked (done) are already translated: do not '
    "translate or return them. Return every line to translate exactly once, in the same order, as "
    'JSON {"lines":[{"id":<line number>,"text":<translation>}]}. A line marked $ continues the line '
    'before it; its text may be "" when its meaning went into the line before.'
)


def build_messages(system_prompt: str, src: str, dst: str, before: list[Item], chunk: list[Item]) -> list[dict]:
    system = system_prompt.replace("{src}", display(src)).replace("{dst}", display(dst))
    parts: list[str] = []
    if before:
        parts.append("Context:\n" + "\n".join(_line(i, context=True) for i in before))
    parts.append("Translate:\n" + "\n".join(_line(i) for i in chunk))
    return [
        {"role": "system", "content": system + "\n\n" + FORMAT_RULES},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _line(item: Item, context: bool = False) -> str:
    mark = "$" if item.prefix == "$" and not context else ""
    head = f"[{item.line_number}]{mark} {item.text}"
    if item.known is None:
        return head
    return head + (" => " if context else " (done) => ") + item.known


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return math.ceil(ascii_chars / 4) + (len(text) - ascii_chars)


def num_ctx(messages: list[dict], asked: int) -> int:
    need = sum(estimate_tokens(m["content"]) for m in messages) + 60 * asked + 512
    return max(2048, math.ceil(need / 1024) * 1024)
