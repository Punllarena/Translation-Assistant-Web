from pydantic import BaseModel


class BrandingOut(BaseModel):
    """What the public endpoint and every admin write answer with."""

    name: str
    show_name: bool
    logo_id: int | None
    logo_dark_id: int | None
    favicon_id: int | None


class BrandingIn(BaseModel):
    """The text part an admin saves; images have their own upload route."""

    name: str
    show_name: bool
