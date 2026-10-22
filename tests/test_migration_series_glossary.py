"""The data steps of the series-glossary revision, run inside the test transaction against a
re-created ``profiles`` table and ``profile_id`` columns; the db fixture rolls it all back."""

import importlib.util
from pathlib import Path

from sqlalchemy import text

from api.core.text import DEFAULT_PARSE_CHARS
from api.models import UserSetting

_VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _migration():
    (path,) = _VERSIONS.glob("*_series_glossary.py")
    spec = importlib.util.spec_from_file_location("mig_series_glossary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy(db):
    """The shape upgrade() hands the data step: profiles and the profile_id columns as
    before, the new columns nullable, no unique constraints on either keying."""
    for stmt in (
        "CREATE TABLE profiles (id serial PRIMARY KEY, "
        "user_id integer NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "name varchar(120) NOT NULL, "
        f"parse_chars text NOT NULL DEFAULT '{DEFAULT_PARSE_CHARS}', "
        "is_default boolean NOT NULL DEFAULT false, "
        "created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (user_id, name))",
        "ALTER TABLE series ADD COLUMN profile_id integer "
        "REFERENCES profiles(id) ON DELETE SET NULL",
        "ALTER TABLE glossary ADD COLUMN profile_id integer "
        "REFERENCES profiles(id) ON DELETE CASCADE",
        "ALTER TABLE custom_words ADD COLUMN profile_id integer "
        "REFERENCES profiles(id) ON DELETE CASCADE",
        "ALTER TABLE glossary ALTER COLUMN series_id DROP NOT NULL",
        "ALTER TABLE custom_words ALTER COLUMN user_id DROP NOT NULL",
        "ALTER TABLE glossary DROP CONSTRAINT glossary_series_id_phrase_key",
        "DROP INDEX uq_custom_words_user_lower_word",
        "DROP INDEX uq_custom_words_series_lower_word",
    ):
        db.execute(text(stmt))


def _profile(db, user, name, *, is_default=False, parse_chars=None, glossary=(), words=()):
    pid = db.execute(text(
        "INSERT INTO profiles (user_id, name, is_default, parse_chars) "
        "VALUES (:u, :n, :d, COALESCE(:pc, :default)) RETURNING id"
    ), {"u": user.id, "n": name, "d": is_default, "pc": parse_chars,
        "default": DEFAULT_PARSE_CHARS}).scalar_one()
    for order, (phrase, translation) in enumerate(glossary):
        db.execute(text(
            "INSERT INTO glossary (profile_id, phrase, translation, sort_order) "
            "VALUES (:p, :ph, :t, :o)"
        ), {"p": pid, "ph": phrase, "t": translation, "o": order})
    for word in words:
        db.execute(text("INSERT INTO custom_words (profile_id, word) VALUES (:p, :w)"),
                   {"p": pid, "w": word})
    return pid


def _link(db, series, pid):
    db.execute(text("UPDATE series SET profile_id = :p WHERE id = :s"),
               {"p": pid, "s": series.id})


def _glossary(db, series_id):
    return [tuple(r) for r in db.execute(text(
        "SELECT phrase, translation, sort_order FROM glossary WHERE series_id = :s "
        "ORDER BY sort_order, id"), {"s": series_id})]


def _words(db, series_id):
    return [tuple(r) for r in db.execute(text(
        "SELECT word, user_id FROM custom_words WHERE series_id = :s ORDER BY id"),
        {"s": series_id})]


def _series(db, user):
    return {title: sid for sid, title in db.execute(text(
        "SELECT id, title FROM series WHERE user_id = :u"), {"u": user.id})}


def _setting(db, user, key):
    return db.execute(text(
        "SELECT value_json FROM user_settings WHERE user_id = :u AND key = :k"
    ), {"u": user.id, "k": key}).scalar_one_or_none()


def test_series_with_profile_gets_copy(db, make_user, make_series):
    user = make_user()
    a, b = make_series(user, "A"), make_series(user, "B")
    _legacy(db)
    pid = _profile(db, user, "P", glossary=[("太郎", "Taro"), ("花子", "Hanako")],
                   words=["Rimuru"])
    _link(db, a, pid)
    _link(db, b, pid)

    _migration()._move_to_series(db.connection())

    for series in (a, b):
        assert _glossary(db, series.id) == [("太郎", "Taro", 0), ("花子", "Hanako", 1)]
        assert _words(db, series.id) == [("Rimuru", user.id)]
    # Only the copies remain: nothing is keyed to a profile any more.
    assert db.execute(text("SELECT count(*) FROM glossary")).scalar_one() == 4
    assert db.execute(text(
        "SELECT count(*) FROM custom_words WHERE profile_id IS NOT NULL")).scalar_one() == 0


def test_series_without_profile_gets_fallback_glossary(db, make_user, make_series):
    chosen, default, oldest = (make_user(email=f"{n}@example.com") for n in "xyz")
    series = {u.id: make_series(u, "Loose") for u in (chosen, default, oldest)}
    _legacy(db)
    _profile(db, chosen, "A", is_default=True, glossary=[("a", "A")])
    b = _profile(db, chosen, "B", glossary=[("b", "B")])
    db.add(UserSetting(user_id=chosen.id, key="profile_used", value_json=b))
    _profile(db, default, "A", is_default=True, glossary=[("a", "A")])
    _profile(db, default, "B", glossary=[("b", "B")])
    _profile(db, oldest, "first", glossary=[("1", "one")])
    _profile(db, oldest, "second", glossary=[("2", "two")])
    db.flush()

    _migration()._move_to_series(db.connection())

    assert _glossary(db, series[chosen.id].id) == [("b", "B", 0)]
    assert _glossary(db, series[default.id].id) == [("a", "A", 0)]
    assert _glossary(db, series[oldest.id].id) == [("1", "one", 0)]


def test_profile_used_that_is_not_an_owned_id_is_ignored(db, make_user, make_series):
    user, other = make_user(), make_user(email="other@example.com")
    series = make_series(user, "Loose")
    _legacy(db)
    _profile(db, user, "A", is_default=True, glossary=[("a", "A")])
    theirs = _profile(db, other, "T", glossary=[("t", "T")])
    db.add(UserSetting(user_id=user.id, key="profile_used", value_json=theirs))
    db.flush()
    _migration()._move_to_series(db.connection())
    assert _glossary(db, series.id) == [("a", "A", 0)]


def test_parse_chars_setting_written_only_when_not_default(db, make_user, make_series):
    custom, plain = make_user(), make_user(email="plain@example.com")
    make_series(custom, "S")
    make_series(plain, "S")
    _legacy(db)
    _profile(db, custom, "A", is_default=True, parse_chars="。 ！")
    _profile(db, plain, "A", is_default=True)

    _migration()._move_to_series(db.connection())

    assert _setting(db, custom, "parse_chars") == "。 ！"
    assert _setting(db, plain, "parse_chars") is None


def test_profile_used_rows_deleted(db, make_user, make_series):
    user = make_user()
    make_series(user, "S")
    _legacy(db)
    pid = _profile(db, user, "A")
    db.add(UserSetting(user_id=user.id, key="profile_used", value_json=pid))
    db.add(UserSetting(user_id=user.id, key="ui_theme", value_json="dark"))
    db.flush()
    _migration()._move_to_series(db.connection())
    assert _setting(db, user, "profile_used") is None
    assert _setting(db, user, "ui_theme") == "dark"


def test_unused_empty_profile_dropped(db, make_user, make_series):
    user = make_user()
    series = make_series(user, "S")
    _legacy(db)
    used = _profile(db, user, "used", is_default=True, glossary=[("a", "A")])
    _link(db, series, used)
    _profile(db, user, "Empty")
    _migration()._move_to_series(db.connection())
    assert set(_series(db, user)) == {"S"}


def test_unused_nonempty_profile_becomes_series(db, make_user, make_series):
    free, taken, twice = (make_user(email=f"{n}@example.com") for n in "abc")
    lonely = make_user(email="lonely@example.com")
    for user in (free, taken, twice):
        make_series(user, "Main")
    make_series(taken, "sequel TERMS")
    make_series(twice, "sequel TERMS")
    make_series(twice, "Sequel Terms (GLOSSARY)")
    _legacy(db)
    for user in (free, taken, twice):
        _profile(db, user, "default", is_default=True)
        _profile(db, user, "Sequel terms", glossary=[("魔王", "Demon Lord")], words=["Veldora"])
    _profile(db, lonely, "default", is_default=True, glossary=[("x", "X")])

    _migration()._move_to_series(db.connection())

    expected = {free: "Sequel terms", taken: "Sequel terms (glossary)",
                twice: "Sequel terms (glossary 2)"}
    for user, title in expected.items():
        sid = _series(db, user)[title]
        assert _glossary(db, sid) == [("魔王", "Demon Lord", 0)]
        assert _words(db, sid) == [("Veldora", user.id)]
    assert _glossary(db, _series(db, lonely)["default"]) == [("x", "X", 0)]
    # The empty default profiles of the users with series made nothing.
    assert "default" not in _series(db, free)
    row = db.execute(text(
        "SELECT syosetu_url, syosetu_volume_mode, volume_title_template FROM series "
        "WHERE id = :s"), {"s": _series(db, free)["Sequel terms"]}).one()
    assert tuple(row) == ("", "all", "")


def test_downgrade_restores_one_profile_per_series(db, make_user, make_series):
    user = make_user()
    a, b = make_series(user, "A"), make_series(user, "B")
    _legacy(db)
    pid = _profile(db, user, "P", is_default=True, glossary=[("太郎", "Taro"), ("花子", "Hanako")],
                   words=["Rimuru"])
    _link(db, a, pid)
    _profile(db, user, "Other", glossary=[("b", "B")])
    _link(db, b, db.execute(text("SELECT id FROM profiles WHERE name = 'Other'")).scalar_one())
    mig = _migration()
    conn = db.connection()
    mig._move_to_series(conn)
    db.execute(text("INSERT INTO custom_words (user_id, word) VALUES (:u, 'senpai')"),
               {"u": user.id})
    # downgrade() recreates an empty profiles table before the data step.
    db.execute(text("UPDATE series SET profile_id = NULL"))
    db.execute(text("DELETE FROM profiles"))

    mig._restore_profiles(conn)

    profiles = {name: (pid, is_default) for pid, name, is_default in db.execute(text(
        "SELECT id, name, is_default FROM profiles WHERE user_id = :u"), {"u": user.id})}
    assert set(profiles) == {"A", "B", "default"}
    assert profiles["default"][1] is True

    def pairs(profile_id):
        return [tuple(r) for r in db.execute(text(
            "SELECT phrase, translation, sort_order FROM glossary WHERE profile_id = :p "
            "ORDER BY sort_order"), {"p": profile_id})]

    def words(profile_id):
        return [r[0] for r in db.execute(text(
            "SELECT word FROM custom_words WHERE profile_id = :p ORDER BY id"),
            {"p": profile_id})]

    assert pairs(profiles["A"][0]) == [("太郎", "Taro", 0), ("花子", "Hanako", 1)]
    assert words(profiles["A"][0]) == ["Rimuru"]
    assert pairs(profiles["B"][0]) == [("b", "B", 0)]
    assert words(profiles["default"][0]) == ["senpai"]
    for series, name in ((a, "A"), (b, "B")):
        linked = db.execute(text("SELECT profile_id FROM series WHERE id = :s"),
                            {"s": series.id}).scalar_one()
        assert linked == profiles[name][0]


def test_downgrade_dedupes_profile_names_and_restores_parse_chars(db, make_user, make_series):
    user, bare = make_user(), make_user(email="bare@example.com")
    long_a, long_b = "x" * 130 + "a", "x" * 130 + "b"
    for title in ("default", long_a, long_b):
        make_series(user, title)
    _legacy(db)
    _migration()._move_to_series(db.connection())
    db.add(UserSetting(user_id=user.id, key="parse_chars", value_json="。"))
    db.flush()

    _migration()._restore_profiles(db.connection())

    rows = db.execute(text(
        "SELECT name, parse_chars FROM profiles WHERE user_id = :u ORDER BY id"),
        {"u": user.id}).all()
    names = [r[0] for r in rows]
    assert len(set(names)) == 4 and "default" in names and "default (2)" in names
    assert all(len(n) <= 120 for n in names)
    assert {r[1] for r in rows} == {"。"}
    assert db.execute(text(
        "SELECT name, is_default, parse_chars FROM profiles WHERE user_id = :u"),
        {"u": bare.id}).one() == ("default", True, DEFAULT_PARSE_CHARS)
