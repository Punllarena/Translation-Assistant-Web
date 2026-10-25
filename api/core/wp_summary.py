"""A series' WordPress summary text <-> publish lines. No app imports: a migration uses it."""

import re

# The most characters a series summary may hold (the PATCH cap and the importer's).
MAX_SUMMARY_CHARS = 100_000

_BLANK_LINES = re.compile(r"\n\s*\n")


def summary_lines(text: str) -> list[dict]:
    """One `%` line per paragraph; blank lines separate paragraphs, single newlines are spaces."""
    paragraphs = _BLANK_LINES.split(text.replace("\r\n", "\n"))
    cleaned = (" ".join(p.split("\n")).strip() for p in paragraphs)
    return [{"prefix": "%", "translated_text": p} for p in cleaned if p]


def lines_to_summary(lines: list[dict]) -> str:
    """Inverse of `summary_lines`: groups `$` continuations as `build_chapter_body` does."""
    groups: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].get("prefix") == "$":
            i += 1
            continue
        group = [lines[i]["translated_text"]]
        i += 1
        while i < len(lines) and lines[i].get("prefix") == "$":
            group.append(lines[i]["translated_text"])
            i += 1
        text = " ".join(t for t in group if t.strip())
        if text:
            groups.append(text)
    return "\n\n".join(groups)
