"""Score how a suggestion fared against the line's final translation."""

from __future__ import annotations

import difflib
import unicodedata

EDITED_MIN = 0.5


def _normalise(text: str) -> str:
    kept = "".join(c for c in text.casefold() if not unicodedata.category(c).startswith("P"))
    return " ".join(kept.split())


def score(suggestion: str, final: str) -> tuple[str, float]:
    a, b = _normalise(suggestion), _normalise(final)
    if a == b:
        return "used", 1.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ("edited" if ratio >= EDITED_MIN else "ignored"), ratio
