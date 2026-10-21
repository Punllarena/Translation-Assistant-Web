"""WordPress publish machinery, from the desktop ui/wp_publish_flow.py without Qt: the
user's WordPress config, the chapter build, the result write-back and the schedule
helpers. Used by api/routers/wp.py and api/publish_job.py."""

from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api import server_settings
from api.core import wp
from api.core.images import shrink_image
from api.models import ApiCredential, Document, DocumentImage, Line, Series, Volume
from api.mt.urls import check_user_url
from api.security import decrypt_secret
from api.wp_prefs import WpPrefs

WHERE = "under Settings → WordPress"


class NotReady(Exception):
    """Something the user must fix first; the message says what and where."""


def wp_config(db: Session, user_id: int) -> tuple[str, str]:
    """(endpoint_url, api_key) of the user's WordPress credential, SSRF-checked (ruling 5).
    Blocking: it resolves DNS."""
    row = db.scalar(select(ApiCredential).where(
        ApiCredential.user_id == user_id, ApiCredential.kind == "wordpress",
        ApiCredential.name == ""))
    if row is None or not row.endpoint_url:
        raise NotReady(f"Set your WordPress endpoint and API key {WHERE}.")
    try:
        key = decrypt_secret(row.secret_enc)
    except ValueError:
        raise NotReady(
            f"Your saved WordPress API key cannot be read; enter it again {WHERE}."
        ) from None
    allow = server_settings.effective(db).wp_allow_private_urls
    problem = check_user_url(row.endpoint_url, allow, "WordPress")
    if problem:
        raise NotReady(problem)
    return row.endpoint_url, key


LIVE = ("publish", "future")
_WP_DATE = "%Y-%m-%dT%H:%M:%SZ"


def wp_date(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime(_WP_DATE)


def check_series(series: Series) -> None:
    """The desktop ensure_series_wp_meta, as a refusal instead of a dialog."""
    if not (series.wp_series_slug and series.wp_series_title_short):
        raise NotReady(
            f'Set the WordPress slug and short title of "{series.title}" on its series page.')


def series_meta(series: Series) -> dict:
    return {"series_slug": series.wp_series_slug,
            "series_title_short": series.wp_series_title_short,
            "syosetu_url": series.syosetu_url}


def image_dict(im: DocumentImage) -> dict:
    """The desktop's in-place shrink: downscaled bytes get a .jpg name."""
    data = shrink_image(im.data)
    src = im.src_path if data is im.data else im.src_path.rsplit(".", 1)[0] + ".jpg"
    return {"id": im.id, "anchor_position": im.anchor_position, "src_path": src, "data": data}


@dataclass(frozen=True)
class Chapter:
    """The desktop PublishJob (renamed: a "job" is a jobs-table row here)."""

    doc_meta: dict
    series_meta: dict
    lines: list[dict]
    inline_images: list[dict]
    cover_image: dict | None
    password: str | None
    unlock_chapter_index: int | None
    prev_wp_chapter_index: int | None


def build_chapter(db: Session, doc: Document, prefs: WpPrefs) -> Chapter:
    """The desktop build_job."""
    series = doc.series
    if series is None:
        raise NotReady("Only a chapter in a series can be published.")
    check_series(series)
    password = unlock = None
    if wp.resolve_wp_password_enabled(series.wp_password_enabled, prefs.wp_password_enabled):
        unlock_after = series.wp_unlock_after or prefs.wp_unlock_after
        password, unlock = wp.compute_password_fields(doc.series_order, unlock_after)
    lines = [{"prefix": p, "translated_text": t} for p, t in db.execute(
        select(Line.prefix, Line.translated_text)
        .where(Line.document_id == doc.id).order_by(Line.line_number))]
    if not any(ln["translated_text"].strip() for ln in lines):
        raise NotReady("No translated lines to publish.")
    images = db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc.id)
                        .order_by(DocumentImage.anchor_position, DocumentImage.id)).all()
    inline = [image_dict(im) for im in images if not im.is_cover and not im.exclude_export]
    cover = next((im for im in images if im.is_cover), None)
    volume = db.get(Volume, doc.volume_id) if doc.volume_id else None
    return Chapter(
        doc_meta={"series_title": series.title, "series_order": doc.series_order,
                  "chapter_title": doc.chapter_title or doc.title,  # ruling 11
                  "volume_title": volume.wp_name if volume else ""},
        series_meta=series_meta(series), lines=lines, inline_images=inline,
        # build_payload sends the cover with chapter 1 only, so only that one is shrunk
        cover_image=image_dict(cover) if cover is not None and doc.series_order == 1 else None,
        password=password, unlock_chapter_index=unlock,
        prev_wp_chapter_index=doc.wp_chapter_index,
    )


def payload(ch: Chapter, api_key: str, *, scheduled: datetime | None, attribution: bool) -> dict:
    """The desktop job_to_payload."""
    return wp.build_payload(
        ch.doc_meta, ch.series_meta, ch.lines, api_key=api_key, password=ch.password,
        unlock_chapter_index=ch.unlock_chapter_index,
        scheduled_date=wp_date(scheduled) if scheduled else None, attribution=attribution,
        images=ch.inline_images, cover=ch.cover_image,
        previous_chapter_index=ch.prev_wp_chapter_index,
    )


def record(doc: Document, result: dict, scheduled: datetime | None) -> bool:
    """The desktop persist_publish_result (ruling 7). False when WordPress reported
    neither created nor updated (its 409 "already there")."""
    if not (result.get("created") or result.get("updated")):
        return False
    doc.wp_status = "future" if scheduled else "publish"
    doc.wp_post_url = str(result.get("post_url") or "")
    doc.wp_published_at = scheduled or datetime.now(UTC)
    doc.wp_scheduled_for = scheduled
    doc.wp_chapter_index = doc.series_order
    return True


def apply_remote_status(doc: Document, result: dict) -> None:
    """The desktop _on_status_ok without its date wipe (ruling 7)."""
    remote = result.get("status")
    if not isinstance(remote, str):
        return
    doc.wp_status = "" if remote == "not_found" else remote[:32]
    doc.wp_post_url = str(result.get("post_url") or "")


def wp_dates(db: Session, user_id: int, series_id: int | None) -> list[str]:
    """The desktop get_wp_dates: dates of published/scheduled chapters, one series or all."""
    q = select(Document.wp_published_at).where(
        Document.user_id == user_id, Document.wp_status.in_(LIVE),
        Document.wp_published_at.is_not(None))
    if series_id is not None:
        q = q.where(Document.series_id == series_id)
    return [wp_date(d) for d in db.scalars(q)]


def suggested_slot(db: Session, doc: Document, prefs: WpPrefs,
                   tz: tzinfo) -> tuple[bool, datetime | None]:
    """The confirm dialog's logic: (previous chapter still scheduled, the auto slot)."""
    if doc.series_order <= 0:
        return False, None
    prev = db.scalar(select(Document).where(
        Document.user_id == doc.user_id, Document.series_id == doc.series_id,
        Document.series_order == doc.series_order - 1).order_by(Document.id).limit(1))
    if prev is None or prev.wp_status != "future":
        return False, None
    if prev.wp_published_at is None:
        return True, None
    scope = None if prefs.wp_schedule_scope_global else doc.series_id
    slot = wp.compute_auto_schedule(
        wp_date(prev.wp_published_at), wp_dates(db, doc.user_id, scope),
        prefs.wp_chapters_per_day, prefs.wp_default_schedule_time, tz=tz)
    return True, slot.replace(tzinfo=tz)


def batch_slots(start: datetime, n: int, per_day: int, default_time: str,
                tz: tzinfo) -> list[datetime]:
    """The desktop _on_publish_batch slot loop: the first at `start`, each next one
    after the previous by compute_auto_schedule over the slots assigned so far."""
    assigned: list[str] = []
    slots: list[datetime] = []
    for i in range(n):
        slot = start if i == 0 else wp.compute_auto_schedule(
            assigned[-1], assigned, per_day, default_time, tz=tz).replace(tzinfo=tz)
        assigned.append(wp_date(slot))
        slots.append(slot)
    return slots


def volume_images(db: Session, volume_id: int) -> tuple[list[dict], dict | None]:
    """The desktop _on_publish_volume_illustrations gathering: every chapter's images in
    reading order, the first cover, the rest unless excluded from export; shrunk.
    ponytail: the volume's art is held in memory at once; stream batches if volumes outgrow it."""
    rows = db.scalars(
        select(DocumentImage).join(Document, Document.id == DocumentImage.document_id)
        .where(Document.volume_id == volume_id,
               or_(DocumentImage.is_cover, DocumentImage.exclude_export.is_(False)))
        .order_by(Document.series_order, Document.id, DocumentImage.anchor_position,
                  DocumentImage.id)).all()
    cover = next((im for im in rows if im.is_cover), None)
    inline = [image_dict(im) for im in rows if not im.is_cover and not im.exclude_export]
    return inline, image_dict(cover) if cover is not None else None
