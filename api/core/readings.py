"""Per-token readings (UniDic kana) for the editor's reading aid."""

from typing import NamedTuple

from api.core import nouns


class Token(NamedTuple):
    surface: str
    kana: str
    pos: str


def tokens(text: str, tagger) -> list[Token]:
    """Parse MeCab output (surface, pron, kana, lemma, POS joined by '-').

    MeCab emits one EOS per input line; each is skipped so later lines keep their tokens.
    """
    out: list[Token] = []
    for line in tagger.parse(text).split("\n"):
        if line == "EOS":
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        kana = "" if parts[2] == "*" else parts[2]
        out.append(Token(parts[0], kana, parts[4].split("-")[0]))
    return out


def read(text: str) -> list[Token]:
    """Tag under the shared MeCab lock; raises nouns.Unavailable when MeCab is missing."""
    t = nouns.tagger()
    with nouns._lock:
        return tokens(text, t)
