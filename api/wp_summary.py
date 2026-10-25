"""Sending a series' WordPress summary (desktop chapter 0, the ToC page text) as chapter
index 0, just before the next chapter of that series is published."""

import logging

import httpx

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
    try:
        wp_http.publish(c, endpoint, wp.build_payload(
            doc_meta={"series_title": series.title, "series_order": 0,
                      "chapter_title": "Summary", "volume_title": ""},
            series_meta=publish.series_meta(series), lines=summary_lines(series.wp_summary),
            api_key=key, attribution=False))
    except WPPublishError as exc:
        series.wp_summary_error = exc.message
    except Exception:
        log.exception("sending the summary of series %s failed", series.id)
        series.wp_summary_error = "sending the series summary failed"
    else:
        series.wp_summary_pending, series.wp_summary_error = False, ""
