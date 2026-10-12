"""The aggregator's per-user preferences (plan ruling 9) and cache keys (ruling 8): pure
helpers for api/routers/mt.py."""

import hashlib
from dataclasses import dataclass
from typing import Any

from api.mt.base import ALL_BACKENDS
from api.mt.languages import LANGUAGES
from api.mt.ollama import DEFAULT_SYSTEM_PROMPT

KEYS = ("mt_target", "mt_enabled", "ollama_model", "ollama_system_prompt")
DEFAULT_TARGET = "en"
DEFAULT_ENABLED = ["mecab", "jparser"]  # desktop defaults (ruling 9)
CACHE_BACKEND_MAX = 40  # MtCache.backend column width
LABELS = {"deepl": "DeepL", "libretranslate": "LibreTranslate", "ollama": "Ollama",
          "mecab": "MeCab", "jparser": "JParser"}
WHERE = "under Settings → Machine translation."
NOT_SET = {
    "deepl": f"Add your DeepL API key {WHERE}",
    "libretranslate": f"Set a LibreTranslate URL {WHERE}",
    "ollama": f"Choose an Ollama model {WHERE}",
}
NO_OLLAMA_URL = f"Set an Ollama URL {WHERE}"


@dataclass
class Prefs:
    target: str
    enabled: list[str]
    ollama_model: str
    ollama_prompt: str


def _str(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def parse(stored: dict[str, Any]) -> Prefs:
    """Settings rows (key → JSON value) with defaults; values of the wrong shape are ignored."""
    target = _str(stored.get("mt_target"), DEFAULT_TARGET)
    enabled = stored.get("mt_enabled")
    if not isinstance(enabled, list):
        enabled = DEFAULT_ENABLED
    return Prefs(
        target=target if target in LANGUAGES else DEFAULT_TARGET,
        enabled=[b for b in enabled if isinstance(b, str) and b in ALL_BACKENDS],
        ollama_model=_str(stored.get("ollama_model"), "").strip(),
        ollama_prompt=_str(stored.get("ollama_system_prompt"), "") or DEFAULT_SYSTEM_PROMPT,
    )


def unreadable_key(backend: str) -> str:
    return f"Your saved {LABELS[backend]} key cannot be read; enter it again {WHERE}"


def prompt_hash(system_prompt: str) -> str:
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:12]


def ollama_cache_key(model: str, system_prompt: str) -> str:
    """ollama:<model>:<sha12>, the model truncated so the key fits mt_cache.backend."""
    digest = prompt_hash(system_prompt)
    room = CACHE_BACKEND_MAX - len("ollama:") - len(":") - len(digest)
    return f"ollama:{model[:room]}:{digest}"
