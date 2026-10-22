"""Flatten a Yomitan term row's ``glossary`` into short plain-text meanings."""

import re

MAX_DEPTH = 64

_SKIP_TAGS = frozenset({"table", "img", "rt", "rp"})
_SKIP_DATA = frozenset(
    {"forms", "formsTable", "references", "example-sentence", "examples", "notes", "attribution"}
)
_BLOCK_TAGS = frozenset({"div", "ul", "ol", "li", "p", "br", "tr"})
_XREF = re.compile(r"\[⇒[^\]]*\]")
_SENSE_NO = re.compile(r"^\d+\s+")
_LATIN = re.compile(r"[A-Za-z]")


def _data(node: dict) -> str | None:
    data = node.get("data")
    value = data.get("content") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def _tag(node: dict) -> str | None:
    tag = node.get("tag")
    return tag if isinstance(tag, str) else None


def _skipped(node: dict) -> bool:
    return _tag(node) in _SKIP_TAGS or _data(node) in _SKIP_DATA


def _text(node, depth: int = 0) -> str:
    """All visible text under ``node``, minus skipped tags and sections."""
    if depth > MAX_DEPTH:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_text(child, depth + 1) for child in node)
    if not isinstance(node, dict) or _skipped(node):
        return ""
    inner = _text(node.get("content"), depth + 1)
    return f" {inner} " if _tag(node) in _BLOCK_TAGS else inner


def _lis(node, depth: int, inside_marked: bool, marked_only: bool, out: list[str]) -> None:
    if depth > MAX_DEPTH:
        return
    if isinstance(node, list):
        for child in node:
            _lis(child, depth + 1, inside_marked, marked_only, out)
        return
    if not isinstance(node, dict) or _skipped(node):
        return
    inside_marked = inside_marked or _data(node) == "glossary"
    if _tag(node) == "li" and (inside_marked or not marked_only):
        out.append(_text(node, depth))
        return
    _lis(node.get("content"), depth + 1, inside_marked, marked_only, out)


def _has_marker(node, depth: int = 0) -> bool:
    if depth > MAX_DEPTH:
        return False
    if isinstance(node, list):
        return any(_has_marker(child, depth + 1) for child in node)
    if not isinstance(node, dict) or _skipped(node):
        return False
    return _data(node) == "glossary" or _has_marker(node.get("content"), depth + 1)


def _structured(content) -> list[str]:
    found: list[str] = []
    _lis(content, 0, False, _has_marker(content), found)
    return found or [_text(content)]


def _lines(text: str) -> list[str]:
    """Candidate meanings from a multi-line plain string (the 新和英 shape)."""
    rows = [ln.strip() for ln in text.splitlines()]
    if rows and ("【" in rows[0] or "[ローマ字]" in rows[0]):
        rows = rows[1:]
    out = []
    for row in rows:
        row = _XREF.sub("", row).strip()
        if not row or "　" in row or not _LATIN.search(row):
            continue
        out.append(_SENSE_NO.sub("", row))
    return out


def meanings(glossary: list) -> list[str]:
    """One cleaned meaning per entry of a Yomitan ``glossary`` array."""
    raw: list[str] = []
    for item in glossary:
        if isinstance(item, str):
            raw.extend(_lines(item) if "\n" in item else [item])
        elif isinstance(item, dict):
            kind = item.get("type")
            if kind == "text" and isinstance(item.get("text"), str):
                raw.append(item["text"])
            elif kind == "structured-content":
                raw.extend(_structured(item.get("content")))
    cleaned = (" ".join(m.split()) for m in raw)
    return [m for m in cleaned if m]


def short_gloss(items: list[str], limit: int = 160) -> str:
    """First two meanings joined by ``;``, cut at a ``; `` boundary past ``limit``."""
    out = "; ".join(items[:2])
    if len(out) <= limit:
        return out
    head = out[: limit - 1]
    cut = head.rfind("; ")
    return (head[:cut] if cut > 0 else head).rstrip() + "…"
