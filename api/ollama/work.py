"""Which lines go to Ollama next, and saving what came back (synchronous DB layer)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import cast

from sqlalchemy import and_, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.core.text import has_letter, replace_and_parse
from api.models import Document, Line
from api.models.ollama import OllamaChunk, OllamaQueueItem, OllamaSuggestion
from api.ollama.chunks import Item, RequestStats, chunk_index, context_before, cut
from api.ollama.prefs import OllamaPrefs
from api.routers.lines import editor_context


def raw_sha(raw_text: str) -> str:
    """The only place the source hash is computed: stale checks and saves both use it."""
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_SPACE = " \t\n\r\f\v"


def _sql_sha(raw):
    """raw_sha in SQL. Python's strip() also drops Unicode spaces, so this may differ for such
    a line; it then only marks the chapter as having work, which rows_for corrects."""
    unified = func.replace(func.replace(raw, "\r\n", "\n"), "\r", "\n")
    text = func.btrim(unified, _SPACE)
    return func.encode(func.sha256(func.convert_to(text, "UTF8")), "hex")


def _with_work(db: Session, doc_ids: list[int]) -> set[int]:
    """The chapters with a non-blank line that has no translation and no current suggestion:
    one query, so a queue pass does not run rows_for (glossary and parse) over finished ones.

    An upper bound: a symbol-only line (a scene break, `has_letter` false) still counts as work
    here, because the rule is not ported to SQL (Postgres `[[:alpha:]]` depends on the locale).
    `next_plan` fills such a line with its source before reading the chapter, after which the
    query no longer sees it; a chapter with only scene breaks left is cleared without a request.
    """
    if not doc_ids:
        return set()
    suggested = exists().where(
        OllamaSuggestion.line_id == Line.id,
        OllamaSuggestion.text.is_not(None),
        OllamaSuggestion.raw_sha == _sql_sha(Line.raw_text),
    )
    return set(db.scalars(
        select(Line.document_id).distinct().where(and_(
            Line.document_id.in_(doc_ids),
            Line.translated_text == "",
            func.btrim(Line.raw_text, _SPACE) != "",
            ~suggested,
        ))
    ))


@dataclass(frozen=True)
class Row(Item):
    line_id: int = 0
    raw_sha: str = ""


@dataclass
class Plan:
    document_id: int
    series_id: int
    before: list[Row]
    chunk: list[Row]

    @property
    def asked(self) -> list[Row]:
        return [r for r in self.chunk if r.known is None]


def rows_for(db: Session, user_id: int, doc: Document) -> list[Row]:
    """Every line in order; `known` is the translation, else a suggestion matching the source.
    A symbol-only line with neither is known as its own source: a scene break is never asked."""
    glossary, parse_chars = editor_context(db, user_id, doc)  # once per document
    lines = db.execute(
        select(Line, OllamaSuggestion.text, OllamaSuggestion.raw_sha)
        .outerjoin(OllamaSuggestion, OllamaSuggestion.line_id == Line.id)
        .where(Line.document_id == doc.id)
        .order_by(Line.line_number)
    )
    rows = []
    for line, sug_text, sug_sha in lines:
        sha = raw_sha(line.raw_text)
        known = None
        if line.translated_text:
            known = line.translated_text
        elif line.raw_text.strip() and not has_letter(line.raw_text):
            known = line.raw_text.strip()  # a scene break stands for itself
        elif sug_text is not None and sug_sha == sha:
            known = sug_text
        text = replace_and_parse(line.raw_text, glossary, parse_chars)[0].strip()
        rows.append(Row(line.line_number, line.prefix, text, known, line.id, sha))
    return rows


def fill_symbol_lines(db: Session, doc: Document) -> int:
    """Copy the source into the translation of the chapter's untranslated symbol-only lines
    (scene breaks), which Ollama never asks about, in one UPDATE. A line that already has a
    translation is left alone, and `translated_at` stays NULL: a copy is not a day's work.
    Flushes only: the caller owns the transaction. Returns how many lines were filled."""
    rows = db.execute(
        select(Line.id, Line.raw_text).where(
            Line.document_id == doc.id, Line.translated_text == ""
        )
    ).all()
    values = [
        {"id": line_id, "translated_text": raw.strip()}
        for line_id, raw in rows
        if raw.strip() and not has_letter(raw)
    ]
    if not values:
        return 0
    db.execute(update(Line), values)
    db.flush()
    return len(values)


def _documents(db: Session, user_id: int, item: OllamaQueueItem) -> list[Document]:
    """The item's chapters in reading order; illustrations chapters carry no text."""
    q = select(Document).where(Document.user_id == user_id, Document.is_illustrations.is_(False))
    if item.kind == "series":
        q = q.where(Document.series_id == item.series_id)
    elif item.kind == "volume":
        q = q.where(Document.volume_id == item.volume_id)
    else:
        docs = {d.id: d for d in db.scalars(q.where(Document.id.in_(item.document_ids or [])))}
        return [docs[i] for i in item.document_ids if i in docs]
    return list(db.scalars(q.order_by(Document.series_order, Document.id)))


def _plan(doc: Document, rows: list[Row], chunk: list[Row], p: OllamaPrefs) -> Plan:
    before = context_before(rows, chunk[0].line_number, p.context_lines)
    return Plan(doc.id, doc.series_id, cast(list[Row], before), chunk)


def next_plan(
    db: Session, user_id: int, p: OllamaPrefs, skip: frozenset[int] = frozenset()
) -> Plan | None:
    """The first chunk with a line to ask. Lines in `skip` (line ids that already failed in this
    run) do not make a chunk worth asking, and keep their item queued for the next run."""
    items = db.scalars(
        select(OllamaQueueItem)
        .where(OllamaQueueItem.user_id == user_id)
        .order_by(OllamaQueueItem.position, OllamaQueueItem.id)
    ).all()
    for item in items:
        skipped = False
        docs = _documents(db, user_id, item)
        pending = _with_work(db, [d.id for d in docs])
        for doc in docs:
            if doc.id not in pending:
                continue
            fill_symbol_lines(db, doc)  # scene breaks are answered here, not by the model
            rows = rows_for(db, user_id, doc)
            for chunk in cut(rows, p.chunk_lines):
                todo = [r for r in cast(list[Row], chunk) if r.known is None]
                if any(r.line_id not in skip for r in todo):
                    return _plan(doc, rows, cast(list[Row], chunk), p)
                skipped = skipped or bool(todo)
        if item.kind != "series" and not skipped:  # a series item stays: its chapters may grow
            db.delete(item)
    db.flush()
    return None


class SymbolOnly(ValueError):
    """A symbol-only line (a scene break): it has nothing to translate, and Ollama never asks
    it. The by-hand route reports the message instead of asking the model."""


def plan_for_line(
    db: Session, user_id: int, doc: Document, line_number: int, p: OllamaPrefs, *, reroll: bool
) -> Plan:
    """The chunk holding the line; the line is always asked, reroll asks all untranslated."""
    raw = db.scalar(
        select(Line.raw_text).where(
            Line.document_id == doc.id, Line.line_number == line_number
        )
    )
    if raw is not None and raw.strip() and not has_letter(raw):
        raise SymbolOnly(f"line {line_number} has nothing to translate")
    rows = rows_for(db, user_id, doc)
    chunks = cut(rows, p.chunk_lines)
    n = chunk_index(chunks, line_number)
    if n is None:
        raise ValueError(f"line {line_number} has no text to translate")
    translated = set(
        db.scalars(
            select(Line.id).where(Line.document_id == doc.id, Line.translated_text != "")
        )
    )
    chunk = [
        replace(r, known=None)
        if r.line_number == line_number or (reroll and r.line_id not in translated)
        else r
        for r in cast(list[Row], chunks[n])
    ]
    return _plan(doc, rows, chunk, p)


def save(
    db: Session,
    user_id: int,
    plan: Plan,
    requests: list[RequestStats],
    lines: dict[int, str],
    *,
    source: str,
    job_id: int | None,
    p: OllamaPrefs,
    model: str,
) -> list[int]:
    """Record every request and keep one suggestion per answered line; the new chunk row ids.
    Lines translated or edited since the plan are skipped. Flushes only: the caller owns the
    transaction."""
    chunk_ids: list[int] = []
    answered_by: dict[int, int] = {}  # line number -> chunk row of the last ok request covering it
    for r in requests:
        chunk = OllamaChunk(
            user_id=user_id, series_id=plan.series_id, document_id=plan.document_id, job_id=job_id,
            source=source, ok=r.ok, clamped=r.clamped, depth=r.depth, model=model,
            preset=p.preset, chunk_lines=p.chunk_lines, context_lines=p.context_lines,
            first_line=r.first_line, last_line=r.last_line, asked=r.asked,
            prompt_tokens=r.prompt_tokens or 0, output_tokens=r.output_tokens or 0,
            prompt_ms=r.prompt_ms, eval_ms=r.eval_ms, load_ms=r.load_ms, total_ms=r.total_ms,
            first_token_ms=r.first_token_ms, reasoning=r.reasoning or None,
            error=r.error or None, prompt=r.prompt,
        )
        db.add(chunk)
        db.flush()
        chunk_ids.append(chunk.id)
        if r.ok:
            for n in lines:
                if r.first_line <= n <= r.last_line:
                    answered_by[n] = chunk.id
    planned = {r.line_number: r for r in plan.chunk}
    current = {
        ln.line_number: ln
        for ln in db.scalars(
            select(Line)
            .join(Document, Document.id == Line.document_id)
            .where(Line.document_id == plan.document_id, Document.user_id == user_id)
        )
    }
    values = []
    for n, text in lines.items():
        row, line = planned.get(n), current.get(n)
        if row is None or line is None or n not in answered_by:
            continue
        if line.translated_text or raw_sha(line.raw_text) != row.raw_sha:
            continue
        values.append(
            {"line_id": line.id, "chunk_id": answered_by[n], "text": text, "raw_sha": row.raw_sha}
        )
    if not values:
        return chunk_ids
    stmt = insert(OllamaSuggestion).values(values)
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=[OllamaSuggestion.line_id],
            set_={
                "chunk_id": stmt.excluded.chunk_id,
                "text": stmt.excluded.text,
                "raw_sha": stmt.excluded.raw_sha,
                "scored": False,
            },
        )
    )
    db.flush()
    return chunk_ids


def lines_left(db: Session, user_id: int, item: OllamaQueueItem) -> int:
    """Non-blank lines in the item's chapters with no translation and no current suggestion.
    Symbol-only lines are not counted: they are filled with their source, never asked."""
    ids = [d.id for d in _documents(db, user_id, item)]
    if not ids:
        return 0
    n = 0
    rows = db.execute(
        select(Line.raw_text, OllamaSuggestion.text, OllamaSuggestion.raw_sha)
        .outerjoin(OllamaSuggestion, OllamaSuggestion.line_id == Line.id)
        .where(Line.document_id.in_(ids), Line.translated_text == "")
    )
    for raw, sug_text, sug_sha in rows:
        if not raw.strip() or not has_letter(raw):
            continue
        if sug_text is not None and sug_sha == raw_sha(raw):
            continue
        n += 1
    return n
