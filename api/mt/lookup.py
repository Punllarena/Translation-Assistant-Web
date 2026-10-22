"""Layered dictionary lookup for JParser and MeCab: EDICT2 plus the admin's Yomitan
dictionaries, in the admin's order (first layer that has a key wins)."""

from collections.abc import Iterator, Mapping

from api import yomitan_store
from api.db import SessionLocal
from api.mt.jparser import DeconjRule, DictEntry

session = SessionLocal  # seam: tests swap it for a context manager yielding their session


def edict_path() -> str:
    from api import dictionary

    return dictionary.path("edict")


def conj_path() -> str:
    from api import dictionary

    return dictionary.path("conjugations")


class Lookup(Mapping[str, DictEntry]):
    def __init__(self, layers: list[Mapping[str, DictEntry]]) -> None:
        self.layers = layers

    def __getitem__(self, key: str) -> DictEntry:
        for layer in self.layers:
            entry = layer.get(key)
            if entry is not None:
                return entry
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        seen: set[str] = set()
        for layer in self.layers:
            for key in layer:
                if key not in seen:
                    seen.add(key)
                    yield key

    def __bool__(self) -> bool:
        return bool(self.layers)  # cheap: Mapping's default would call __len__

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def all(self, key: str) -> list[DictEntry]:
        out = []
        for layer in self.layers:
            entry = layer.get(key)
            if entry is not None:
                out.append(entry)
        return out


def candidate_keys(text: str, rules: list[DeconjRule], max_len: int = 12) -> set[str]:
    pairs = {(r.suffix, r.base_suffix) for r in rules if r.suffix}
    keys: set[str] = set()
    for i in range(len(text)):
        for j in range(i + 1, min(len(text), i + max_len) + 1):
            sub = text[i:j]
            if any(c.isspace() for c in sub):
                break  # every longer substring from i contains it too
            keys.add(sub)
            if len(sub) >= 2:  # analyze() only deconjugates tokens of 2+ characters
                for suffix, base_suffix in pairs:
                    if sub.endswith(suffix):
                        keys.add(sub[: len(sub) - len(suffix)] + base_suffix)
    keys.discard("")
    return keys


def layered(keys: set[str], edict: Mapping[str, DictEntry] | None) -> Lookup | None:
    with session() as db:
        order = yomitan_store.order(db)
        fetched = yomitan_store.fetch(db, keys) if len(order) > 1 else {}
    if edict is None and len(order) <= 1:
        return None
    layers: list[Mapping[str, DictEntry]] = []
    for tok in order:
        if tok == yomitan_store.EDICT:
            if edict is not None:
                layers.append(edict)
        else:
            layers.append(fetched.get(tok, {}))
    return Lookup(layers)
