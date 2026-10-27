"""Ollama background-translation preferences: chunk presets and custom sizes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# preset -> (chunk lines, context lines); 0 chunk lines means the whole chapter
PRESETS: dict[str, tuple[int, int]] = {"small": (12, 5), "medium": (25, 10), "large": (0, 0)}
KEYS = ("ollama_preset", "ollama_chunk_lines", "ollama_context_lines", "ollama_num_thread")


@dataclass(frozen=True)
class OllamaPrefs:
    preset: str
    chunk_lines: int
    context_lines: int
    num_thread: int | None


def _int(value: Any, lo: int, hi: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        return None
    return value


def parse(stored: dict[str, Any]) -> OllamaPrefs:
    preset = stored.get("ollama_preset")
    if preset not in PRESETS and preset != "custom":
        preset = "small"
    num_thread = _int(stored.get("ollama_num_thread"), 1, 64)
    if preset in PRESETS:
        return OllamaPrefs(preset, *PRESETS[preset], num_thread)
    chunk = _int(stored.get("ollama_chunk_lines"), 0, 500)
    context = _int(stored.get("ollama_context_lines"), 0, 50)
    if chunk is None or context is None:
        return OllamaPrefs("custom", *PRESETS["small"], num_thread)
    return OllamaPrefs("custom", chunk, context, num_thread)
