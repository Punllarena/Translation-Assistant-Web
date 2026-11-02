from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import Patch


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    anchor_position: int
    exclude_export: bool
    src_path: str


class ImageUpdate(Patch):
    exclude_export: bool | None = None
    anchor_position: int | None = Field(None, ge=0)
    document_id: int | None = None  # another chapter of the same volume
