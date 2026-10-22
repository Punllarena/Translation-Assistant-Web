from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.core.text import DEFAULT_PARSE_CHARS


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parse_chars: str = DEFAULT_PARSE_CHARS
    is_default: bool = False


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parse_chars: str | None = None
    is_default: bool | None = None

    @model_validator(mode="after")
    def _no_explicit_null(self) -> "ProfileUpdate":
        # Omitted is fine (exclude_unset skips it); an explicit null is a client error.
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parse_chars: str
    is_default: bool
