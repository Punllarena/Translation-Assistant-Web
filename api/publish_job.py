"""The WordPress jobs (spec §9, §10): batch publish/schedule (desktop _BatchPublishWorker)
and volume illustrations (desktop _IllustrationsPublishWorker). Each re-reads the user's
config, so a credential change between enqueue and run is honoured."""

import logging
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from api import publish, wp_prefs
from api.core import wp, wp_http
from api.core.wp import WPPublishError
from api.jobs import JobContext, JobError, handler
from api.models import Document, Volume
from api.wp_prefs import WpPrefs

log = logging.getLogger(__name__)
http_client = wp_http.client  # the seam tests replace


def _config(ctx: JobContext) -> tuple[str, str]:
    try:
        return publish.wp_config(ctx.db, ctx.job.user_id)
    except publish.NotReady as exc:
        raise JobError(str(exc)) from exc


def _publish_one(db: Session, c: httpx.Client, user_id: int, item: dict, endpoint: str,
                 key: str, prefs: WpPrefs, confirm: bool) -> dict:
    doc = db.get(Document, item["document_id"])
    if doc is None or doc.user_id != user_id:
        return {"document_id": item["document_id"], "ok": False,
                "error": "the chapter no longer exists"}
    scheduled = datetime.fromisoformat(item["scheduled_for"]) if item["scheduled_for"] else None
    row = {"document_id": doc.id, "title": doc.title, "series_order": doc.series_order,
           "scheduled_for": item["scheduled_for"]}
    try:
        if doc.wp_status in publish.LIVE and not confirm:  # ruling 6
            raise publish.NotReady(
                "already published or scheduled; tick Overwrite to publish it again")
        ch = publish.build_chapter(db, doc, prefs)
        result = wp_http.publish(c, endpoint, publish.payload(
            ch, key, scheduled=scheduled, attribution=prefs.wp_attribution_enabled))
    except (publish.NotReady, WPPublishError) as exc:
        return {**row, "ok": False, "error": str(exc)}
    except Exception:  # one bad chapter must not stop the rest
        log.exception("publishing document %s failed", doc.id)
        return {**row, "ok": False, "error": "publishing this chapter failed"}
    written = publish.record(doc, result, scheduled)
    return {**row, "ok": True, "created": bool(result.get("created")),
            "post_url": str(result.get("post_url") or ""),
            "password": ch.password if written else None,
            "unlock_chapter_index": ch.unlock_chapter_index if written else None}


@handler("wp_publish")
def publish_batch(ctx: JobContext) -> dict:
    endpoint, key = _config(ctx)
    prefs = wp_prefs.load(ctx.db, ctx.job.user_id)
    items = ctx.params["chapters"]
    rows: list[dict] = []
    ctx.progress(0, len(items), "Starting")
    with http_client() as c:
        for i, item in enumerate(items, start=1):
            rows.append(_publish_one(ctx.db, c, ctx.job.user_id, item, endpoint, key, prefs,
                                     ctx.params["confirm_republish"]))
            ctx.job.result_json = {"chapters": list(rows)}  # durable with the progress commit
            ctx.progress(i, len(items), f"Chapter {i} of {len(items)}")
    return {"chapters": rows}


@handler("wp_illustrations")
def publish_illustrations(ctx: JobContext) -> dict:
    volume = ctx.db.get(Volume, ctx.params["volume_id"])
    series = volume.series if volume is not None else None
    if series is None or series.user_id != ctx.job.user_id:
        raise JobError("the volume no longer exists")
    endpoint, key = _config(ctx)
    try:
        publish.check_series(series)
    except publish.NotReady as exc:
        raise JobError(str(exc)) from exc
    inline, cover = publish.volume_images(ctx.db, volume.id)
    if not inline and cover is None:
        raise JobError("This volume has no illustrations to publish.")
    payloads = wp.build_illustrations_payloads(
        {"series_title": series.title, "volume_title": volume.wp_name},
        publish.series_meta(series), inline, api_key=key, cover=cover)
    ctx.progress(0, len(payloads), "Uploading")
    first: dict | None = None
    with http_client() as c:
        for i, p in enumerate(payloads, start=1):
            try:
                result = wp_http.publish_illustrations(c, endpoint, p)
            except WPPublishError as exc:
                raise JobError(f"batch {i}/{len(payloads)}: {exc.message}") from exc
            first = first or result  # the desktop reports the first ("replace") answer
            ctx.progress(i, len(payloads), f"Batch {i} of {len(payloads)}")
    return {"page_url": str(first.get("page_url") or ""), "created": bool(first.get("created")),
            "batches": len(payloads), "images": len(inline) + (cover is not None)}
