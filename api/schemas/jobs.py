from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    kind: str
    state: str
    progress: int
    total: int
    message: str
    params: dict = Field(validation_alias="params_json")
    result: dict | None = Field(validation_alias="result_json")
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
