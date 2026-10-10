from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

# Bounds mirror the columns in api/models/identity.py. name is String(120); endpoint_url
# is Text, so it is capped here at 2048 characters (a generous URL length) to reject
# absurd input with a 422 instead of storing it.
CredentialKind = Literal["deepl", "libretranslate", "wordpress", "ollama"]
Name = Annotated[str, StringConstraints(max_length=120)]
EndpointUrl = Annotated[str, StringConstraints(max_length=2048)]


class CredentialCreate(BaseModel):
    kind: CredentialKind
    name: Name = ""
    secret: str = Field(min_length=1)
    endpoint_url: EndpointUrl = ""


class CredentialUpdate(BaseModel):
    name: Name | None = None
    secret: str | None = Field(default=None, min_length=1)
    endpoint_url: EndpointUrl | None = None

    @model_validator(mode="after")
    def _no_explicit_null(self) -> "CredentialUpdate":
        # Omitted is fine (exclude_unset skips it); an explicit null is a client error.
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class CredentialOut(BaseModel):
    id: int
    kind: str
    name: str
    endpoint_url: str
    has_secret: bool
    secret_hint: str
