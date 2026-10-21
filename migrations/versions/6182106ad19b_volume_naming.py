"""volume naming: volumes get kind, decimal index and subtitle instead of a title

Revision ID: 6182106ad19b
Revises: f8ea6091f19f
Create Date: 2026-10-21 14:21:39.141242

The data step parses each legacy title with api.core.volume_names.parse_title_fit (no
frozen copy). Downgrade restores ``title`` from wp_volume_title (published volumes), else
the short label: lossy only in that the label's format may differ from the original string.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

from api.core.volume_names import label, parse_title_fit

# revision identifiers, used by Alembic.
revision: str = '6182106ad19b'
down_revision: str | Sequence[str] | None = 'f8ea6091f19f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def _free(name: str, taken: set) -> str:
    candidate, n = name, 2
    while candidate in taken:
        candidate, n = f"{name} ({n})", n + 1
    return candidate


def _split_titles(conn: Connection) -> None:
    """Parse every volume title per series in volume_order, id order. A number the column
    cannot hold, or a parsed (kind, index) already taken in the series, keeps the whole
    title as an unkinded, unnumbered subtitle instead. Such a fallback title that is (or
    starts with) the series title keeps its EPUB title as an override, so the default
    template never renders "Series - Series"."""
    rows = conn.execute(sa.text(
        "SELECT v.id, v.series_id, v.title, v.epub_title, s.title FROM volumes v "
        "JOIN series s ON s.id = v.series_id ORDER BY v.series_id, v.volume_order, v.id"
    )).all()
    numbered: set = set()
    unnumbered: dict[tuple, set[str]] = {}
    for vid, series_id, title, epub_title, series_title in rows:
        kind, index, subtitle = parse_title_fit(title, series_title)
        if index is not None and (series_id, kind.lower(), index) in numbered:
            kind, index, subtitle = "", None, title.strip()
        if index is None:
            # Old titles were unique, so this only bites on whitespace-only differences.
            seen = unnumbered.setdefault((series_id, kind.lower()), set())
            subtitle = _free(subtitle, seen)
            seen.add(subtitle)
        else:
            numbered.add((series_id, kind.lower(), index))
        if (not kind and index is None and not (epub_title or "").strip()
                and _names_series(title, series_title)):
            epub_title = title
        conn.execute(sa.text(
            "UPDATE volumes SET kind = :k, volume_index = :i, subtitle = :s, epub_title = :e "
            "WHERE id = :id"
        ), {"k": kind, "i": index, "s": subtitle, "e": epub_title, "id": vid})


def _names_series(title: str, series_title: str) -> bool:
    """The title is the series title or starts with it, ignoring case."""
    series = series_title.strip().lower()
    return bool(series) and title.strip().lower().startswith(series)


def _freeze_wp_names(conn: Connection) -> None:
    """Already-published volumes keep sending WordPress exactly their old title."""
    conn.execute(sa.text(
        "UPDATE volumes v SET wp_volume_title = v.title WHERE EXISTS ("
        "SELECT 1 FROM documents d WHERE d.volume_id = v.id "
        "AND (d.wp_post_url <> '' OR d.wp_published_at IS NOT NULL))"
    ))


def _label_titles(conn: Connection) -> None:
    """Downgrade: title = the frozen WordPress name (a published volume's exact old title),
    else the short label; suffixed ' (n)' where two collide."""
    rows = conn.execute(sa.text(
        "SELECT id, series_id, kind, volume_index, subtitle, wp_volume_title FROM volumes "
        "ORDER BY series_id, volume_order, id"
    )).all()
    taken: dict[int, set[str]] = {}
    for vid, series_id, kind, index, subtitle, wp_title in rows:
        seen = taken.setdefault(series_id, set())
        title = _free(wp_title or label(kind, index, subtitle) or "Volume", seen)
        seen.add(title)
        conn.execute(sa.text("UPDATE volumes SET title = :t WHERE id = :id"),
                     {"t": title, "id": vid})


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('series', sa.Column('volume_title_template', sa.Text(), server_default='', nullable=False))
    op.add_column('volumes', sa.Column('kind', sa.Text(), server_default='Volume', nullable=False))
    op.add_column('volumes', sa.Column('volume_index', sa.Numeric(precision=10, scale=3), nullable=True))
    op.add_column('volumes', sa.Column('subtitle', sa.Text(), server_default='', nullable=False))
    op.add_column('volumes', sa.Column('wp_volume_title', sa.Text(), nullable=True))
    conn = op.get_bind()
    _split_titles(conn)
    _freeze_wp_names(conn)
    op.drop_constraint(op.f('volumes_series_id_title_key'), 'volumes', type_='unique')
    op.drop_column('volumes', 'title')
    op.create_index('uq_volumes_kind_index', 'volumes', ['series_id', sa.literal_column('lower(kind)'), 'volume_index'], unique=True, postgresql_where=sa.text('volume_index IS NOT NULL'))
    op.create_index('uq_volumes_kind_subtitle', 'volumes', ['series_id', sa.literal_column('lower(kind)'), 'subtitle'], unique=True, postgresql_where=sa.text('volume_index IS NULL'))


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('volumes', sa.Column('title', sa.TEXT(), autoincrement=False, nullable=True))
    _label_titles(op.get_bind())
    op.alter_column('volumes', 'title', nullable=False)
    op.drop_index('uq_volumes_kind_subtitle', table_name='volumes', postgresql_where=sa.text('volume_index IS NULL'))
    op.drop_index('uq_volumes_kind_index', table_name='volumes', postgresql_where=sa.text('volume_index IS NOT NULL'))
    op.create_unique_constraint(op.f('volumes_series_id_title_key'), 'volumes', ['series_id', 'title'], postgresql_nulls_not_distinct=False)
    op.drop_column('volumes', 'wp_volume_title')
    op.drop_column('volumes', 'subtitle')
    op.drop_column('volumes', 'volume_index')
    op.drop_column('volumes', 'kind')
    op.drop_column('series', 'volume_title_template')
