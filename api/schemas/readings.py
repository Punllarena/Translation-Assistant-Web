from pydantic import BaseModel, Field

MAX_READING_CHARS = 5_000


class ReadingsRequest(BaseModel):
    text: str = Field(max_length=MAX_READING_CHARS)


class ReadingToken(BaseModel):
    surface: str
    kana: str
    pos: str


class ReadingsOut(BaseModel):
    available: bool
    message: str = ""
    tokens: list[ReadingToken]
