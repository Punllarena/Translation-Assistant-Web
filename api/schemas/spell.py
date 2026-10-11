from typing import Annotated

from pydantic import BaseModel, Field

# The client batches the visible cards; 200 covers a tall screen with room to spare.
MAX_TEXTS = 200
MAX_TEXT_CHARS = 100_000


class SpellRequest(BaseModel):
    texts: list[Annotated[str, Field(max_length=MAX_TEXT_CHARS)]] = Field(max_length=MAX_TEXTS)
    profile_id: int | None = None


class Misspelling(BaseModel):
    start: int  # UTF-16 code units
    end: int
    word: str
    suggestions: list[str]


class SpellResult(BaseModel):
    available: bool
    results: list[list[Misspelling]]
