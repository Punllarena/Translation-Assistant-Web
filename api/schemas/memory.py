from datetime import datetime

from pydantic import BaseModel, Field

from api.schemas.lines import MAX_TRANSLATION_CHARS, NoNulStr


class TmMatch(BaseModel):
    translated_text: str
    document_id: int
    document_title: str
    updated_at: datetime


MAX_NEEDLE_CHARS = 1000


class FindMatch(BaseModel):
    document_id: int
    title: str
    line_number: int
    before: str
    after: str  # "" when too_long
    too_long: bool = False  # the replaced line would exceed the per-line limit


class FindResult(BaseModel):
    matches: list[FindMatch]
    truncated: bool  # more matches exist than were returned


class ReplaceTarget(BaseModel):
    document_id: int = Field(ge=1, le=2**31 - 1)  # out-of-range ints would 500 in Postgres
    line_number: int = Field(ge=0, le=2**31 - 1)
    before: str = Field(max_length=MAX_TRANSLATION_CHARS)  # the text the user reviewed


class ReplaceRequest(BaseModel):
    find: NoNulStr = Field(min_length=1, max_length=MAX_NEEDLE_CHARS)
    replace: NoNulStr = Field(max_length=MAX_NEEDLE_CHARS)
    case_sensitive: bool = False
    targets: list[ReplaceTarget] = Field(max_length=5000)


class ReplaceResult(BaseModel):
    replaced: int
    skipped: int  # changed since the search, or not in this series


class SuggestRequest(BaseModel):
    min_freq: int = Field(default=2, ge=1, le=999)


class Term(BaseModel):
    term: str
    count: int


class Suggestions(BaseModel):
    available: bool
    message: str | None = None
    terms: list[Term]
