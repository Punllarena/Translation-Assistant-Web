from typing import Literal

from pydantic import BaseModel, Field


class BatchError(BaseModel):
    name: str
    message: str


class BatchImportOut(BaseModel):
    series_id: int
    profile_id: int | None
    imported: list[str]
    skipped: list[str]
    errors: list[BatchError]
    warnings: list[str]


class ExportZipRequest(BaseModel):
    document_ids: list[int] = Field(min_length=1)
    format: Literal["txt", "md", "md-ruby"]
