from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (UniqueConstraint("user_id", "title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), index=True
    )
    syosetu_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wp_series_slug: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wp_series_title_short: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wp_password_enabled: Mapped[bool | None] = mapped_column(Boolean)
    wp_unlock_after: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="series")
    volumes: Mapped[list["Volume"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class Volume(Base):
    __tablename__ = "volumes"
    __table_args__ = (UniqueConstraint("series_id", "title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    volume_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    epub_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    epub_author: Mapped[str] = mapped_column(Text, nullable=False, default="")
    epub_language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    epub_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Desktop ta.db keeps volume metadata denormalised on every document row
    # (volume_illustrator/publisher/identifier); here it lives once per volume.
    epub_illustrator: Mapped[str] = mapped_column(Text, nullable=False, default="")
    epub_publisher: Mapped[str] = mapped_column(Text, nullable=False, default="")
    epub_identifier: Mapped[str] = mapped_column(Text, nullable=False, default="")

    series: Mapped[Series] = relationship(back_populates="volumes")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), index=True
    )
    volume_id: Mapped[int | None] = mapped_column(
        ForeignKey("volumes.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # The per-chapter display title the desktop app renumbers on split/merge
    # (documents.chapter_title); `title` is the document's own name.
    chapter_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_language: Mapped[str] = mapped_column(String(16), nullable=False, default="ja")
    series_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Ours, not the desktop's: phase 6 fills it from the WordPress REST response when
    # this app publishes a chapter, so it can update that post later. An imported
    # chapter has a wp_post_url and a NULL wp_post_id — that is not a mapping gap.
    wp_post_id: Mapped[int | None] = mapped_column(Integer)
    # wp_post_url and wp_chapter_index come straight from the desktop schema and are
    # what the phase 6 re-publish safeguard reads to know a chapter is already live.
    wp_post_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wp_chapter_index: Mapped[int | None] = mapped_column(Integer)
    wp_status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    wp_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wp_scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    series: Mapped[Series | None] = relationship(back_populates="documents")
    lines: Mapped[list["Line"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    images: Mapped[list["DocumentImage"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Line(Base):
    __tablename__ = "lines"
    __table_args__ = (
        UniqueConstraint("document_id", "line_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prefix: Mapped[str] = mapped_column(String(1), nullable=False, default="%")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    translated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    document: Mapped[Document] = relationship(back_populates="lines")


class DocumentImage(Base):
    __tablename__ = "document_images"
    __table_args__ = (Index("ix_document_images_doc_anchor", "document_id", "anchor_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    anchor_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_cover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    src_path: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    exclude_export: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    document: Mapped[Document] = relationship(back_populates="images")


class MtCache(Base):
    __tablename__ = "mt_cache"
    __table_args__ = (
        UniqueConstraint("backend", "source_lang", "target_lang", "source_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backend: Mapped[str] = mapped_column(String(40), nullable=False)
    source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(16), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkSession(Base):
    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lines_translated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    words_translated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
