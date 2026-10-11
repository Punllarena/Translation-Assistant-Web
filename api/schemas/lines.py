from pydantic import BaseModel, Field

from api.schemas.documents import DocumentOut
from api.schemas.profiles import ProfileOut

# A pasted translation for one paragraph; generous, but bounded.
MAX_TRANSLATION_CHARS = 100_000


class LineOut(BaseModel):
    line_number: int
    prefix: str
    raw_text: str
    display_text: str  # raw_text with markers stripped and the glossary applied
    sentences: list[str]  # display_text split on the profile's parse characters
    replaced: bool  # whether the glossary changed anything
    translated_text: str


class DocumentLines(BaseModel):
    document: DocumentOut
    profile: ProfileOut | None
    lines: list[LineOut]


class LineEdit(BaseModel):
    line_number: int = Field(ge=0, le=2**31 - 1)
    translated_text: str = Field(max_length=MAX_TRANSLATION_CHARS)


class LineBatch(BaseModel):
    # The client flushes its dirty set; a few thousand covers any real chapter.
    lines: list[LineEdit] = Field(min_length=1, max_length=5000)
