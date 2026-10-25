"""Desktop chapter 0 (the published ToC-page text) -> ``series.wp_summary``."""

import sqlite3

from api.core.tadb_schema import ImportReport, _get
from api.core.wp_summary import MAX_SUMMARY_CHARS, lines_to_summary
from api.models import Series

LIVE = ("publish", "future")


def is_summary(row: sqlite3.Row) -> bool:
    """A published chapter 0 of a named series; a chapter with no series is never one."""
    return bool(
        _get(row, "documents", "series_title", "")
        and _get(row, "documents", "series_order", 0) == 0
        and _get(row, "documents", "wp_chapter_index") == 0
        and _get(row, "documents", "wp_status", "") in LIVE
    )


class Summaries:
    """The summary documents of one import and their lines, until ``finish`` writes them."""

    def __init__(self, max_lines: int, max_chars: int) -> None:
        self.max_lines, self.max_chars = max_lines, max_chars
        self.dropped: dict[int, int] = {}  # desktop document id -> lines left out
        self.series: dict[int, Series] = {}  # desktop document id -> series
        self.lines: dict[int, list[dict]] = {}  # desktop document id -> line dicts

    def take(self, row: sqlite3.Row, series: Series) -> None:
        self.series[row["id"]] = series
        self.lines[row["id"]] = []

    def add_line(self, row: sqlite3.Row, report: ImportReport) -> bool:
        """Collect a summary document's line (True: it is a summary line, never an orphan).
        The same caps as an ordinary line: too many, too long or NUL-bearing ones are dropped."""
        doc_id = row["document_id"]
        lines = self.lines.get(doc_id)
        if lines is None:
            return False
        text = _get(row, "lines", "translated_text", "") or ""
        if len(lines) >= self.max_lines or len(text) > self.max_chars or "\x00" in text:
            report.skipped["lines"] += 1
            if doc_id not in self.dropped:  # one message per document, not one per line
                report.messages.append(
                    f"documents row {doc_id}: summary lines over {self.max_lines}, longer than "
                    f"{self.max_chars} characters or holding NUL were skipped")
            self.dropped[doc_id] = self.dropped.get(doc_id, 0) + 1
            return True
        lines.append({"prefix": _get(row, "lines", "prefix", "%") or "%", "translated_text": text})
        return True

    def finish(self, report: ImportReport) -> None:
        for desktop_id, series in sorted(self.series.items()):
            if series.wp_summary:
                report.messages.append(
                    f"documents row {desktop_id}: kept the summary already on {series.title!r}")
                continue
            text = lines_to_summary(self.lines[desktop_id])
            if len(text) > MAX_SUMMARY_CHARS:
                report.messages.append(
                    f"documents row {desktop_id}: chapter 0 is longer than {MAX_SUMMARY_CHARS} "
                    f"characters; it was not written as the summary of {series.title!r}")
                continue
            series.wp_summary = text
            series.wp_summary_pending = False
            report.messages.append(
                f"documents row {desktop_id}: chapter 0 became the summary of {series.title!r}")
