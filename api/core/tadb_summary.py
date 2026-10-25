"""Desktop chapter 0 (the published ToC-page text) -> ``series.wp_summary``."""

import sqlite3

from api.core.tadb_schema import ImportReport, _get
from api.core.wp_summary import lines_to_summary
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

    def __init__(self) -> None:
        self.series: dict[int, Series] = {}  # desktop document id -> series
        self.lines: dict[int, list[dict]] = {}  # desktop document id -> line dicts

    def take(self, row: sqlite3.Row, series: Series) -> None:
        self.series[row["id"]] = series
        self.lines[row["id"]] = []

    def add_line(self, row: sqlite3.Row) -> bool:
        lines = self.lines.get(row["document_id"])
        if lines is None:
            return False
        lines.append({
            "prefix": _get(row, "lines", "prefix", "%") or "%",
            "translated_text": _get(row, "lines", "translated_text", "") or "",
        })
        return True

    def finish(self, report: ImportReport) -> None:
        for desktop_id, series in sorted(self.series.items()):
            if series.wp_summary:
                report.messages.append(
                    f"documents row {desktop_id}: kept the summary already on {series.title!r}")
                continue
            series.wp_summary = lines_to_summary(self.lines[desktop_id])
            series.wp_summary_pending = False
            report.messages.append(
                f"documents row {desktop_id}: chapter 0 became the summary of {series.title!r}")
