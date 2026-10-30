from typing import Literal

from pydantic import BaseModel


class GalleryImageOut(BaseModel):
    """An image tile: a chapter's own image or a volume's cover, never its bytes."""

    id: int
    kind: Literal["image", "cover"]
    volume_id: int | None
    document_id: int | None
    src_path: str
    anchor_position: int
    exclude_export: bool
