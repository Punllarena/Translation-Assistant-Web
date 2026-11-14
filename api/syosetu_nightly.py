"""The nightly syosetu check (docs/superpowers/specs/2026-11-14-syosetu-nightly-design.md).

Once a day, after the admin's time, the tick queues one ``syosetu_nightly`` job per user
with an eligible series. The job reads each series' index (refreshing its date, headings
and checked-at), seeds an unset mark, and queues an ordinary ``syosetu_fetch`` for the
chapters above ``max(mark, highest series_order)``. Chapters at or below that are never
fetched here, so deleted chapters stay deleted."""

from datetime import UTC, datetime

from sqlalchemy import Select, func, select

from api import jobs, server_settings
from api.core import scrape
from api.core.syosetu_volumes import heading_sequence
from api.fetch_job import fetch_active, mark_read
from api.jobs import JobContext, handler
from api.models import Document, Series

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


def _check(ctx: JobContext, c, series: Series, delay: float) -> list[int] | None:
    """Read one series' index; the chapter numbers to fetch, or None when its mark was
    only seeded. Raises ScrapeError / ValueError when the index cannot be read."""
    index = scrape.fetch_series_index(c, series.syosetu_url, delay=delay)
    mark_read(series, index, datetime.now(UTC))
    series.syosetu_headings = heading_sequence(index)
    highest = _highest_order(ctx.db, series.id)
    nums = [ch["num"] for ch in index]
    if series.syosetu_fetched_through is None:
        series.syosetu_fetched_through = max([highest, *nums])
        return None
    floor = max(series.syosetu_fetched_through, highest)
    return sorted(n for n in nums if n > floor)


@handler("syosetu_nightly")
def nightly(ctx: JobContext) -> dict:
    user_id = ctx.job.user_id
    series_list = ctx.db.scalars(eligible_series(user_id).order_by(Series.id)).all()
    delay = server_settings.effective(ctx.db).syosetu_delay_seconds
    n = len(series_list)
    checked, busy, queued, failed = 0, 0, [], []
    with http_client() as c:
        for i, series in enumerate(series_list):
            ctx.progress(i, n, series.title)
            if fetch_active(ctx.db, user_id, series.id):
                busy += 1
                continue
            try:
                nums = _check(ctx, c, series, delay)
            except (scrape.ScrapeError, ValueError) as exc:
                message = str(exc) or type(exc).__name__
                series.syosetu_check_error = message
                failed.append({"series_id": series.id, "title": series.title, "message": message})
                continue
            checked += 1
            if nums:
                job = jobs.enqueue(ctx.db, user_id, "syosetu_fetch",
                                   {"series_id": series.id, "nums": nums}, total=len(nums))
                queued.append({"series_id": series.id, "title": series.title,
                               "chapters": len(nums), "job_id": job.id})
    ctx.progress(n, n, f"{checked} series checked, {len(queued)} with new chapters, "
                       f"{len(failed)} failed")
    return {"checked": checked, "busy": busy, "queued": queued, "failed": failed}
