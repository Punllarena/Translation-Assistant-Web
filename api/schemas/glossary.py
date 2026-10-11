from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.schemas.lines import NoNulStr

MAX_PHRASE_CHARS = 500
MAX_GLOSSARY_ENTRIES = 10_000


def underscored(translation: str) -> str:
    """The desktop stores a glossary translation with spaces as underscores."""
    return translation.replace(" ", "_")


class GlossaryIn(BaseModel):
    phrase: NoNulStr = Field(min_length=1, max_length=MAX_PHRASE_CHARS)
    translation: NoNulStr = Field(max_length=MAX_PHRASE_CHARS)

    @field_validator("translation")
    @classmethod
    def _underscores(cls, v: str) -> str:
        return underscored(v)


class GlossaryList(BaseModel):
    entries: list[GlossaryIn] = Field(max_length=MAX_GLOSSARY_ENTRIES)

    @model_validator(mode="after")
    def _unique(self) -> "GlossaryList":
        phrases = [e.phrase for e in self.entries]
        if len(set(phrases)) != len(phrases):
            raise ValueError("entries: a phrase is listed more than once")
        return self


class GlossaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phrase: str
    translation: str
    sort_order: int


class ImportResult(BaseModel):
    added: int
    updated: int
    skipped: int  # rows with an empty or over-long phrase, or a NUL
