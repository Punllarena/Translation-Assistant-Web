from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.glossary import ImportResult


class BatchError(BaseModel):
    name: str
    message: str


class BatchImportOut(BaseModel):
    series_id: int
    glossary: ImportResult | None  # null when no CSV was imported
    imported: list[str]
    skipped: list[str]
    errors: list[BatchError]
    warnings: list[str]


class ExportZipRequest(BaseModel):
    document_ids: list[int] = Field(min_length=1, max_length=500)
    format: Literal["txt", "md", "md-ruby"]
