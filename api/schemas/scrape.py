from typing import Literal

from pydantic import BaseModel, Field


class FetchUrl(BaseModel):
    url: str = Field(max_length=2000)


class Fetched(BaseModel):
    title: str
    content: str


class NovelChapter(BaseModel):
    num: int
    title: str


class NovelInfo(BaseModel):
    title: str
    author: str
    short_story: bool
    first_chapter: NovelChapter


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


class VolumeHeadings(BaseModel):
    mode: Literal["all", "marker", "off"]
    marker: str = Field("", max_length=1)
    apply: bool = False


class RegroupCounts(BaseModel):
    volumes_created: int
    chapters_moved: int
    volumes_emptied: int


class Refetch(BaseModel):
    force: bool = False
