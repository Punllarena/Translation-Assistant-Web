from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from api.db import Base


class Dictionary(Base):
    """An admin-uploaded Yomitan dictionary (spec "Upload and storage")."""

    __tablename__ = "dictionaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    identity_key: Mapped[str] = mapped_column(String(600), unique=True)
    title: Mapped[str] = mapped_column(String(256))
    revision: Mapped[str] = mapped_column(String(256))
    attribution: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(String(1024))
    entry_count: Mapped[int] = mapped_column(Integer)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DictionaryTerm(Base):
    """The winning flattened entry for one lookup key; denormalised so a lookup is one query."""

    __tablename__ = "dictionary_terms"
    __table_args__ = (Index("ix_dictionary_terms_key", "key"),)

    dictionary_id: Mapped[int] = mapped_column(
        ForeignKey("dictionaries.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    headwords: Mapped[list[str]] = mapped_column(ARRAY(Text))
    reading: Mapped[str] = mapped_column(Text)
    pos: Mapped[list[str]] = mapped_column(ARRAY(Text))
    gloss: Mapped[str] = mapped_column(Text)
