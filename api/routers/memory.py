from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, scoped
from api.models import Document, Line, User
from api.routing import api_router
from api.schemas.memory import TmMatch

router = api_router(tags=["memory"])

TM_LIMIT = 5  # desktop find_tm_matches


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
