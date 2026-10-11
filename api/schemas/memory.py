from datetime import datetime

from pydantic import BaseModel


class TmMatch(BaseModel):
    translated_text: str
    document_id: int
    document_title: str
    updated_at: datetime
