"""Per-token readings (UniDic kana of the word as written) for the editor's reading aid."""

from typing import NamedTuple

from api.core import nouns


class Token(NamedTuple):
    surface: str
    kana: str
    pos: str


def tokens(text: str, tagger) -> list[Token]:
    """Tag with fugashi's node API: `tagger(text)` yields words with `.surface` and `.feature`.

    Newlines are whitespace nodes, so a multi-line text keeps every token.
    """
    out: list[Token] = []
    for w in tagger(text):
        kana = w.feature.kana
        if not kana or kana == "*":
            kana = ""
        out.append(Token(w.surface, kana, w.feature.pos1 or ""))
    return out


def read(text: str) -> list[Token]:
    """Tag under the shared MeCab lock; raises nouns.Unavailable when MeCab is missing."""
    t = nouns.tagger()
    with nouns._lock:
        return tokens(text, t)
