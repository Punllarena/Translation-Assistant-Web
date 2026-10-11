from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select, tuple_, update
from sqlalchemy.orm import Session

from api.core.text import needle_pattern, replace_all
from api.deps import current_user, db_session, scoped
from api.models import Document, Line, Series, User
from api.routing import api_router
from api.schemas.lines import NoNulStr
from api.schemas.memory import (
    MAX_NEEDLE_CHARS,
    FindMatch,
    FindResult,
    ReplaceRequest,
    ReplaceResult,
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
    rows = db.execute(
        select(Line.document_id, Document.title, Line.line_number, text)
        .join(Document, Document.id == Line.document_id)
        .where(Document.series_id == series.id, narrow)
        .order_by(Document.series_order, Document.id, Line.line_number)
    )
    matches: list[FindMatch] = []
    for doc_id, title, number, before in rows:
        if not pattern.search(before):
            continue
        if len(matches) == MAX_MATCHES:
            return FindResult(matches=matches, truncated=True)
        matches.append(
            FindMatch(
                document_id=doc_id,
                title=title,
                line_number=number,
                before=before,
                after=replace_all(pattern, before, replace),
            )
        )
    return FindResult(matches=matches, truncated=False)


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
            .with_for_update(of=Line)
        )
        for line in lines:
            before = wanted[(line.document_id, line.line_number)]
            if line.translated_text != before or not pattern.search(before):
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
