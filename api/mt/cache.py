"""mt_cache (spec §8): results keyed by backend, language pair and the source's SHA-256,
so revisiting a line costs nothing. First write wins."""

import hashlib

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.models import MtCache


def key_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get(db: Session, backend: str, src: str, dst: str, text: str) -> str | None:
    return db.scalar(
        select(MtCache.result_text).where(
            MtCache.backend == backend,
            MtCache.source_lang == src,
            MtCache.target_lang == dst,
            MtCache.source_sha256 == key_text(text),
        )
    )


def put(db: Session, backend: str, src: str, dst: str, text: str, result: str) -> None:
    db.execute(
        insert(MtCache)
        .values(backend=backend, source_lang=src, target_lang=dst,
                source_sha256=key_text(text), result_text=result)
        .on_conflict_do_nothing()
    )
