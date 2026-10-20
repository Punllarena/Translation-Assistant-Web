from pydantic import BaseModel, EmailStr, Field

from api.accounts import MIN_PASSWORD, USERNAME_PATTERN


class SetupStatus(BaseModel):
    needs_setup: bool


class SetupAdmin(BaseModel):
    email: EmailStr
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=MIN_PASSWORD)
