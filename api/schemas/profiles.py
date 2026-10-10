from pydantic import BaseModel, ConfigDict, Field

DEFAULT_PARSE_CHARS = "、 。 ？ ！ 「 」 …… "


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parse_chars: str = DEFAULT_PARSE_CHARS
    is_default: bool = False


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parse_chars: str | None = None
    is_default: bool | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parse_chars: str
    is_default: bool
