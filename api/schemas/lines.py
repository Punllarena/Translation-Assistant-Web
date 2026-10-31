from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from api.schemas.documents import MAX_RAW_CHARS, DocumentOut

# A pasted translation for one paragraph; generous, but bounded.
MAX_TRANSLATION_CHARS = 100_000


def _reject_nul(v: str) -> str:
    if "\x00" in v:
        raise ValueError("NUL control character is not allowed")
    return v


# Postgres text columns cannot hold NUL, so any user text bound for one goes through this.
NoNulStr = Annotated[str, AfterValidator(_reject_nul)]


class GlossaryMark(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # UTF-16 offsets into the plain text (raw_text with $ / % stripped).
    from_: int = Field(alias="from")
    to: int
    translation: str
    # UTF-16 offsets into the replaced (display) text, for highlight mapping.
    shown_from: int
    shown_to: int


class LineOut(BaseModel):
    line_number: int
    prefix: str
    raw_text: str
    plain_text: str  # raw_text with markers stripped (what replace_and_parse starts from)
    display_text: str  # plain_text with the glossary applied
    sentences: list[str]  # display_text split on the user's parse characters
    replaced: bool  # whether the glossary changed anything
    glossary_marks: list[GlossaryMark]  # glossary matches, offsets into plain_text
    translated_text: str


class DocumentLines(BaseModel):
    document: DocumentOut
    lines: list[LineOut]


class LineEdit(BaseModel):
    line_number: int = Field(ge=0, le=2**31 - 1)
    translated_text: NoNulStr = Field(max_length=MAX_TRANSLATION_CHARS)


class LineBatch(BaseModel):
    # The client flushes its dirty set; a few thousand covers any real chapter.
    lines: list[LineEdit] = Field(min_length=1, max_length=5000)


class SaveResult(BaseModel):
    # Lines that no longer exist (the source was edited elsewhere); everything else saved.
    missing: list[int]


class SourceUpdate(BaseModel):
    text: NoNulStr = Field(max_length=MAX_RAW_CHARS)
    force: bool = False  # confirm a change in the number of lines
