from typing import Annotated, ClassVar, Self

from pydantic import BaseModel, StringConstraints, model_validator

# A name a person reads in a list: surrounding whitespace dropped, never empty.
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]

# Free text about a work (original title, author): trimmed, no NUL, may be blank.
Credit = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=300, pattern=r"^[^\x00]*$")
]


class Patch(BaseModel):
    """A PATCH body. Omitted fields are left alone (handlers dump with exclude_unset);
    an explicit null is a client error, except for fields in NULLABLE, where null means
    "clear it"."""

    NULLABLE: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _no_explicit_null(self) -> Self:
        for field in self.model_fields_set - self.NULLABLE:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self
