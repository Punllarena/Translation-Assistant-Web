from typing import Literal

from pydantic import BaseModel


class RestoreStatusOut(BaseModel):
    """The restore thread's state; no data from the backup beyond counts."""

    phase: Literal["idle", "restoring", "done", "failed"]
    done: int
    total: int
    message: str
    error: str | None
