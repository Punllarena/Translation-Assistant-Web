from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

# Bounds mirror the columns in api/models/identity.py. name is String(120); endpoint_url
# is Text, so it is capped here at 2048 characters (a generous URL length) to reject
# absurd input with a 422 instead of storing it. secret is LargeBinary (no column width),
# so it is capped at 4096 characters: real keys are a few hundred characters, and the
# cap leaves room for JWT-style tokens while stopping multi-megabyte payloads.
CredentialKind = Literal["deepl", "libretranslate", "wordpress", "ollama"]
Name = Annotated[str, StringConstraints(max_length=120)]
EndpointUrl = Annotated[str, StringConstraints(max_length=2048)]
SECRET_MAX_LENGTH = 4096
SECRET_OPTIONAL = {"ollama", "libretranslate"}  # endpoint-only kinds: the key is optional


class CredentialCreate(BaseModel):
    kind: CredentialKind
    name: Name = ""
    secret: str = Field(default="", max_length=SECRET_MAX_LENGTH)
    endpoint_url: EndpointUrl = ""

    @model_validator(mode="after")
    def _secret_required(self) -> "CredentialCreate":
        if not self.secret and self.kind not in SECRET_OPTIONAL:
            raise ValueError(f"secret: required for {self.kind}")
        return self


class CredentialUpdate(BaseModel):
    name: Name | None = None
    secret: str | None = Field(default=None, min_length=1, max_length=SECRET_MAX_LENGTH)
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
    has_secret: bool  # a readable secret is present
    secret_hint: str
    secret_unreadable: bool  # a stored blob exists but cannot be decrypted; re-enter it
