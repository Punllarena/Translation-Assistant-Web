"""WordPress publish machinery, from the desktop ui/wp_publish_flow.py without Qt: the
user's WordPress config, the chapter build, the result write-back and the schedule
helpers. Used by api/routers/wp.py and api/publish_job.py."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.models import ApiCredential
from api.mt.urls import check_user_url
from api.security import decrypt_secret

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
    problem = check_user_url(row.endpoint_url, get_settings().wp_allow_private_urls, "WordPress")
    if problem:
        raise NotReady(problem)
    return row.endpoint_url, key
