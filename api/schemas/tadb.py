from pydantic import BaseModel

from api.schemas.jobs import JobOut


class TadbUploadOut(BaseModel):
    upload_id: str
    job_id: int


class TadbRunIn(BaseModel):
    force: bool = False


class TadbPendingOut(BaseModel):
    job: JobOut
    upload_id: str
