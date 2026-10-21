from decimal import Decimal
from typing import Annotated, ClassVar, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from api.core.volume_names import format_index
from api.schemas.common import Patch

Kind = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Subtitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
VolumeIndex = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=3)]
NAME_EMPTY = "give a kind, number or subtitle"


def check_name(kind: str, index: Decimal | None, subtitle: str) -> None:
    """A volume needs something to be called by."""
    if not kind and index is None and not subtitle:
        raise ValueError(NAME_EMPTY)


class VolumeCreate(BaseModel):
    kind: Kind = "Volume"
    volume_index: VolumeIndex | None = None
    subtitle: Subtitle = ""
    volume_order: int | None = Field(default=None, ge=0, le=2**31 - 1)  # None: last
    epub_title: str = ""
    epub_author: str = ""
    epub_language: str = Field(default="en", min_length=2, max_length=16)
    epub_description: str = ""
    epub_illustrator: str = ""
    epub_publisher: str = ""
    epub_identifier: str = ""

    @model_validator(mode="after")
    def _named(self) -> Self:
        check_name(self.kind, self.volume_index, self.subtitle)
        return self


class VolumeUpdate(Patch):
    """The router checks the merged kind/index/subtitle with check_name()."""

    NULLABLE: ClassVar[frozenset[str]] = frozenset({"volume_index"})

    kind: Kind | None = None
    volume_index: VolumeIndex | None = None
    subtitle: Subtitle | None = None
    volume_order: int | None = Field(default=None, ge=0, le=2**31 - 1)
    epub_title: str | None = None
    epub_author: str | None = None
    epub_language: str | None = Field(default=None, min_length=2, max_length=16)
    epub_description: str | None = None
    epub_illustrator: str | None = None
    epub_publisher: str | None = None
    epub_identifier: str | None = None


class VolumeMerge(BaseModel):
    volume_ids: list[int] = Field(min_length=1, max_length=1000)
    into: int


class VolumeIds(BaseModel):
    volume_ids: list[int] = Field(max_length=1000)


class VolumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    kind: str
    volume_index: str | None  # "3.5", never a float
    subtitle: str
    label: str
    full_title: str
    wp_volume_title: str | None
    volume_order: int
    epub_title: str
    epub_author: str
    epub_language: str
    epub_description: str
    epub_illustrator: str
    epub_publisher: str
    epub_identifier: str

    @field_validator("volume_index", mode="before")
    @classmethod
    def _index_text(cls, value: object) -> object:
        return format_index(value) if isinstance(value, Decimal) else value


class CoverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    src_path: str
