"""The syosetu series fetch job (desktop SeriesFetchWorker + FetchSeriesDialog).

Takes chapter numbers, never URLs (plan ruling 8): the index is re-read from the
series' own syosetu_url. Chapters already in the series are skipped, so a rerun
resumes an interrupted fetch (ruling 10). A chapter under a syosetu chapter-title
heading goes into the volume made from that heading (VolumeSyosetuGroup), created on
first sight; chapters already in the series are never moved."""

from sqlalchemy import select

from api import server_settings
from api.core import scrape
from api.core.syosetu_volumes import heading_sequence, targets
from api.core.text import build_new_file, lines_to_db_rows, parse_file_content
from api.jobs import JobContext, JobError, handler
from api.library import check_line_count, write_lines
from api.models import Document, Job, Series, Volume, VolumeSyosetuGroup
from api.volume_order import place as place_volume

http_client = scrape.client  # the seam tests replace


def existing_orders(db, series_id: int) -> set[int]:
    return set(db.scalars(select(Document.series_order).where(Document.series_id == series_id)))


FETCH_BUSY = "a fetch for this series is already queued or running"


def fetch_active(db, user_id: int, series_id: int) -> bool:
    """A syosetu_fetch job for the series is queued or running: regrouping or merging
    now could move or delete a volume under it."""
    return db.scalar(select(Job.id).where(
        Job.user_id == user_id, Job.kind == "syosetu_fetch",
        Job.state.in_(("queued", "running")),
        Job.params_json["series_id"].as_integer() == series_id,
    ).limit(1)) is not None


def group_volume(db, series_id: int, heading: str) -> Volume:
    """The volume holding ``heading``'s chapters: matched by the hidden key, so renaming
    it is safe; otherwise a new unkinded, unnumbered volume placed after the last unkinded
    one (else at the end), with the heading as its subtitle (suffixed while that is taken)."""
    volume = db.scalar(select(Volume).join(
        VolumeSyosetuGroup, VolumeSyosetuGroup.volume_id == Volume.id).where(
        VolumeSyosetuGroup.series_id == series_id, VolumeSyosetuGroup.heading == heading))
    if volume is not None:
        return volume
    taken = set(db.scalars(select(Volume.subtitle).where(
        Volume.series_id == series_id, Volume.kind == "", Volume.volume_index.is_(None))))
    subtitle, n = heading, 2
    while subtitle in taken:
        subtitle, n = f"{heading} ({n})", n + 1
    volume = Volume(series_id=series_id, kind="", subtitle=subtitle, volume_order=0)
    db.add(volume)
    db.flush()
    place_volume(db, volume)
    db.add(VolumeSyosetuGroup(series_id=series_id, volume_id=volume.id, heading=heading))
    db.flush()
    return volume


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
            full = scrape.fetch_series_index(c, series.syosetu_url)
        except (ValueError, scrape.ScrapeError) as exc:
            raise JobError(f"could not read the chapter list: {exc}") from exc
        index = [ch for ch in full if ch["num"] in wanted]
        series.syosetu_headings = heading_sequence(full)
        place = targets(series.syosetu_headings, wanted,
                        series.syosetu_volume_mode, series.syosetu_volume_marker)
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
                    heading = place[ch["num"]]
                    volume = heading and group_volume(ctx.db, series.id, heading)
                    doc = Document(
                        user_id=series.user_id, series_id=series.id, title=title or ch["title"],
                        chapter_title=title or ch["title"], series_order=ch["num"],
                        source_url=ch["url"], volume_id=volume.id if volume else None,
                    )
                    ctx.db.add(doc)
                    ctx.db.flush()
                    write_lines(ctx.db, doc.id, lines_to_db_rows(raw, translated))
                    added += 1
            ctx.progress(i, len(index), f"Chapter {ch['num']}")
    missing = sorted(wanted - {ch["num"] for ch in index})
    return {"added": added, "skipped": skipped, "errors": errors, "missing": missing}
