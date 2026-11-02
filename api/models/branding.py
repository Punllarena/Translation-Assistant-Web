from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from api.db import Base


class Branding(Base):
    """The site-wide brand: one row, id 1, created on first read."""

    __tablename__ = "branding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # None = the default name (api/branding.DEFAULT_NAME), never an empty brand.
    name: Mapped[str | None] = mapped_column(String(60))
    show_name: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class BrandImage(Base):
    """An uploaded logo or favicon; one row per kind. Replacing makes a new row, so its id
    is a cache key that never changes meaning."""

    __tablename__ = "brand_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
