from pydantic import BaseModel


class TadbUploadOut(BaseModel):
    upload_id: str
    job_id: int


class TadbRunIn(BaseModel):
    force: bool = False
