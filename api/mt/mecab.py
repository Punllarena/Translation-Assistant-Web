"""MeCab word-by-word analysis (desktop ta/translators/mecab.py, fugashi branch),
as structured entries with edict glosses when an edict2 file is configured."""

from api.core import nouns
from api.mt import jparser, lookup
from api.mt.base import NeedsSetup


def run(text: str) -> list[dict]:
    try:
        tagger = nouns.tagger()
    except nouns.Unavailable as exc:
        raise NeedsSetup(str(exc)) from exc
    path = lookup.edict_path()
    edict = jparser.load_index(path) if path else None
    with nouns._lock:  # one MeCab tagger, not thread-safe (phase 4)
        words = list(tagger(text))
    rows = []
    for word in words:
        f = word.feature
        reading = getattr(f, "kana", "") or getattr(f, "pron", "") or ""
        lemma = (getattr(f, "lemma", "") or "").split("-")[0]
        rows.append((word, f, reading, lemma if lemma != word.surface else ""))
    keys = {k for word, _f, _r, lemma in rows for k in (word.surface, lemma) if k}
    lk = lookup.layered(keys, edict)
    out = []
    for word, f, reading, lemma in rows:
        hit = lk and (lk.get(lemma or word.surface) or lk.get(word.surface))
        out.append({
            "surface": word.surface, "reading": reading, "lemma": lemma,
            "pos": getattr(f, "pos1", "") or "", "gloss": hit.gloss if hit else "",
            "tense": "", "base_form": "", "matched": True,
        })
    return out
