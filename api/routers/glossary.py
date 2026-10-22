from fastapi import Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.core.text import load_glossary
from api.deps import current_user, db_session, scoped
from api.models import GlossaryEntry, Series, User
from api.routing import api_router
from api.schemas.glossary import (
    MAX_GLOSSARY_ENTRIES,
    MAX_PHRASE_CHARS,
    GlossaryIn,
    GlossaryList,
    GlossaryOut,
    ImportResult,
    underscored,
)
from api.uploads import read_capped

router = api_router(prefix="/series/{series_id}/glossary", tags=["glossary"])

MAX_CSV_BYTES = 1 << 20  # a glossary CSV is a few KB; 1 MiB is generous


def _entries(db: Session, series_id: int) -> list[GlossaryEntry]:
    return list(
        db.scalars(
            select(GlossaryEntry)
            .where(GlossaryEntry.series_id == series_id)
            .order_by(GlossaryEntry.sort_order, GlossaryEntry.id)
        )
    )


def _upsert(db: Session, series_id: int, pairs: dict[str, str]) -> int:
    """Insert new phrases at the end and update existing ones in place (ruling 5).
    Returns how many were new."""
    existing = set(
        db.scalars(
            select(GlossaryEntry.phrase).where(
                GlossaryEntry.series_id == series_id, GlossaryEntry.phrase.in_(pairs)
            )
        )
    )
    start = db.scalar(
        select(func.coalesce(func.max(GlossaryEntry.sort_order), -1)).where(
            GlossaryEntry.series_id == series_id
        )
    ) + 1
    stmt = insert(GlossaryEntry).values(
        [
            {"series_id": series_id, "phrase": p, "translation": t, "sort_order": start + i}
            for i, (p, t) in enumerate(pairs.items())
        ]
    )
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["series_id", "phrase"],
            set_={"translation": stmt.excluded.translation},
        )
    )
    return len(pairs) - len(existing)


@router.get("", response_model=list[GlossaryOut])
def list_glossary(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[GlossaryEntry]:
    return _entries(db, scoped(db, Series, series_id, user.id).id)


@router.put("", response_model=list[GlossaryOut])
def replace_glossary(
    series_id: int,
    body: GlossaryList,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[GlossaryEntry]:
    """The desktop set_glossary: the whole list, in order (edit, delete and reorder)."""
    series = scoped(db, Series, series_id, user.id)
    db.execute(delete(GlossaryEntry).where(GlossaryEntry.series_id == series.id))
    db.add_all(
        GlossaryEntry(
            series_id=series.id, phrase=e.phrase, translation=e.translation, sort_order=i
        )
        for i, e in enumerate(body.entries)
    )
    db.flush()
    return _entries(db, series.id)


@router.post("", response_model=GlossaryOut)
def add_phrase(
    series_id: int,
    body: GlossaryIn,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> GlossaryEntry:
    series = scoped(db, Series, series_id, user.id)
    _upsert(db, series.id, {body.phrase: body.translation})
    return db.scalar(
        select(GlossaryEntry).where(
            GlossaryEntry.series_id == series.id, GlossaryEntry.phrase == body.phrase
        )
    )


def import_pairs(db: Session, series_id: int, text: str) -> ImportResult:
    """Upsert the glossary CSV ``text`` into the series (shared with the batch TXT import)."""
    pairs: dict[str, str] = {}  # a phrase repeated in the file: the last row wins
    skipped = 0
    for phrase, translation in load_glossary(text):
        bad = not phrase or "\x00" in phrase or "\x00" in translation
        if bad or len(phrase) > MAX_PHRASE_CHARS or len(translation) > MAX_PHRASE_CHARS:
            skipped += 1
            continue
        pairs[phrase] = underscored(translation)
    if len(pairs) > MAX_GLOSSARY_ENTRIES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"the file holds more than {MAX_GLOSSARY_ENTRIES} phrases",
        )
    added = _upsert(db, series_id, pairs) if pairs else 0
    db.flush()
    return ImportResult(added=added, updated=len(pairs) - added, skipped=skipped)


@router.post("/import", response_model=ImportResult)
def import_csv(
    series_id: int,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> ImportResult:
    series = scoped(db, Series, series_id, user.id)
    try:
        text = read_capped(file, MAX_CSV_BYTES).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "the file is not UTF-8") from exc
    return import_pairs(db, series.id, text)
