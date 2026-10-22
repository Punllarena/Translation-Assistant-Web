from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from api.core.text import DEFAULT_PARSE_CHARS, replace_and_parse, split_parse_chars
from api.deps import current_user, db_session, scoped
from api.library import replace_raw_lines
from api.models import Document, GlossaryEntry, Line, User, UserSetting
from api.routing import api_router
from api.schemas.documents import DocumentOut
from api.schemas.lines import DocumentLines, LineBatch, LineOut, SaveResult, SourceUpdate

router = api_router(tags=["lines"])


def user_parse_chars(db: Session, user_id: int) -> str:
    """The user's `parse_chars` setting; unset or not a string means the default.
    An empty string is a real choice: don't split."""
    value = db.scalar(
        select(UserSetting.value_json).where(
            UserSetting.user_id == user_id, UserSetting.key == "parse_chars"
        )
    )
    return value if isinstance(value, str) else DEFAULT_PARSE_CHARS


def editor_context(
    db: Session, user_id: int, doc: Document
) -> tuple[list[tuple[str, str]], list[str]]:
    """The chapter's series glossary (in apply order) and the user's parse characters."""
    glossary = [
        tuple(row)
        for row in db.execute(
            select(GlossaryEntry.phrase, GlossaryEntry.translation)
            .where(GlossaryEntry.series_id == doc.series_id)
            .order_by(GlossaryEntry.sort_order, GlossaryEntry.id)
        )
    ]
    return glossary, split_parse_chars(user_parse_chars(db, user_id))


def display_line(db: Session, user_id: int, doc: Document, line: Line) -> str:
    """One line as the editor displays it (glossary applied, % and $ stripped), trimmed:
    the text machine translation is asked for (desktop source_sentence_changed)."""
    glossary, parse_chars = editor_context(db, user_id, doc)
    return replace_and_parse(line.raw_text, glossary, parse_chars)[0].strip()


@router.get("/documents/{document_id}/lines", response_model=DocumentLines)
def get_lines(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> DocumentLines:
    doc = scoped(db, Document, document_id, user.id)
    glossary, parse_chars = editor_context(db, user.id, doc)
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
    return DocumentLines(document=doc, lines=lines)


@router.patch("/documents/{document_id}/lines", response_model=SaveResult)
def save_lines(
    document_id: int,
    body: LineBatch,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> SaveResult:
    """Write the client's dirty lines in one statement. translated_at is stamped when a
    line goes from empty to translated, cleared when it is emptied, and kept on an edit,
    so the statistics heatmap counts the day a line was first translated. Unknown lines are
    reported, not fatal, so one stale line cannot block the rest."""
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
    now = datetime.now(UTC)
    rows = []
    for number, text in edits.items():
        if number not in current:
            continue
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
    if rows:
        doc.updated_at = func.now()
    db.flush()
    return SaveResult(missing=missing)


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
    replace_raw_lines(db, doc, raw, body.force)
    return doc
