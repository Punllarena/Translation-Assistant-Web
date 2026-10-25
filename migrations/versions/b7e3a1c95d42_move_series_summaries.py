"""move series summaries: a published chapter 0 becomes series.wp_summary

Revision ID: b7e3a1c95d42
Revises: 6fd2c71c71da
Create Date: 2026-10-25 16:10:00.000000

Data only. The desktop kept a series' WordPress summary (the ToC page text) as a chapter with
``wp_chapter_index = 0``. A live one (``publish``/``future``) becomes the series' ``wp_summary``
(not pending: it is already on WordPress) and is deleted, with the series renumbered 1..N
(syosetu series keep their numbers). A chapter 0 that is not live loses its index and publishes
as an ordinary chapter. Live chapters whose display number no longer matches their
``wp_chapter_index`` are logged, not fixed.
"""
import logging
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision: str = 'b7e3a1c95d42'
down_revision: str | Sequence[str] | None = '6fd2c71c71da'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None



def lines_to_summary(lines: list[dict]) -> str:
    """Frozen copy of the helper at the time of this revision: `$` lines continue the
    previous paragraph; paragraphs are joined by a blank line."""
    groups: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].get("prefix") == "$":
            i += 1
            continue
        group = [lines[i]["translated_text"]]
        i += 1
        while i < len(lines) and lines[i].get("prefix") == "$":
            group.append(lines[i]["translated_text"])
            i += 1
        text = " ".join(t for t in group if t.strip())
        if text:
            groups.append(text)
    return (chr(10) * 2).join(groups)


_LIVE = "('publish', 'future')"


def move_summaries(conn: Connection) -> list[str]:
    """Move each series' live chapter 0 into ``wp_summary``; return the log lines."""
    logs: list[str] = []
    summaries = conn.execute(text(
        "SELECT d.series_id, s.title, array_agg(d.id ORDER BY d.id) "
        "FROM documents d JOIN series s ON s.id = d.series_id "
        f"WHERE d.wp_chapter_index = 0 AND d.wp_status IN {_LIVE} "
        "GROUP BY d.series_id, s.title ORDER BY d.series_id"
    )).all()
    affected = [series_id for series_id, _, _ in summaries]

    # 1. Live summary documents: the lowest id is the text; all of them go.
    for series_id, title, ids in summaries:
        lines = [dict(r._mapping) for r in conn.execute(text(
            "SELECT prefix, translated_text FROM lines WHERE document_id = :d "
            "ORDER BY line_number"), {"d": ids[0]})]
        conn.execute(text(
            "UPDATE series SET wp_summary = :t, wp_summary_pending = false WHERE id = :s"
        ), {"t": lines_to_summary(lines), "s": series_id})
        conn.execute(text("DELETE FROM documents WHERE id = ANY(:ids)"), {"ids": list(ids)})
        if len(ids) > 1:
            logs.append(
                f"series {series_id} {title!r}: {len(ids)} published chapter-0 documents "
                f"{list(ids)}; summary taken from document {ids[0]}, all deleted"
            )

    # 2. Unsent ones are ordinary chapters.
    conn.execute(text("UPDATE documents SET wp_chapter_index = NULL WHERE wp_chapter_index = 0"))

    if not affected:
        return logs

    # 3. Renumber the non-syosetu series that lost a document.
    conn.execute(text(
        "UPDATE documents d SET series_order = r.n FROM ("
        "  SELECT d2.id, row_number() OVER ("
        "    PARTITION BY d2.series_id ORDER BY d2.series_order, d2.id) AS n"
        "  FROM documents d2 JOIN series s ON s.id = d2.series_id"
        "  WHERE d2.series_id = ANY(:s) AND s.syosetu_url = ''"
        ") r WHERE d.id = r.id AND d.series_order <> r.n"
    ), {"s": affected})

    # 4. Report live chapters whose display number no longer matches their index.
    mismatches = conn.execute(text(
        "SELECT series_id, series_title, id, title, display, wp_chapter_index FROM ("
        "  SELECT d.series_id, s.title AS series_title, d.id, d.title, d.wp_chapter_index,"
        "    d.wp_status, d.is_illustrations,"
        "    CASE WHEN s.syosetu_url <> '' THEN d.series_order"
        "    ELSE d.series_order - count(*) FILTER (WHERE d.is_illustrations) OVER ("
        "      PARTITION BY d.series_id ORDER BY d.series_order, d.id"
        "      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) END AS display"
        "  FROM documents d JOIN series s ON s.id = d.series_id"
        "  WHERE d.series_id = ANY(:s)"
        ") x "
        f"WHERE NOT is_illustrations AND wp_status IN {_LIVE} "
        "AND wp_chapter_index IS NOT NULL AND display <> wp_chapter_index "
        "ORDER BY series_id, display, id"
    ), {"s": affected}).all()
    for series_id, series_title, doc_id, title, display, index in mismatches:
        logs.append(
            f"series {series_id} {series_title!r}: document {doc_id} {title!r} is chapter "
            f"{display} but was published as chapter {index}"
        )
    return logs


def upgrade() -> None:
    """Move published chapter-0 summaries onto their series. migrations/env.py configures no
    logging (and alembic's logger has a NullHandler), so the log lines get a console handler
    for the duration when the root logger has none."""
    log = logging.getLogger("alembic.runtime.migration")
    handler = None if logging.getLogger().handlers else logging.StreamHandler()
    if handler:
        log.addHandler(handler)
    try:
        for line in move_summaries(op.get_bind()):
            log.warning(line)
    finally:
        if handler:
            log.removeHandler(handler)


def downgrade() -> None:
    """No-op: the deleted chapter-0 documents are not restored, and ``wp_summary`` keeps its
    text until the previous revision drops the column."""
