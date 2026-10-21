from pydantic import BaseModel, Field


class FetchUrl(BaseModel):
    url: str = Field(max_length=2000)


class Fetched(BaseModel):
    title: str
    content: str


class IndexChapter(BaseModel):
    num: int
    title: str
    url: str
    group: str | None = None
    fetched: bool


class Marker(BaseModel):
    marker: str
    headings: int


class ChapterList(BaseModel):
    chapters: list[IndexChapter]
    markers: list[Marker]


class FetchChapters(BaseModel):
    nums: list[int] = Field(min_length=1, max_length=5000)


class Refetch(BaseModel):
    force: bool = False
