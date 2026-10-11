from pydantic import BaseModel, ConfigDict

from api.schemas.common import Patch


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    anchor_position: int
    is_cover: bool
    exclude_export: bool
    src_path: str


class ImageUpdate(Patch):
    exclude_export: bool | None = None
