"""series glossary: glossaries and words belong to a series; profiles are retired

Revision ID: c5af30ce0a6b
Revises: 6182106ad19b
Create Date: 2026-10-22 09:54:46.878934

The data step gives every series a copy of the glossary and words of the profile the editor
applied to it (series.profile_id, else profile_used, else is_default, else the oldest). A
profile no series received becomes a glossary-only series when it holds anything, and is
dropped when empty. The fallback profile's parse characters become the ``parse_chars`` user
setting. Plain SQL, no app imports, so later code changes cannot alter what this does.

Downgrade makes one profile per series, named after it, plus a ``default`` profile per user
holding the account-wide words: a shared profile comes back split.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision: str = 'c5af30ce0a6b'
down_revision: str | Sequence[str] | None = '6182106ad19b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of api.core.text.DEFAULT_PARSE_CHARS (and the old profiles server default).
DEFAULT_PARSE_CHARS = "、 。 ？ ！ 「 」 …… "

# Each user's fallback profile, as editor_profile() picked it without a series profile:
# the profile_used setting when it is a number naming one of theirs, else is_default,
# else the lowest id. NULL for a user with no profiles.
_FALLBACK = """
SELECT u.id AS user_id, (
    SELECT p.id FROM profiles p WHERE p.user_id = u.id
    ORDER BY EXISTS (
        SELECT 1 FROM user_settings us
        WHERE us.user_id = u.id AND us.key = 'profile_used'
          AND jsonb_typeof(us.value_json) = 'number' AND us.value_json::text = p.id::text
    ) DESC, p.is_default DESC, p.id
    LIMIT 1
) AS profile_id
FROM users u
"""


def _copy(conn: Connection, profile_id: int, series_id: int, user_id: int) -> None:
    """Copy a profile's glossary and words into a series, keeping their order."""
    conn.execute(sa.text(
        "INSERT INTO glossary (series_id, phrase, translation, sort_order) "
        "SELECT :s, phrase, translation, sort_order FROM glossary WHERE profile_id = :p "
        "ORDER BY sort_order, id"
    ), {"s": series_id, "p": profile_id})
    conn.execute(sa.text(
        "INSERT INTO custom_words (user_id, series_id, word) "
        "SELECT :u, :s, word FROM custom_words WHERE profile_id = :p ORDER BY id"
    ), {"u": user_id, "s": series_id, "p": profile_id})


def _free_title(name: str, taken: set[str]) -> str:
    """name, else 'name (glossary)', else 'name (glossary n)': free ignoring case."""
    candidate, n = name, 2
    if candidate.lower() in taken:
        candidate = f"{name} (glossary)"
    while candidate.lower() in taken:
        candidate, n = f"{name} (glossary {n})", n + 1
    return candidate


def _adopt_unused(conn: Connection, used: set[int]) -> None:
    """A non-empty profile no series received becomes a chapterless series of its own."""
    rows = conn.execute(sa.text(
        "SELECT p.id, p.user_id, p.name FROM profiles p "
        "WHERE EXISTS (SELECT 1 FROM glossary g WHERE g.profile_id = p.id) "
        "   OR EXISTS (SELECT 1 FROM custom_words w WHERE w.profile_id = p.id) "
        "ORDER BY p.user_id, p.id"
    )).all()
    taken: dict[int, set[str]] = {}
    for profile_id, user_id, name in rows:
        if profile_id in used:
            continue
        if user_id not in taken:
            taken[user_id] = {t.lower() for t in conn.execute(sa.text(
                "SELECT title FROM series WHERE user_id = :u"), {"u": user_id}).scalars()}
        title = _free_title(name, taken[user_id])
        taken[user_id].add(title.lower())
        series_id = conn.execute(sa.text(
            "INSERT INTO series (user_id, title, syosetu_url, wp_series_slug, "
            "wp_series_title_short) VALUES (:u, :t, '', '', '') RETURNING id"
        ), {"u": user_id, "t": title}).scalar_one()
        _copy(conn, profile_id, series_id, user_id)


def _move_to_series(conn: Connection) -> None:
    """Spec Migration steps 2-7: re-key glossary and words from profiles to series."""
    fallback = dict(conn.execute(sa.text(_FALLBACK)).all())
    used: set[int] = set()
    for series_id, user_id, profile_id in conn.execute(sa.text(
        "SELECT id, user_id, profile_id FROM series ORDER BY id"
    )).all():
        profile_id = profile_id if profile_id is not None else fallback.get(user_id)
        if profile_id is not None:
            _copy(conn, profile_id, series_id, user_id)
            used.add(profile_id)
    _adopt_unused(conn, used)
    conn.execute(sa.text(
        "INSERT INTO user_settings (user_id, key, value_json) "
        f"SELECT f.user_id, 'parse_chars', to_jsonb(p.parse_chars) FROM ({_FALLBACK}) f "
        "JOIN profiles p ON p.id = f.profile_id WHERE p.parse_chars <> :default "
        "ON CONFLICT (user_id, key) DO UPDATE SET value_json = EXCLUDED.value_json"
    ), {"default": DEFAULT_PARSE_CHARS})
    conn.execute(sa.text("DELETE FROM glossary WHERE profile_id IS NOT NULL"))
    conn.execute(sa.text("DELETE FROM custom_words WHERE profile_id IS NOT NULL"))
    conn.execute(sa.text("DELETE FROM user_settings WHERE key = 'profile_used'"))


def _free_name(title: str, taken: set[str]) -> str:
    """title cut to the 120-character profile name, suffixed ' (n)' when already taken."""
    candidate, n = title[:120], 2
    while candidate in taken:
        suffix = f" ({n})"
        candidate, n = title[:120 - len(suffix)] + suffix, n + 1
    return candidate


def _new_profile(conn: Connection, user_id: int, name: str, parse_chars: str,
                 is_default: bool) -> int:
    return conn.execute(sa.text(
        "INSERT INTO profiles (user_id, name, parse_chars, is_default) "
        "VALUES (:u, :n, :pc, :d) RETURNING id"
    ), {"u": user_id, "n": name, "pc": parse_chars, "d": is_default}).scalar_one()


def _restore_profiles(conn: Connection) -> None:
    """Downgrade data step: a `default` profile per user with the account-wide words, and
    one profile per series with its glossary and words, which series.profile_id names."""
    parse = dict(conn.execute(sa.text(
        "SELECT user_id, value_json #>> '{}' FROM user_settings "
        "WHERE key = 'parse_chars' AND jsonb_typeof(value_json) = 'string'"
    )).all())
    taken: dict[int, set[str]] = {}
    for (user_id,) in conn.execute(sa.text("SELECT id FROM users ORDER BY id")).all():
        pid = _new_profile(conn, user_id, "default", parse.get(user_id, DEFAULT_PARSE_CHARS),
                           True)
        taken[user_id] = {"default"}
        conn.execute(sa.text(
            "UPDATE custom_words SET profile_id = :p WHERE user_id = :u AND series_id IS NULL"
        ), {"p": pid, "u": user_id})
    for series_id, user_id, title in conn.execute(sa.text(
        "SELECT id, user_id, title FROM series ORDER BY id"
    )).all():
        name = _free_name(title, taken[user_id])
        taken[user_id].add(name)
        pid = _new_profile(conn, user_id, name, parse.get(user_id, DEFAULT_PARSE_CHARS), False)
        params = {"p": pid, "s": series_id}
        conn.execute(sa.text("UPDATE series SET profile_id = :p WHERE id = :s"), params)
        conn.execute(sa.text("UPDATE glossary SET profile_id = :p WHERE series_id = :s"), params)
        conn.execute(sa.text("UPDATE custom_words SET profile_id = :p WHERE series_id = :s"),
                     params)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('glossary', sa.Column('series_id', sa.Integer(), nullable=True))
    op.add_column('custom_words', sa.Column('user_id', sa.Integer(), nullable=True))
    op.add_column('custom_words', sa.Column('series_id', sa.Integer(), nullable=True))
    # A shared profile's rows and their per-series copies coexist until the data step
    # deletes the originals, so the old keying cannot stay unique or required meanwhile.
    op.drop_constraint(op.f('glossary_profile_id_phrase_key'), 'glossary', type_='unique')
    op.drop_index(op.f('uq_custom_words_profile_lower_word'), table_name='custom_words')
    op.alter_column('glossary', 'profile_id', nullable=True)
    op.alter_column('custom_words', 'profile_id', nullable=True)
    _move_to_series(op.get_bind())
    op.alter_column('glossary', 'series_id', nullable=False)
    op.alter_column('custom_words', 'user_id', nullable=False)

    op.create_index(op.f('ix_glossary_series_id'), 'glossary', ['series_id'], unique=False)
    op.create_unique_constraint(op.f('glossary_series_id_phrase_key'), 'glossary', ['series_id', 'phrase'])
    op.create_foreign_key(op.f('glossary_series_id_fkey'), 'glossary', 'series', ['series_id'], ['id'], ondelete='CASCADE')
    op.create_index(op.f('ix_custom_words_series_id'), 'custom_words', ['series_id'], unique=False)
    op.create_index(op.f('ix_custom_words_user_id'), 'custom_words', ['user_id'], unique=False)
    op.create_index('uq_custom_words_series_lower_word', 'custom_words', ['series_id', sa.literal_column('lower(word)')], unique=True, postgresql_where=sa.text('series_id IS NOT NULL'))
    op.create_index('uq_custom_words_user_lower_word', 'custom_words', ['user_id', sa.literal_column('lower(word)')], unique=True, postgresql_where=sa.text('series_id IS NULL'))
    op.create_foreign_key(op.f('custom_words_user_id_fkey'), 'custom_words', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('custom_words_series_id_fkey'), 'custom_words', 'series', ['series_id'], ['id'], ondelete='CASCADE')

    op.drop_index(op.f('ix_glossary_profile_id'), table_name='glossary')
    op.drop_constraint(op.f('glossary_profile_id_fkey'), 'glossary', type_='foreignkey')
    op.drop_column('glossary', 'profile_id')
    op.drop_index(op.f('ix_custom_words_profile_id'), table_name='custom_words')
    op.drop_constraint(op.f('custom_words_profile_id_fkey'), 'custom_words', type_='foreignkey')
    op.drop_column('custom_words', 'profile_id')
    op.drop_index(op.f('ix_series_profile_id'), table_name='series')
    op.drop_constraint(op.f('series_profile_id_fkey'), 'series', type_='foreignkey')
    op.drop_column('series', 'profile_id')
    op.drop_index(op.f('ix_profiles_user_id'), table_name='profiles')
    op.drop_table('profiles')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('profiles',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=120), autoincrement=False, nullable=False),
    sa.Column('parse_chars', sa.TEXT(), server_default=sa.text("'、 。 ？ ！ 「 」 …… '::text"), autoincrement=False, nullable=False),
    sa.Column('is_default', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('profiles_user_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('profiles_pkey')),
    sa.UniqueConstraint('user_id', 'name', name=op.f('profiles_user_id_name_key'), postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_index(op.f('ix_profiles_user_id'), 'profiles', ['user_id'], unique=False)
    op.add_column('series', sa.Column('profile_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.create_foreign_key(op.f('series_profile_id_fkey'), 'series', 'profiles', ['profile_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_series_profile_id'), 'series', ['profile_id'], unique=False)
    op.add_column('glossary', sa.Column('profile_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.add_column('custom_words', sa.Column('profile_id', sa.INTEGER(), autoincrement=False, nullable=True))
    _restore_profiles(op.get_bind())
    op.alter_column('glossary', 'profile_id', nullable=False)
    op.alter_column('custom_words', 'profile_id', nullable=False)

    op.create_foreign_key(op.f('glossary_profile_id_fkey'), 'glossary', 'profiles', ['profile_id'], ['id'], ondelete='CASCADE')
    op.create_index(op.f('ix_glossary_profile_id'), 'glossary', ['profile_id'], unique=False)
    op.create_unique_constraint(op.f('glossary_profile_id_phrase_key'), 'glossary', ['profile_id', 'phrase'], postgresql_nulls_not_distinct=False)
    op.create_foreign_key(op.f('custom_words_profile_id_fkey'), 'custom_words', 'profiles', ['profile_id'], ['id'], ondelete='CASCADE')
    op.create_index(op.f('uq_custom_words_profile_lower_word'), 'custom_words', ['profile_id', sa.literal_column('lower(word::text)')], unique=True)
    op.create_index(op.f('ix_custom_words_profile_id'), 'custom_words', ['profile_id'], unique=False)

    op.drop_constraint(op.f('glossary_series_id_fkey'), 'glossary', type_='foreignkey')
    op.drop_constraint(op.f('glossary_series_id_phrase_key'), 'glossary', type_='unique')
    op.drop_index(op.f('ix_glossary_series_id'), table_name='glossary')
    op.drop_column('glossary', 'series_id')
    op.drop_constraint(op.f('custom_words_user_id_fkey'), 'custom_words', type_='foreignkey')
    op.drop_constraint(op.f('custom_words_series_id_fkey'), 'custom_words', type_='foreignkey')
    op.drop_index('uq_custom_words_user_lower_word', table_name='custom_words', postgresql_where=sa.text('series_id IS NULL'))
    op.drop_index('uq_custom_words_series_lower_word', table_name='custom_words', postgresql_where=sa.text('series_id IS NOT NULL'))
    op.drop_index(op.f('ix_custom_words_user_id'), table_name='custom_words')
    op.drop_index(op.f('ix_custom_words_series_id'), table_name='custom_words')
    op.drop_column('custom_words', 'series_id')
    op.drop_column('custom_words', 'user_id')
