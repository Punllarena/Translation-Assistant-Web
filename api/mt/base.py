"""The aggregator's shared vocabulary (spec §8): SSE events, setup and failure signals."""

import json

Event = tuple[str, dict]  # (type, data); types are listed in the plan's ruling 11

HTTP_BACKENDS = ("deepl", "libretranslate", "ollama")
ANALYZERS = {"mecab", "jparser"}
ALL_BACKENDS = HTTP_BACKENDS + ("mecab", "jparser")


def sse(event: Event) -> str:
    kind, data = event
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class NeedsSetup(Exception):
    """The backend is not configured for this user or server; the message says how."""


class BackendError(Exception):
    """A backend call failed. The message is shown to the user: never put a secret in it."""
