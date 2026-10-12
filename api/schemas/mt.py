from typing import Literal

from pydantic import BaseModel

Backend = Literal["deepl", "libretranslate", "ollama", "mecab", "jparser"]


class BackendStatus(BaseModel):
    name: Backend
    available: bool
    message: str | None = None


class Backends(BaseModel):
    languages: dict[str, str]
    target: str
    enabled: list[str]
    ollama_default_prompt: str
    backends: list[BackendStatus]
