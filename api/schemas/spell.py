from typing import Annotated

from pydantic import BaseModel, Field, model_validator

# The client batches the visible cards; 200 covers a tall screen with room to spare.
MAX_TEXTS = 200
MAX_TEXT_CHARS = 100_000
MAX_TOTAL_CHARS = 200_000  # across all texts: bounds regex + enchant work per request


class SpellRequest(BaseModel):
    texts: list[Annotated[str, Field(max_length=MAX_TEXT_CHARS)]] = Field(max_length=MAX_TEXTS)
    series_id: int | None = Field(default=None, ge=1, le=2**31 - 1)  # 2**31+ would 500 in Postgres

    @model_validator(mode="after")
    def _total_size(self):
        if sum(len(t) for t in self.texts) > MAX_TOTAL_CHARS:
            raise ValueError(f"texts total more than {MAX_TOTAL_CHARS} characters")
        return self


class Misspelling(BaseModel):
    start: int  # UTF-16 code units
    end: int
    word: str
    suggestions: list[str]


class SpellResult(BaseModel):
    available: bool
    results: list[list[Misspelling]]
