"""Server-side spellcheck: the desktop SpellHighlighter's enchant wiring
(translation_assistant/spellcheck.py at f1a96ce) without Qt. No database imports;
the caller passes the custom words (account-wide plus the series')."""

import re
import threading
from functools import cache

_WORD_RE = re.compile(r"\b[A-Za-z']{2,}\b")
MAX_SUGGESTIONS = 5
# ponytail: one global lock serialises enchant; per-thread dictionaries if spellcheck
# throughput ever matters
_LOCK = threading.Lock()


@cache
def dictionary(lang: str = "en_US"):
    """An enchant dictionary, or None when enchant or every English dictionary is
    missing — spellcheck then degrades to flagging nothing, as on the desktop."""
    try:
        import enchant
    except (ImportError, OSError):
        return None
    for candidate in (lang, "en_US", "en_GB", "en_CA", "en"):
        try:
            return enchant.Dict(candidate)
        except Exception:
            continue
    return None


def _utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def misspellings(text: str, custom: set[str], d) -> list[tuple[int, int, str]]:
    """(start, end, word) for each misspelled word, in UTF-16 code units — the offsets a
    browser string uses, so the client can slice with them as given. `custom` holds
    lowercased words; a word is skipped when its lowercase form is in it."""
    found = []
    offset, prev = 0, 0
    for m in _WORD_RE.finditer(text):
        offset += _utf16_len(text[prev : m.start()])
        prev = m.start()
        word = m.group()
        if word.lower() in custom:
            continue
        try:
            with _LOCK:
                ok = bool(d.check(word))
        except Exception:
            ok = True  # the desktop treats a dictionary error as "spelled correctly"
        if not ok:
            found.append((offset, offset + len(word), word))  # the word is ASCII
    return found


def suggest(d, word: str) -> list[str]:
    try:
        with _LOCK:
            return list(d.suggest(word))[:MAX_SUGGESTIONS]
    except Exception:
        return []
