from pydantic import BaseModel


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
