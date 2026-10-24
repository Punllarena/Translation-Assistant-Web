"""The WordPress jobs (spec §9, §10): batch publish/schedule (desktop _BatchPublishWorker)
and the Illustrations chapter's upload (desktop _IllustrationsPublishWorker). Each re-reads
the user's config, so a credential change between enqueue and run is honoured."""

import logging
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from api import illustrations, publish, wp_prefs
from api.core import wp_http
from api.core.wp import WPPublishError
from api.jobs import JobContext, JobError, handler
from api.library import chapter_number
from api.models import Document
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
    row = {"document_id": doc.id, "title": doc.title,
           "chapter_number": chapter_number(db, doc), "illustrations": doc.is_illustrations,
           "scheduled_for": item["scheduled_for"]}
    try:
        if doc.wp_status in publish.LIVE and not confirm:  # ruling 6
            raise publish.NotReady(
                "already published or scheduled; tick Overwrite to publish it again")
        if doc.is_illustrations:  # no schedule slot: the endpoint takes no date
            out = illustrations.upload(db, c, doc, endpoint, key)
            return {**row, "ok": True, "created": out["created"], "post_url": out["page_url"],
                    "password": None, "unlock_chapter_index": None}
        ch = publish.build_chapter(db, doc, prefs)
        result = wp_http.publish(c, endpoint, publish.payload(
            ch, key, scheduled=scheduled, attribution=prefs.wp_attribution_enabled))
    except (publish.NotReady, WPPublishError) as exc:
        return {**row, "ok": False, "error": str(exc)}
    except Exception:  # one bad chapter must not stop the rest
        log.exception("publishing document %s failed", doc.id)
        return {**row, "ok": False, "error": "publishing this chapter failed"}
    written = publish.record(doc, result, scheduled, ch.doc_meta["series_order"])
    if written:
        publish.freeze_volume_name(db, doc.volume_id)
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
    # .get: a job queued before the Illustrations chapter carried {volume_id} instead
    doc_id = ctx.params.get("document_id")
    doc = ctx.db.get(Document, doc_id) if doc_id is not None else None
    if doc is None or doc.user_id != ctx.job.user_id or not doc.is_illustrations:
        raise JobError("the Illustrations chapter no longer exists")
    endpoint, key = _config(ctx)

    def progress(done: int, total: int) -> None:
        ctx.progress(done, total, f"Batch {done} of {total}" if done else "Uploading")
    try:
        with http_client() as c:
            return illustrations.upload(ctx.db, c, doc, endpoint, key, progress)
    except (publish.NotReady, WPPublishError) as exc:
        raise JobError(str(exc)) from exc
