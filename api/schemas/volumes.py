from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import Patch, Title


class VolumeCreate(BaseModel):
    title: Title
    volume_order: int | None = Field(default=None, ge=0, le=2**31 - 1)  # None: last
    epub_title: str = ""
    epub_author: str = ""
    epub_language: str = Field(default="en", min_length=2, max_length=16)
    epub_description: str = ""
    epub_illustrator: str = ""
    epub_publisher: str = ""
    epub_identifier: str = ""


class VolumeUpdate(Patch):
    title: Title | None = None
    volume_order: int | None = Field(default=None, ge=0, le=2**31 - 1)
    epub_title: str | None = None
    epub_author: str | None = None
    epub_language: str | None = Field(default=None, min_length=2, max_length=16)
    epub_description: str | None = None
    epub_illustrator: str | None = None
    epub_publisher: str | None = None
    epub_identifier: str | None = None


class VolumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    title: str
    volume_order: int
    epub_title: str
    epub_author: str
    epub_language: str
    epub_description: str
    epub_illustrator: str
    epub_publisher: str
    epub_identifier: str


class CoverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    src_path: str
