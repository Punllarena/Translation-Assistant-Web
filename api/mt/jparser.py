"""JParser: edict2 lookup with deconjugation, ported from the desktop app as structured entries."""

import functools
import json
import os
import re
import threading
from typing import NamedTuple

from api.mt.base import NeedsSetup

Entry = dict

# edict2: word1;word2(P) [reading] /(pos,...) gloss1/gloss2/EntLXXX/
_EDICT_PAT = re.compile(r"^([^\[/]+?)\s*(?:\[([^\]]+)\])?\s*/(.+)/$")
_WORD_ANNOTATION = re.compile(r"\([^)]+\)")
_POS_PAT = re.compile(r"^\(([^)]+)\)")
_ENTL_PAT = re.compile(r"/EntL\S+/?$")


class DictEntry(NamedTuple):
    headwords: tuple[str, ...]
    reading: str
    pos_tags: frozenset[str]
    gloss: str
    common: bool = False  # True if any headword has (P) marker


class DeconjRule(NamedTuple):
    conj_type: str
    pos: str
    suffix: str
    base_suffix: str
    tense: str
    negative: bool
    formal: bool


class DeconjMatch(NamedTuple):
    base_form: str
    entry: DictEntry
    tense: str
    negative: bool
    formal: bool
    conj_type: str


def _clean_gloss(gloss: str) -> str:
    gloss = _ENTL_PAT.sub("", gloss).rstrip("/")
    parts = [p.strip() for p in gloss.split("/") if p.strip()]
    defs: list[str] = []
    for p in parts:
        pm = _POS_PAT.match(p)
        if pm:
            after = _POS_PAT.sub("", p).strip()
            # strip leading numbered sense marker like "(1)"
            after = re.sub(r"^\(\d+\)\s*", "", after)
            if after:
                defs.append(after)
        elif not p.startswith("("):
            defs.append(p)
        elif ")" in p:
            after = p[p.index(")") + 1:].strip()
            after = re.sub(r"^\(\d+\)\s*", "", after)
            if after:
                defs.append(after)
        if len(defs) >= 2:
            break
    return "; ".join(defs) if defs else gloss[:60]


def _parse_edict_line(line: str) -> DictEntry | None:
    if not line or line.startswith("#"):
        return None
    m = _EDICT_PAT.match(line)
    if not m:
        return None
    words_raw, reading, gloss_raw = m.group(1), m.group(2) or "", m.group(3)

    headwords: list[str] = []
    common = False
    for w in words_raw.split(";"):
        w = w.strip()
        if "(P)" in w:
            common = True
        w_clean = _WORD_ANNOTATION.sub("", w).strip()
        if w_clean:
            headwords.append(w_clean)
    if not headwords:
        return None

    pos_tags: set[str] = set()
    pm = _POS_PAT.match(gloss_raw)
    if pm:
        for tag in pm.group(1).split(","):
            pos_tags.add(tag.strip())

    gloss = _clean_gloss(gloss_raw)
    return DictEntry(
        headwords=tuple(headwords),
        reading=reading.strip(),
        pos_tags=frozenset(pos_tags),
        gloss=gloss,
        common=common,
    )


def _load_conj_rules(path: str) -> list[DeconjRule]:
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-16")
    except UnicodeDecodeError:
        text = raw.decode("utf-8")
    data = json.loads(text)

    # Build a map of stem type → its tenses (for chained conjugation)
    stem_tenses: dict[str, list[dict]] = {}
    for entry in data:
        stem_tenses[entry["Name"]] = entry["Tenses"]

    def _base_suffix_for(tenses: list[dict]) -> str:
        for t in tenses:
            if t["Tense"] == "Remove" and not t["Negative"] and not t["Formal"]:
                return t["Suffix"]
        for t in tenses:
            if t["Tense"] == "Non-past" and not t["Negative"] and not t["Formal"]:
                return t["Suffix"]
        return ""

    rules: list[DeconjRule] = []
    seen: set[tuple] = set()

    def _add(conj_type, pos, suffix, base_suffix, tense, negative, formal):
        if not suffix:
            return
        key = (conj_type, suffix, base_suffix, tense, negative, formal)
        if key in seen:
            return
        seen.add(key)
        rules.append(DeconjRule(
            conj_type=conj_type,
            pos=pos,
            suffix=suffix,
            base_suffix=base_suffix,
            tense=tense,
            negative=negative,
            formal=formal,
        ))

    for entry in data:
        name = entry["Name"]
        pos = entry["Part of Speech"]
        tenses = entry["Tenses"]
        base_sfx = _base_suffix_for(tenses)

        for t in tenses:
            tense = t["Tense"]
            suffix = t["Suffix"]
            negative = t["Negative"]
            formal = t["Formal"]

            if tense == "Remove":
                continue

            if tense == "Stem" and "Next Type" in t:
                # Chained: word = stem + stem_suffix + stem_type_tense_suffix
                # → dict form = stem_rawstem + parent_base_suffix
                next_type = t["Next Type"]
                next_tenses = stem_tenses.get(next_type, [])
                # The stem itself is a valid form (e.g. ta-stem = past)
                # Add compound rules: suffix + next_tense_suffix → base
                for nt in next_tenses:
                    if nt["Tense"] == "Remove":
                        continue
                    ns = nt["Suffix"]
                    compound = suffix + ns
                    if not compound:
                        # stem with no additional suffix = the stem tense itself
                        # e.g. v-ta-stem Past suffix="" → just the suffix from parent stem
                        compound = suffix  # use parent stem suffix
                        _add(name, pos, compound, base_sfx, nt["Tense"],
                             nt["Negative"], nt["Formal"])
                    else:
                        _add(name, pos, compound, base_sfx, nt["Tense"],
                             nt["Negative"], nt["Formal"])
                # Also add the stem suffix alone for stem-only lookup
                # (e.g. 食べた is v1 past → suffix=た, base_suffix=る)
                for nt in next_tenses:
                    if nt["Tense"] in ("Remove",) and not nt["Negative"] and not nt["Formal"]:
                        if suffix:
                            _add(name, pos, suffix, base_sfx, "Past",
                                 negative, formal)
                        break
                # also add plain stem suffix for the case where stem = past (v-ta-stem suffix="")
                for nt in next_tenses:
                    if (nt["Tense"] == "Past" and not nt["Negative"] and not nt["Formal"]
                            and not nt["Suffix"]):
                        if suffix:
                            _add(name, pos, suffix, base_sfx, "Past",
                                 False, False)
                        break
                continue

            if "Next Type" in t:
                continue  # skip other chained forms

            _add(name, pos, suffix, base_sfx, tense, negative, formal)

    rules.sort(key=lambda r: -len(r.suffix))
    return rules


def deconjugate(
    word: str,
    rules: list[DeconjRule],
    index: dict[str, DictEntry],
) -> list[DeconjMatch]:
    results: list[DeconjMatch] = []
    seen: set[str] = set()

    for rule in rules:
        if not word.endswith(rule.suffix):
            continue
        stem = word[: len(word) - len(rule.suffix)]
        base = stem + rule.base_suffix
        if not base or base in seen:
            continue
        entry = index.get(base)
        if entry is None:
            continue
        # POS filter: skip if entry POS is known and doesn't match conj_type prefix
        if entry.pos_tags:
            # conj_type like "v5k" should match edict2 "v5k", "v5" etc.
            # adj-i should match adj-i; adj-na should match adj-na
            ct = rule.conj_type
            tag_match = any(
                t == ct or t.startswith(ct) or ct.startswith(t)
                for t in entry.pos_tags
            )
            if not tag_match:
                continue
        seen.add(base)
        results.append(DeconjMatch(
            base_form=base,
            entry=entry,
            tense=rule.tense,
            negative=rule.negative,
            formal=rule.formal,
            conj_type=rule.conj_type,
        ))

    return results


def _entry(
    surface: str,
    entry: DictEntry,
    *,
    tense: str | None = None,
    base_form: str | None = None,
) -> Entry:
    return {
        "surface": surface,
        "reading": entry.reading,
        "lemma": "",
        "pos": ",".join(sorted(entry.pos_tags)),
        "gloss": entry.gloss,
        "tense": tense or "",
        "base_form": base_form if base_form and base_form != surface else "",
        "matched": True,
    }


_load_lock = threading.Lock()


def _read_index(path: str) -> dict[str, DictEntry] | None:
    if not path:
        return None
    idx: dict[str, DictEntry] = {}
    enc = "euc-jp"
    try:
        with open(path, encoding="euc-jp", errors="strict") as f:
            f.read(200)
    except UnicodeDecodeError:
        enc = "utf-8"
    except OSError:
        return None
    with open(path, encoding=enc, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entry = _parse_edict_line(line)
            if entry is None:
                continue
            for hw in entry.headwords:
                existing = idx.get(hw)
                if existing is None or (entry.common and not existing.common):
                    idx[hw] = entry
            if entry.reading:
                existing = idx.get(entry.reading)
                if existing is None or (entry.common and not existing.common):
                    idx[entry.reading] = entry
    return idx


@functools.lru_cache(maxsize=2)
def _load_index_locked(path: str, mtime_ns: int) -> dict[str, DictEntry] | None:
    return _read_index(path)


def _mtime(path: str) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def load_index(path: str) -> dict[str, DictEntry] | None:
    """Load the edict2 index, cached per (path, mtime) so a replaced file is reloaded.
    Thread-safe; None when there is no file."""
    mtime = _mtime(path) if path else None
    if mtime is None:
        return None
    with _load_lock:
        return _load_index_locked(path, mtime)


@functools.lru_cache(maxsize=2)
def _load_rules_cached(path: str, mtime_ns: int) -> list[DeconjRule]:
    try:
        return _load_conj_rules(path)
    except (OSError, ValueError, KeyError):
        return []


def load_rules(path: str) -> list[DeconjRule]:
    mtime = _mtime(path) if path else None
    if mtime is None:
        return []
    with _load_lock:
        return _load_rules_cached(path, mtime)


def analyze(text: str, index: dict[str, DictEntry], rules: list[DeconjRule]) -> list[Entry]:
    output: list[Entry] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue

        # Greedy longest direct match (up to 12 chars)
        best_direct: tuple[int, DictEntry] | None = None
        for length in range(min(12, len(text) - i), 0, -1):
            token = text[i : i + length]
            if token in index:
                best_direct = (length, index[token])
                break

        # Greedy longest deconjugated match
        best_deconj: tuple[int, DeconjMatch] | None = None
        for length in range(min(12, len(text) - i), 1, -1):
            token = text[i : i + length]
            matches = deconjugate(token, rules, index)
            if matches:
                best_deconj = (length, matches[0])
                break

        if best_direct and best_deconj:
            dl, de = best_direct
            cl, cm = best_deconj
            # prefer longer match; on tie prefer deconj if it adds tense info
            if cl > dl:
                output.append(_entry(
                    text[i : i + cl], cm.entry, tense=cm.tense, base_form=cm.base_form,
                ))
                i += cl
            else:
                token = text[i : i + dl]
                if cl == dl and cm.tense != "Non-past":
                    output.append(_entry(
                        token, cm.entry, tense=cm.tense, base_form=cm.base_form,
                    ))
                else:
                    output.append(_entry(token, de))
                i += dl
        elif best_direct:
            dl, de = best_direct
            output.append(_entry(text[i : i + dl], de))
            i += dl
        elif best_deconj:
            cl, cm = best_deconj
            output.append(_entry(
                text[i : i + cl], cm.entry, tense=cm.tense, base_form=cm.base_form,
            ))
            i += cl
        else:
            if ch not in "。、！？…・":
                output.append({
                    "surface": ch, "reading": "", "lemma": "", "pos": "", "gloss": "",
                    "tense": "", "base_form": "", "matched": False,
                })
            i += 1
    return output


def _edict_path() -> str:
    from api import dictionary

    return dictionary.path("edict")


def _conj_path() -> str:
    from api import dictionary

    return dictionary.path("conjugations")


def run(text: str) -> list[Entry]:
    index = load_index(_edict_path())
    if index is None:
        raise NeedsSetup(
            "JParser needs the EDICT2 dictionary. An admin can download it from Admin → Dictionary."
        )
    return analyze(text, index, load_rules(_conj_path()))
