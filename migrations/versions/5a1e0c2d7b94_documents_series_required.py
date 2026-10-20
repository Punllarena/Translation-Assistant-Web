"""documents series required

Revision ID: 5a1e0c2d7b94
Revises: 8d1b54fd9353
Create Date: 2026-10-20 17:39:42.966861

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.core.series_titles import free_title

# revision identifiers, used by Alembic.
revision: str = '5a1e0c2d7b94'
down_revision: str | Sequence[str] | None = '8d1b54fd9353'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _give_orphans_a_series() -> None:
    """Each document with no series gets a series of its own, titled like it."""
    bind = op.get_bind()
    orphans = bind.execute(
        sa.text("SELECT id, user_id, title FROM documents WHERE series_id IS NULL ORDER BY id")
    ).all()
    taken: dict[int, set[str]] = {}
    for doc_id, user_id, title in orphans:
        if user_id not in taken:
            rows = bind.execute(
                sa.text("SELECT title FROM series WHERE user_id = :u"), {"u": user_id}
            )
            taken[user_id] = {row[0] for row in rows}
        name = free_title(taken[user_id], title)
        taken[user_id].add(name)
        series_id = bind.execute(
            sa.text(
                "INSERT INTO series (user_id, title, syosetu_url, wp_series_slug, "
                "wp_series_title_short) VALUES (:u, :t, '', '', '') RETURNING id"
            ),
            {"u": user_id, "t": name},
        ).scalar_one()
        bind.execute(
            sa.text("UPDATE documents SET series_id = :s, series_order = 1 WHERE id = :d"),
            {"s": series_id, "d": doc_id},
        )


def upgrade() -> None:
    """Upgrade schema."""
    _give_orphans_a_series()
    op.alter_column('documents', 'series_id', existing_type=sa.INTEGER(), nullable=False)
    op.drop_constraint('documents_series_id_fkey', 'documents', type_='foreignkey')
    op.create_foreign_key(
        'documents_series_id_fkey', 'documents', 'series', ['series_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema (the series created for orphans stay)."""
    op.drop_constraint('documents_series_id_fkey', 'documents', type_='foreignkey')
    op.create_foreign_key(
        'documents_series_id_fkey', 'documents', 'series', ['series_id'], ['id'],
        ondelete='SET NULL',
    )
    op.alter_column('documents', 'series_id', existing_type=sa.INTEGER(), nullable=True)
