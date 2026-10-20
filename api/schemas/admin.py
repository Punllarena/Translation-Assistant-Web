from typing import Any, Literal

from pydantic import BaseModel


class ServerSettingOut(BaseModel):
    key: str
    value: Any
    source: Literal["db", "env", "default"]


class SettingValue(BaseModel):
    value: Any
