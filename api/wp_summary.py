"""Sending a series' WordPress summary (desktop chapter 0, the ToC page text) as chapter
index 0, just before the next chapter of that series is published."""

import logging

import httpx
from sqlalchemy import update
from sqlalchemy.orm import object_session

from api import publish
from api.core import wp, wp_http
from api.core.wp import WPPublishError
from api.core.wp_summary import summary_lines
from api.models import Series

log = logging.getLogger(__name__)


def send(c: httpx.Client, series: Series, endpoint: str, key: str) -> None:
    """Post the pending summary; never raises. A failure leaves it pending, with the reason."""
    if not (series.wp_summary_pending and series.wp_summary.strip()):
        return
    if not (series.wp_series_slug and series.wp_series_title_short):
        return  # the chapter's own check_series reports this; nothing to send to yet
    sent = series.wp_summary
    try:
        wp_http.publish(c, endpoint, wp.build_payload(
            doc_meta={"series_title": series.title, "series_order": 0,
                      "chapter_title": "Summary", "volume_title": ""},
            series_meta=publish.series_meta(series), lines=summary_lines(sent),
            api_key=key, attribution=False))
    except WPPublishError as exc:
        log.warning("summary of series %s: %s", series.id, exc.message)
        series.wp_summary_error = exc.message
    except Exception:
        log.exception("sending the summary of series %s failed", series.id)
        series.wp_summary_error = "sending the series summary failed"
    else:
        # Only if the text is still what went out: an edit made meanwhile stays pending.
        db = object_session(series)
        if db is None:
            series.wp_summary_pending, series.wp_summary_error = False, ""
            return
        db.flush()
        db.execute(update(Series).where(Series.id == series.id, Series.wp_summary == sent)
                   .values(wp_summary_pending=False, wp_summary_error=""))
        db.refresh(series)
