"""The nightly syosetu check (docs/superpowers/specs/2026-11-14-syosetu-nightly-design.md).

Once a day, after the admin's time, the tick queues one ``syosetu_nightly`` job per user
with an eligible series. The job reads each series' index (refreshing its date, headings
and checked-at), seeds an unset mark, and queues an ordinary ``syosetu_fetch`` for the
chapters above ``max(mark, highest series_order)``. Chapters at or below that are never
fetched here, so deleted chapters stay deleted."""

import logging
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from api import jobs, server_settings
from api.core import scrape
from api.core.syosetu_volumes import heading_sequence
from api.fetch_job import fetch_active, mark_read
from api.jobs import JobContext, handler
from api.models import Document, Job, Series

log = logging.getLogger(__name__)
_warned: tuple[str, str] | None = None  # the bad (time, zone) pair already logged

http_client = scrape.client  # the seam tests replace


def eligible_series(user_id: int | None = None) -> Select:
    """Series in the nightly pass: a syosetu URL, Ongoing, not archived, not switched off."""
    stmt = select(Series).where(
        Series.syosetu_url != "", Series.status == "ongoing",
        Series.archived_at.is_(None), Series.syosetu_nightly.is_(True),
    )
    return stmt if user_id is None else stmt.where(Series.user_id == user_id)


def _highest_order(db, series_id: int) -> int:
    return db.scalar(select(func.coalesce(func.max(Document.series_order), 0))
                     .where(Document.series_id == series_id))


def _read(c, series: Series, delay: float) -> tuple[list[dict] | None, str]:
    """The series' index, or None and the message to store. Any error is that series' alone:
    one changed page must not cost every later series its pass for the day."""
    try:
        return scrape.fetch_series_index(c, series.syosetu_url, delay=delay), ""
    except (scrape.ScrapeError, ValueError) as exc:
        return None, str(exc) or type(exc).__name__
    except Exception:
        log.exception("nightly syosetu check: reading series %s failed", series.id)
        return None, "could not read the chapter list"


def _new_chapters(db, series: Series, index: list[dict]) -> list[int] | None:
    """Record the read; the chapter numbers to fetch, or None when the mark was only seeded."""
    mark_read(series, index, datetime.now(UTC))
    series.syosetu_headings = heading_sequence(index)
    highest = _highest_order(db, series.id)
    nums = [ch["num"] for ch in index]
    if series.syosetu_fetched_through is None:
        series.syosetu_fetched_through = max([highest, *nums])
        return None
    floor = max(series.syosetu_fetched_through, highest)
    return sorted(n for n in nums if n > floor)


@handler("syosetu_nightly")
def nightly(ctx: JobContext) -> dict:
    user_id = ctx.job.user_id
    ids = ctx.db.scalars(
        eligible_series(user_id).with_only_columns(Series.id).order_by(Series.id)).all()
    delay = server_settings.effective(ctx.db).syosetu_delay_seconds
    n = len(ids)
    checked, busy, queued, failed = 0, 0, [], []
    with http_client() as c:
        for i, series_id in enumerate(ids):
            ctx.progress(i, n, f"Series {i + 1} of {n}")
            # Re-read each series as it comes up: the run is minutes long, and a series
            # deleted, archived, switched off or moved to another novel meanwhile is skipped.
            series = ctx.db.scalar(
                eligible_series(user_id).where(Series.id == series_id)
                .execution_options(populate_existing=True))
            if series is None:
                continue
            if fetch_active(ctx.db, user_id, series.id):
                busy += 1
                continue
            index, message = _read(c, series, delay)
            if index is None:
                series.syosetu_check_error = message
                failed.append({"series_id": series.id, "title": series.title, "message": message})
                continue
            checked += 1
            nums = _new_chapters(ctx.db, series, index)
            if nums:
                job = jobs.enqueue(ctx.db, user_id, "syosetu_fetch",
                                   {"series_id": series.id, "nums": nums}, total=len(nums))
                queued.append({"series_id": series.id, "title": series.title,
                               "chapters": len(nums), "job_id": job.id})
    ctx.progress(n, n, f"{checked} series checked, {len(queued)} with new chapters, "
                       f"{len(failed)} failed")
    return {"checked": checked, "busy": busy, "queued": queued, "failed": failed}


def tick(db: Session, now: datetime) -> None:
    """Queue today's ``syosetu_nightly`` job for every user with an eligible series, once the
    admin's local time has passed (a job of any state for that local day counts). Commits its
    own session, a sanctioned commit outside the route boundary like the Ollama tick."""
    global _warned
    prefs = server_settings.effective(db)
    if not prefs.syosetu_nightly_enabled:
        return
    try:  # env values skip the validators
        at = server_settings.parse_hhmm(prefs.syosetu_nightly_time)
        local = now.astimezone(server_settings.zone(prefs.syosetu_nightly_tz))
    except ValueError:
        bad = (prefs.syosetu_nightly_time, prefs.syosetu_nightly_tz)
        if _warned != bad:  # once per bad pair, not every minute
            log.warning("nightly syosetu check skipped: bad time %r or zone %r", *bad)
            _warned = bad
        return
    _warned = None
    if local.time() < at:
        return
    day = local.date().isoformat()
    done = select(Job.user_id).where(
        Job.kind == "syosetu_nightly", Job.params_json["day"].astext == day)
    users = db.scalars(
        eligible_series().with_only_columns(Series.user_id).distinct()
        .where(Series.user_id.not_in(done))
    ).all()
    for user_id in users:
        jobs.enqueue(db, user_id, "syosetu_nightly", {"day": day})
    db.commit()
