"""Series phrase suggestions: the desktop core.extract_frequent_nouns, ported verbatim,
and the MeCab tagger it runs on."""

import functools
import threading

SETUP = "MeCab is not installed on the server. Install it with: pip install 'ta-web[mecab]'"

# ponytail: one global lock (a MeCab tagger is not thread-safe); a tagger per thread if
# suggestion requests start queueing behind each other.
_lock = threading.Lock()


class Unavailable(Exception):
    """MeCab or its dictionary is missing; the message says how to install it."""


@functools.cache
def _tagger():
    import fugashi

    # No arguments: unidic-lite's own dicrc node format already emits surface, reading,
    # kana, lemma, POS joined by "-" (tab index 4), the columns extract_frequent_nouns
    # reads. "-Ochasen" fails there ("unknown format type [chasen]").
    return fugashi.Tagger()


def tagger():
    try:
        return _tagger()
    except (ImportError, RuntimeError) as exc:
        raise Unavailable(f"{SETUP} ({exc})") from exc


def frequent_nouns(raw_lines: list[str], known: set[str], min_freq: int) -> list[tuple[str, int]]:
    t = tagger()
    with _lock:
        return extract_frequent_nouns(raw_lines, known, min_freq, _tagger=t)


def extract_frequent_nouns(
    raw_lines: list[str],
    already_in_glossary: set[str],
    min_freq: int = 2,
    *,
    _tagger=None,
) -> list[tuple[str, int]]:
    """
    Tokenize raw_lines with MeCab via fugashi, return (noun, count) pairs sorted by count desc.

    Skips: verbs, numbers (名詞-数詞), single-char tokens, terms in already_in_glossary.
    _tagger: injection seam — any object with .parse(str) -> str; defaults to fugashi.Tagger().
    Raises ImportError if fugashi is not installed and _tagger is None.
    """
    if _tagger is None:
        import fugashi as _fugashi
        _tagger = _fugashi.Tagger()

    counts: dict[str, int] = {}
    for line in raw_lines:
        if not line.strip():
            continue
        parsed = _tagger.parse(line)
        for token_line in parsed.split("\n"):
            if not token_line or token_line == "EOS":
                continue
            parts = token_line.split("\t")
            if len(parts) < 5:
                continue
            surface = parts[0]
            features = parts[4].split("-")
            if not features or features[0] != "名詞":
                continue
            if len(features) > 1 and features[1] == "数詞":
                continue
            if len(surface) < 2:
                continue
            if surface in already_in_glossary:
                continue
            counts[surface] = counts.get(surface, 0) + 1

    return sorted(
        [(term, cnt) for term, cnt in counts.items() if cnt >= min_freq],
        key=lambda x: x[1],
        reverse=True,
    )
