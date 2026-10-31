"""The user's Ollama endpoint for chunk translation: credential, URL guard, model, prompt, info."""

from __future__ import annotations

from dataclasses import replace

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import server_settings
from api.models import UserSetting
from api.mt import ollama
from api.mt.ollama import ModelInfo
from api.mt.prefs import LABELS, NOT_SET
from api.mt.urls import check_user_url
from api.ollama import prefs as ollama_prefs
from api.ollama.prefs import OllamaPrefs
from api.ollama.translate import Endpoint
from api.routers.mt import _configure, _prefs

UNKNOWN = ModelInfo(thinking=False, context_length=None)  # until ready() asks the server
_INFO: dict[tuple[str, str], ModelInfo] = {}  # (url, model) -> /api/show answer


def prefs_for(db: Session, user_id: int) -> OllamaPrefs:
    rows = db.execute(
        select(UserSetting.key, UserSetting.value_json).where(
            UserSetting.user_id == user_id, UserSetting.key.in_(ollama_prefs.KEYS)
        )
    )
    return ollama_prefs.parse({key: value for key, value in rows})


def load(db: Session, user_id: int) -> tuple[Endpoint | None, str | None]:
    """The endpoint, or the setup message to show instead. Blocking (DNS, decryption).

    `src` is "ja"; callers set it from the document being translated."""
    p = _prefs(db, user_id)
    job = _configure(db, user_id, "ollama", p)
    if job.setup:
        return None, job.setup
    if not job.model:
        return None, NOT_SET["ollama"]
    op = prefs_for(db, user_id)
    return Endpoint(job.url, job.key, job.model, job.prompt, "ja", p.target,
                    op.num_thread, UNKNOWN, op.think), None


def recheck(db: Session, url: str) -> str | None:
    """The URL guard again, just before a request (DNS may have changed). Blocking."""
    allow = server_settings.effective(db).mt_allow_private_urls
    return check_user_url(url, allow, LABELS["ollama"])


async def ready(client: httpx.AsyncClient, ep: Endpoint) -> Endpoint:
    """`ep` with its model info filled in; BackendError when the server cannot answer."""
    key = (ep.url, ep.model)
    info = _INFO.get(key)
    if info is None:
        info = _INFO[key] = await ollama.show(client, ep.url, ep.token, ep.model)
    return replace(ep, info=info)
