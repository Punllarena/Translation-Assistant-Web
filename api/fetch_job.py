"""The syosetu series fetch job (desktop SeriesFetchWorker + FetchSeriesDialog).

Takes chapter numbers, never URLs (plan ruling 8): the index is re-read from the
series' own syosetu_url. Chapters already in the series are skipped, so a rerun
resumes an interrupted fetch (ruling 10)."""

from sqlalchemy import select

from api import server_settings
from api.core import scrape
from api.core.text import build_new_file, lines_to_db_rows, parse_file_content
from api.jobs import JobContext, JobError, handler
from api.library import check_line_count, write_lines
from api.models import Document, Series

http_client = scrape.client  # the seam tests replace


def existing_orders(db, series_id: int) -> set[int]:
    return set(db.scalars(select(Document.series_order).where(Document.series_id == series_id)))


@handler("syosetu_fetch")
def fetch_series(ctx: JobContext) -> dict:
    series = ctx.db.get(Series, ctx.params["series_id"])
    if series is None or series.user_id != ctx.job.user_id:
        raise JobError("the series no longer exists")
    wanted = set(ctx.params["nums"])
    delay = server_settings.effective(ctx.db).syosetu_delay_seconds
    ctx.progress(0, len(wanted), "Reading the chapter list")
    added, skipped, errors = 0, 0, []
    with http_client() as c:
        try:
            index = [ch for ch in scrape.fetch_series_index(c, series.syosetu_url)
                     if ch["num"] in wanted]
        except (ValueError, scrape.ScrapeError) as exc:
            raise JobError(f"could not read the chapter list: {exc}") from exc
        have = existing_orders(ctx.db, series.id)
        for i, ch in enumerate(index, start=1):
            if ch["num"] in have:
                skipped += 1
            else:
                try:
                    title, content = scrape.fetch_syosetu(c, ch["url"], delay=delay)
                    raw, translated, _ = parse_file_content(build_new_file(content))
                    check_line_count(raw)
                except Exception as exc:  # one bad chapter must not stop the rest
                    message = getattr(exc, "detail", None) or str(exc) or type(exc).__name__
                    errors.append({"num": ch["num"], "message": str(message)})
                else:
                    doc = Document(
                        user_id=series.user_id, series_id=series.id, title=title or ch["title"],
                        chapter_title=title or ch["title"], series_order=ch["num"],
                        source_url=ch["url"],
                    )
                    ctx.db.add(doc)
                    ctx.db.flush()
                    write_lines(ctx.db, doc.id, lines_to_db_rows(raw, translated))
                    added += 1
            ctx.progress(i, len(index), f"Chapter {ch['num']}")
    missing = sorted(wanted - {ch["num"] for ch in index})
    return {"added": added, "skipped": skipped, "errors": errors, "missing": missing}
