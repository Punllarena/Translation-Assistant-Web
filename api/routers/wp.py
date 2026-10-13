"""WordPress (spec §10): preferences, connection test, status refresh, one-chapter
publish, and the batch publish and volume illustrations jobs (api/publish_job.py)."""

from dataclasses import asdict

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from api import publish, wp_prefs
from api.core import wp_http
from api.core.wp import WPPublishError
from api.deps import current_user, db_session
from api.models import User
from api.routing import api_router
from api.schemas.wp import WpPrefsOut, WpTestOut

router = api_router(tags=["wp"])

http_client = wp_http.client  # the seam tests replace
PROBE_SLUG = "ta-web-connection-test"


def _ready(fn, *args):
    """Run a publish step; NotReady is the user's to fix, so a 422 with its message."""
    try:
        return fn(*args)
    except publish.NotReady as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/wp/prefs", response_model=WpPrefsOut)
def get_prefs(user: User = Depends(current_user), db: Session = Depends(db_session)) -> WpPrefsOut:
    return WpPrefsOut(**asdict(wp_prefs.load(db, user.id)))


@router.post("/wp/test", response_model=WpTestOut)
def test_connection(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> WpTestOut:
    """Ruling 13: ask /status with the saved key; not_found for the probe slug is success."""
    endpoint, key = _ready(publish.wp_config, db, user.id)
    try:
        with http_client() as c:
            wp_http.check_status(c, endpoint, key, PROBE_SLUG, 1)
    except WPPublishError as exc:
        if exc.status_code == 401:
            return WpTestOut(ok=False, message="WordPress answered, but rejected the API key.")
        return WpTestOut(ok=False, message=exc.message)
    return WpTestOut(ok=True, message="Connected; WordPress accepted the API key.")
