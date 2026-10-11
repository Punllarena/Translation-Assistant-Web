from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from api.core.text import lines_to_db_rows, replace_and_parse, split_parse_chars
from api.deps import current_user, db_session, owned_ref, scoped
from api.library import check_line_count
from api.models import Document, GlossaryEntry, Line, Profile, Series, User
from api.routing import api_router
from api.schemas.documents import DocumentOut
from api.schemas.lines import DocumentLines, LineBatch, LineOut, SourceUpdate
from api.schemas.profiles import DEFAULT_PARSE_CHARS

router = api_router(tags=["lines"])


def editor_profile(
    db: Session, user_id: int, doc: Document, profile_id: int | None
) -> Profile | None:
    """The profile whose glossary and parse characters the editor uses: an explicit
    choice, else the series' profile, else the default, else the oldest, else none."""
    if profile_id is not None:
        return owned_ref(db, Profile, profile_id, user_id, "profile_id")
    if doc.series_id is not None:
        series = db.get(Series, doc.series_id)
        if series.profile_id is not None:
            return db.get(Profile, series.profile_id)
    return db.scalar(
        select(Profile)
        .where(Profile.user_id == user_id)
        .order_by(Profile.is_default.desc(), Profile.id)
        .limit(1)
    )


@router.get("/documents/{document_id}/lines", response_model=DocumentLines)
def get_lines(
    document_id: int,
    profile_id: int | None = Query(None),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> DocumentLines:
    doc = scoped(db, Document, document_id, user.id)
    profile = editor_profile(db, user.id, doc, profile_id)
    glossary: list[tuple[str, str]] = []
    if profile is not None:
        glossary = [
            tuple(row)
            for row in db.execute(
                select(GlossaryEntry.phrase, GlossaryEntry.translation)
                .where(GlossaryEntry.profile_id == profile.id)
                .order_by(GlossaryEntry.sort_order, GlossaryEntry.id)
            )
        ]
    parse_chars = split_parse_chars(profile.parse_chars if profile else DEFAULT_PARSE_CHARS)
    lines = []
    for line in db.scalars(
        select(Line).where(Line.document_id == doc.id).order_by(Line.line_number)
    ):
        display, sentences, replaced = replace_and_parse(line.raw_text, glossary, parse_chars)
        lines.append(
            LineOut(
                line_number=line.line_number,
                prefix=line.prefix,
                raw_text=line.raw_text,
                display_text=display,
                sentences=sentences,
                replaced=replaced,
                translated_text=line.translated_text,
            )
        )
    return DocumentLines(document=doc, profile=profile, lines=lines)


@router.patch("/documents/{document_id}/lines", status_code=status.HTTP_204_NO_CONTENT)
def save_lines(
    document_id: int,
    body: LineBatch,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> None:
    """Write the client's dirty lines in one statement. translated_at is stamped when a
    line goes from empty to translated, cleared when it is emptied, and kept on an edit,
    so the statistics heatmap counts the day a line was first translated."""
    doc = scoped(db, Document, document_id, user.id)
    edits = {edit.line_number: edit.translated_text for edit in body.lines}
    if len(edits) != len(body.lines):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "line_number: listed more than once"
        )
    current = {
        number: (line_id, old)
        for number, line_id, old in db.execute(
            select(Line.line_number, Line.id, Line.translated_text).where(
                Line.document_id == doc.id, Line.line_number.in_(edits)
            )
        )
    }
    missing = sorted(set(edits) - set(current))
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"line_number: no such line ({', '.join(map(str, missing))})",
        )
    now = datetime.now(UTC)
    rows = []
    for number, text in edits.items():
        line_id, old = current[number]
        row = {"id": line_id, "translated_text": text}
        if not text:
            row["translated_at"] = None
        elif not old:
            row["translated_at"] = now
        rows.append(row)
    # Rows differ in which columns they set, so group them: one executemany per shape.
    for keys in {tuple(sorted(r)) for r in rows}:
        db.execute(update(Line), [r for r in rows if tuple(sorted(r)) == keys])
    doc.updated_at = func.now()
    db.flush()


@router.put("/documents/{document_id}/source", response_model=DocumentOut)
def replace_source(
    document_id: int,
    body: SourceUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Document:
    """Edit Source (the desktop replace_raw_content). One text line is one line, a leading
    $ marks a continuation; lines are not re-split. Translations and translated_at stay
    attached by position, so a change in line count is refused unless forced."""
    doc = scoped(db, Document, document_id, user.id)
    if not body.text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "source text is empty")
    # The client joins its lines with "\n", so split on that alone: str.splitlines would
    # also break on \v, \x1c-\x1e, \x85, U+2028 and U+2029, and drop a trailing blank line.
    raw = body.text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    check_line_count(raw)
    rows = lines_to_db_rows(raw, [])
    existing = {
        line.line_number: line
        for line in db.scalars(select(Line).where(Line.document_id == doc.id))
    }
    if len(rows) != len(existing) and not body.force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"line count changes from {len(existing)} to {len(rows)}; translations stay "
            "attached by line position",
        )
    for row in rows:
        line = existing.pop(row["line_number"], None)
        prefix = row["prefix"] or "%"
        if line is None:
            db.add(
                Line(
                    document_id=doc.id,
                    line_number=row["line_number"],
                    prefix=prefix,
                    raw_text=row["raw_text"],
                    translated_text="",
                )
            )
        else:
            line.prefix, line.raw_text = prefix, row["raw_text"]
    for line in existing.values():
        db.delete(line)
    doc.updated_at = func.now()
    db.flush()
    return doc
