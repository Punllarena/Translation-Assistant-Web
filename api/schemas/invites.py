from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class InviteCreate(BaseModel):
    email: EmailStr | None = None
    ttl_days: int = Field(default=14, ge=1, le=90)


class InviteCreated(BaseModel):
    token: str
    expires_at: datetime


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None


class AcceptInvite(BaseModel):
    token: str
    email: EmailStr
    password: str = Field(min_length=12)
