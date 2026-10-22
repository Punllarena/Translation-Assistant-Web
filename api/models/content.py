from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    and_,
    func,
    literal,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.elements import ColumnElement

from api.core import volume_names
from api.db import Base

if TYPE_CHECKING:
    from api.models.identity import CustomWord, GlossaryEntry


class Series(Base):
    __tablename__ = "series"
    __table_args__ = (UniqueConstraint("user_id", "title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    syosetu_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    original_title: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    original_author: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    author_romaji: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    wp_series_slug: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wp_series_title_short: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wp_password_enabled: Mapped[bool | None] = mapped_column(Boolean)
    wp_unlock_after: Mapped[int | None] = mapped_column(Integer)
    # Which syosetu chapter-title headings start a volume: 'all', 'marker' (headings that
    # begin with syosetu_volume_marker) or 'off'. syosetu_headings is the index's heading
    # sequence from the last read, [[first_num, heading], ...]; None = never read.
    syosetu_volume_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="all", server_default="all"
    )
    syosetu_volume_marker: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    syosetu_headings: Mapped[list | None] = mapped_column(JSONB)
    # How a volume's EPUB title is built (api/core/volume_names.py); '' = the default.
    volume_title_template: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", passive_deletes=True
    )
    volumes: Mapped[list["Volume"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    glossary: Mapped[list["GlossaryEntry"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", passive_deletes=True
    )
    custom_words: Mapped[list["CustomWord"]] = relationship(
        back_populates="series", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def volume_title_template_effective(self) -> str:
        return self.volume_title_template or volume_names.DEFAULT_TEMPLATE


class Volume(Base):
    """Named by kind + decimal index + subtitle; unique per series by (kind, index), or by
    (kind, subtitle) when unnumbered (indexes below the class)."""

    __tablename__ = "volumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, default="Volume", server_default="Volume"
    )
    volume_index: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    subtitle: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
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
    # What WordPress was first sent as volume_title; the plugin keys pages on it, so it
    # never changes once set. None = never published.
    wp_volume_title: Mapped[str | None] = mapped_column(Text)
    series: Mapped[Series] = relationship(back_populates="volumes")

    @classmethod
    def named(cls, kind: str, index: Decimal | None, subtitle: str) -> ColumnElement[bool]:
        """SQL for "has this name", by the keys of the unique indexes below."""
        # Both sides through Postgres' lower(), so the match is the unique index's own.
        same_kind = func.lower(cls.kind) == func.lower(literal(kind, Text))
        if index is not None:
            return and_(same_kind, cls.volume_index == index)
        return and_(same_kind, cls.volume_index.is_(None), cls.subtitle == subtitle)

    @property
    def label(self) -> str:
        return volume_names.label(self.kind, self.volume_index, self.subtitle)

    @property
    def full_title(self) -> str:
        """The effective EPUB title: the override, else the series template."""
        override = (self.epub_title or "").strip()
        if override:
            return override
        series = self.series
        rendered = volume_names.render(
            series.volume_title_template_effective, series=series.title,
            kind=self.kind, index=self.volume_index, subtitle=self.subtitle,
        )
        return rendered or self.label or series.title

    @property
    def wp_name(self) -> str:
        """The volume_title WordPress gets: frozen after the first publish."""
        return self.wp_volume_title or volume_names.wp_label(
            self.kind, self.volume_index, self.subtitle
        )


Index(
    "uq_volumes_kind_index", Volume.series_id, func.lower(Volume.kind), Volume.volume_index,
    unique=True, postgresql_where=Volume.volume_index.is_not(None),
)
Index(
    "uq_volumes_kind_subtitle", Volume.series_id, func.lower(Volume.kind), Volume.subtitle,
    unique=True, postgresql_where=Volume.volume_index.is_(None),
)


class VolumeSyosetuGroup(Base):
    """A syosetu heading whose chapters go into this volume; never shown, so a renamed
    volume still receives them. A merged volume holds several."""

    __tablename__ = "volume_syosetu_groups"
    __table_args__ = (
        UniqueConstraint("series_id", "heading", name="uq_volume_syosetu_groups_series_heading"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    heading: Mapped[str] = mapped_column(Text, nullable=False)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True
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
    # Reserved: the WordPress plugin's response carries page/post URLs but no post id,
    # so phase 6b leaves this NULL (plan ruling 9). wp_post_url is what it records.
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

    series: Mapped[Series] = relationship(back_populates="documents")
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
        # Translation memory looks lines up by exact source text. A hash index has no
        # btree's ~2.7 KB row limit, and equality is the only lookup it serves.
        Index("ix_lines_raw_text_hash", "raw_text", postgresql_using="hash"),
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
