from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DictFileOut(BaseModel):
    present: bool
    source: Literal["env", "data_dir"] | None
    size: int | None
    updated_at: datetime | None
    entries: int | None


class DictionaryOut(BaseModel):
    edict: DictFileOut
    conjugations: DictFileOut
