from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    is_admin: bool


class SetupStatus(BaseModel):
    needed: bool


class SetupRequest(BaseModel):
    token: str
    email: EmailStr
    password: str = Field(min_length=12)
