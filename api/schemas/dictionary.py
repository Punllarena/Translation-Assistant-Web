from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DictFileOut(BaseModel):
    present: bool
    source: Literal["env", "data_dir"] | None
    size: int | None
    updated_at: datetime | None
    entries: int | None


class YomitanDictOut(BaseModel):
    id: int
    title: str
    revision: str
    attribution: str
    author: str
    url: str
    entries: int
    installed_at: datetime


class DictionaryOut(BaseModel):
    edict: DictFileOut
    conjugations: DictFileOut
    yomitan: list[YomitanDictOut]
    order: list[str]


class OrderOut(BaseModel):
    order: list[str]


class OrderIn(BaseModel):
    order: list[str]
