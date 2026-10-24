from pydantic import BaseModel


class BookChapter(BaseModel):
    order: int
    title: str
    href: str
    char_count: int
    image_count: int
    image_only: bool


class BookOut(BaseModel):
    title: str
    author: str
    illustrator: str
    publisher: str
    identifier: str
    has_cover: bool
    chapters: list[BookChapter]


class ChapterError(BaseModel):
    title: str
    message: str


class EpubImportOut(BaseModel):
    series_id: int
    volume_id: int
    imported: list[str]
    skipped: list[str]
    empty: list[str]
    errors: list[ChapterError]
