from pydantic import BaseModel, EmailStr, Field

from api.accounts import MIN_PASSWORD


class SetupStatus(BaseModel):
    needs_setup: bool


class SetupAdmin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD)
