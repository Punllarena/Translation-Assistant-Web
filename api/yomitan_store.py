"""Installed Yomitan dictionaries: storage, the admin-set order, and the one-query fetch
JParser uses (spec "Upload and storage" and "Lookup"). Flushes only; the route commits."""

from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import Text, bindparam, delete, func, insert, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from api.core.yomitan_read import Parsed
from api.models import Dictionary, DictionaryTerm, ServerSetting
from api.mt.jparser import DictEntry

ORDER_KEY = "dictionary_order"
EDICT = "edict"
BATCH = 1000


def token(dictionary_id: int) -> str:
    return f"yomitan:{dictionary_id}"


@dataclass
class Installed:
    dictionary: Dictionary
    replaced_revision: str | None


def installed(db: Session) -> list[Dictionary]:
    return list(db.scalars(select(Dictionary).order_by(Dictionary.id)))


def install(db: Session, parsed: Parsed) -> Installed:
    meta = parsed.meta
    fields = {
        "title": meta.title, "revision": meta.revision, "attribution": meta.attribution,
        "author": meta.author, "url": meta.url, "entry_count": parsed.entry_count,
    }
    row = db.scalar(select(Dictionary).where(Dictionary.identity_key == meta.identity_key))
    replaced = None
    if row is None:
        row = Dictionary(identity_key=meta.identity_key, updated_at=func.now(), **fields)
        db.add(row)
    else:
        replaced = row.revision
        db.execute(delete(DictionaryTerm).where(DictionaryTerm.dictionary_id == row.id))
        for name, value in fields.items():
            setattr(row, name, value)
        row.updated_at = func.now()
    db.flush()
    rows = [
        {"dictionary_id": row.id, "key": key, "headwords": list(e.headwords),
         "reading": e.reading, "pos": sorted(e.pos), "gloss": e.gloss}
        for key, e in parsed.terms.items()
    ]
    for i in range(0, len(rows), BATCH):
        db.execute(insert(DictionaryTerm), rows[i:i + BATCH])
    db.flush()
    db.refresh(row)
    return Installed(row, replaced)


def order(db: Session) -> list[str]:
    row = db.get(ServerSetting, ORDER_KEY)
    stored = row.value if row is not None and isinstance(row.value, list) else []
    ids = [d.id for d in installed(db)]
    valid = {EDICT, *(token(i) for i in ids)}
    out: list[str] = []
    for t in stored:
        if isinstance(t, str) and t in valid and t not in out:
            out.append(t)
    out += [token(i) for i in ids if token(i) not in out]
    if EDICT not in out:
        out.insert(0, EDICT)
    return out


def set_order(db: Session, tokens: list[str], user_id: int) -> list[str]:
    current = order(db)
    if len(tokens) != len(current) or set(tokens) != set(current):
        raise ValueError("The order must list every dictionary exactly once.")
    stmt = pg_insert(ServerSetting).values(key=ORDER_KEY, value=list(tokens), updated_by=user_id)
    db.execute(stmt.on_conflict_do_update(
        index_elements=[ServerSetting.key],
        set_={"value": stmt.excluded.value, "updated_by": user_id, "updated_at": func.now()},
    ))
    db.flush()
    return list(tokens)


def remove(db: Session, dictionary_id: int) -> bool:
    gone = db.execute(delete(Dictionary).where(Dictionary.id == dictionary_id)).rowcount
    db.flush()
    return bool(gone)


def fetch(db: Session, keys: Collection[str]) -> dict[str, dict[str, DictEntry]]:
    if not keys:
        return {}
    t = DictionaryTerm
    stmt = select(t.dictionary_id, t.key, t.headwords, t.reading, t.pos, t.gloss).where(
        t.key == func.any(bindparam("keys", list(keys), type_=ARRAY(Text)))
    )
    out: dict[str, dict[str, DictEntry]] = {}
    for dict_id, key, headwords, reading, pos, gloss in db.execute(stmt):
        out.setdefault(token(dict_id), {})[key] = DictEntry(
            tuple(headwords), reading, frozenset(pos), gloss, False, bool(pos)
        )
    return out
