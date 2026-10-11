from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select, tuple_, update
from sqlalchemy.orm import Session

from api.core import nouns
from api.core.text import needle_pattern, replace_all
from api.deps import current_user, db_session, owned_ref, scoped
from api.models import Document, GlossaryEntry, Line, Profile, Series, User
from api.routing import api_router
from api.schemas.lines import MAX_TRANSLATION_CHARS, NoNulStr
from api.schemas.memory import (
    MAX_NEEDLE_CHARS,
    FindMatch,
    FindResult,
    ReplaceRequest,
    ReplaceResult,
    Suggestions,
    SuggestRequest,
    Term,
    TmMatch,
)

router = api_router(tags=["memory"])

TM_LIMIT = 5  # desktop find_tm_matches
MAX_MATCHES = 1000

Needle = Annotated[NoNulStr, Query(min_length=1, max_length=MAX_NEEDLE_CHARS)]
Replacement = Annotated[NoNulStr, Query(max_length=MAX_NEEDLE_CHARS)]


@router.get("/tm/matches", response_model=list[TmMatch])
def tm_matches(
    document_id: int,
    line_number: int = Query(ge=0, le=2**31 - 1),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[TmMatch]:
    """The desktop find_tm_matches: earlier translations of this exact source text in the
    user's other documents, most recently updated document first (ruling 1)."""
    doc = scoped(db, Document, document_id, user.id)
    raw = db.scalar(
        select(Line.raw_text).where(Line.document_id == doc.id, Line.line_number == line_number)
    )
    if raw is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such line")
    if not raw.strip():
        return []
    rows = db.execute(
        select(Line.translated_text, Document.id, Document.title, Document.updated_at)
        .join(Document, Document.id == Line.document_id)
        .where(
            Document.user_id == user.id,
            Line.raw_text == raw,
            Line.translated_text != "",
            Line.document_id != doc.id,
        )
        .order_by(Document.updated_at.desc(), Line.id.desc())
        .limit(TM_LIMIT)
    )
    return [
        TmMatch(translated_text=t, document_id=i, document_title=title, updated_at=u)
        for t, i, title, u in rows
    ]


def _too_long(pattern, before: str, replacement: str) -> bool:
    """Cheap upper bound on the replaced length, checked before the result is built."""
    grow = max(0, len(replacement) - 1)  # a match is at least one character
    return len(before) + len(pattern.findall(before)) * grow > MAX_TRANSLATION_CHARS


@router.get("/series/{series_id}/find", response_model=FindResult)
def find_in_series(
    series_id: int,
    q: Needle,
    replace: Replacement = "",
    case_sensitive: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> FindResult:
    """The desktop find_in_series, with each match's replaced text as a preview."""
    series = scoped(db, Series, series_id, user.id)
    pattern = needle_pattern(q, case_sensitive)
    text = Line.translated_text
    # SQL narrows the rows; the pattern decides (Postgres lower() and Python's case
    # folding can disagree on rare characters).
    if case_sensitive:
        narrow = text.contains(q, autoescape=True)
    else:
        narrow = text.icontains(q, autoescape=True)
    # One row past the cap tells us whether results were cut off; the LIMIT keeps a
    # one-letter needle from loading the whole series.
    rows = db.execute(
        select(Line.document_id, Document.title, Line.line_number, text)
        .join(Document, Document.id == Line.document_id)
        .where(Document.series_id == series.id, narrow)
        .order_by(Document.series_order, Document.id, Line.line_number)
        .limit(MAX_MATCHES + 1)
    ).all()
    truncated = len(rows) > MAX_MATCHES
    matches: list[FindMatch] = []
    for doc_id, title, number, before in rows:
        if not pattern.search(before):
            continue
        if len(matches) == MAX_MATCHES:
            break
        too_long = _too_long(pattern, before, replace)
        matches.append(
            FindMatch(
                document_id=doc_id,
                title=title,
                line_number=number,
                before=before,
                after="" if too_long else replace_all(pattern, before, replace),
                too_long=too_long,
            )
        )
    return FindResult(matches=matches, truncated=truncated)


@router.post("/series/{series_id}/replace", response_model=ReplaceResult)
def replace_in_series(
    series_id: int,
    body: ReplaceRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> ReplaceResult:
    """Apply a reviewed batch in one transaction (ruling 4). A target is replaced only if
    its line still holds the text the user reviewed; anything else is skipped."""
    series = scoped(db, Series, series_id, user.id)
    pattern = needle_pattern(body.find, body.case_sensitive)
    wanted = {(t.document_id, t.line_number): t.before for t in body.targets}
    replaced, touched = 0, set()
    if wanted:
        lines = db.scalars(
            select(Line)
            .join(Document, Document.id == Line.document_id)
            .where(
                Document.series_id == series.id,
                tuple_(Line.document_id, Line.line_number).in_(list(wanted)),
            )
            .order_by(Line.id)  # one lock order across concurrent replaces: no deadlock
            .with_for_update(of=Line)
        )
        for line in lines:
            before = wanted[(line.document_id, line.line_number)]
            if line.translated_text != before or not pattern.search(before):
                continue
            if _too_long(pattern, before, body.replace):
                continue
            line.translated_text = replace_all(pattern, before, body.replace)
            if not line.translated_text:
                line.translated_at = None  # as save_lines: an emptied line is untranslated
            replaced += 1
            touched.add(line.document_id)
    if touched:
        db.execute(update(Document).where(Document.id.in_(touched)).values(updated_at=func.now()))
    db.flush()
    return ReplaceResult(replaced=replaced, skipped=len(wanted) - replaced)


MAX_TERMS = 500


@router.post("/series/{series_id}/phrase-suggestions", response_model=Suggestions)
def phrase_suggestions(
    series_id: int,
    body: SuggestRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Suggestions:
    """The desktop SeriesPhrasesDialog analysis, synchronous until phase 6 (ruling 2)."""
    series = scoped(db, Series, series_id, user.id)
    known: set[str] = set()
    if body.profile_id is not None:
        profile = owned_ref(db, Profile, body.profile_id, user.id, "profile_id")
        known = set(
            db.scalars(select(GlossaryEntry.phrase).where(GlossaryEntry.profile_id == profile.id))
        )
    raw = [
        r
        for r in db.scalars(
            select(Line.raw_text)
            .join(Document, Document.id == Line.document_id)
            .where(Document.series_id == series.id)
        )
        if r.strip()
    ]
    try:
        terms = nouns.frequent_nouns(raw, known, body.min_freq)
    except nouns.Unavailable as exc:
        return Suggestions(available=False, message=str(exc), terms=[])
    return Suggestions(available=True, terms=[Term(term=t, count=c) for t, c in terms[:MAX_TERMS]])
