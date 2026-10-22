"""Desktop profiles in a ta.db import: read into memory, never written as rows.

Each series the import creates gets a copy of its desktop profile's glossary and words.
A profile copied to no series is dropped when empty and otherwise kept as a chapterless
series of its own (spec "Unused profiles"). Every write goes through ``tadb_rows._add``,
so report counts, row skips and the dry-run rollback work as for any other table.
"""

import sqlite3
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.core.series_titles import free_glossary_title
from api.core.tadb_schema import ImportReport, _get
from api.core.text import DEFAULT_PARSE_CHARS
from api.models import CustomWord, GlossaryEntry, Series, UserSetting


@dataclass
class DesktopProfile:
    name: str
    parse_chars: str
    is_default: bool
    glossary: list[tuple[str, str, int]] = field(default_factory=list)  # phrase, tr, order
    words: list[str] = field(default_factory=list)


def _orphan(report: ImportReport | None, table: str, row: sqlite3.Row) -> None:
    if report is not None:
        report.skipped[table] += 1
        report.messages.append(f"{table} row {row['id']}: profile_id {row['profile_id']} not found")


def read_profiles(
    conn: sqlite3.Connection, report: ImportReport | None = None
) -> dict[str, DesktopProfile]:
    """Every desktop profile by name, in desktop id order, with its glossary (in apply
    order) and words. Rows naming a missing profile are reported as skipped."""
    by_id: dict[int, DesktopProfile] = {}
    for row in conn.execute("SELECT * FROM profiles ORDER BY id"):
        by_id[row["id"]] = DesktopProfile(
            name=row["name"],
            parse_chars=_get(row, "profiles", "parse_chars", DEFAULT_PARSE_CHARS),
            is_default=bool(_get(row, "profiles", "is_default", 0)),
        )
    for row in conn.execute("SELECT * FROM glossary ORDER BY profile_id, sort_order, id"):
        profile = by_id.get(row["profile_id"])
        if profile is None:
            _orphan(report, "glossary", row)
            continue
        sort_order = _get(row, "glossary", "sort_order", 0)
        profile.glossary.append((row["phrase"], row["translation"], sort_order))
    for row in conn.execute("SELECT * FROM custom_words ORDER BY id"):
        profile = by_id.get(row["profile_id"])
        if profile is None:
            _orphan(report, "custom_words", row)
            continue
        profile.words.append(row["word"])
    return {p.name: p for p in by_id.values()}


def fallback(profiles: dict[str, DesktopProfile]) -> DesktopProfile | None:
    """The profile a series with no profile name uses: the desktop default, else the oldest."""
    return next((p for p in profiles.values() if p.is_default), None) or next(
        iter(profiles.values()), None
    )


def copy_to_series(db: Session, series: Series, p: DesktopProfile, report: ImportReport) -> None:
    from api.core import tadb_rows  # imports this module; resolved at call time

    where = f"for series {series.title!r}"
    for i, (phrase, translation, sort_order) in enumerate(p.glossary):
        entry = GlossaryEntry(
            series_id=series.id, phrase=phrase, translation=translation, sort_order=sort_order
        )
        tadb_rows._add(db, entry, "glossary", f"profile {p.name!r} entry {i + 1} {where}", report)
    for i, word in enumerate(p.words):
        row = CustomWord(user_id=series.user_id, series_id=series.id, word=word)
        tadb_rows._add(db, row, "custom_words", f"profile {p.name!r} word {i + 1} {where}", report)


def adopt_profile(
    db: Session,
    series: Series,
    profile_name: str,
    profiles: dict[str, DesktopProfile],
    used: set[str],
    report: ImportReport,
) -> None:
    """Copy a newly created series' desktop profile into it: the named one, else (no name)
    the fallback. An unknown name leaves the glossary empty, with a message."""
    if profile_name:
        profile = profiles.get(profile_name)
        if profile is None:
            report.messages.append(
                f"series {series.title!r}: profile {profile_name!r} does not exist in the "
                "source; imported with an empty glossary"
            )
            return
    else:
        profile = fallback(profiles)
        if profile is None:
            return
    copy_to_series(db, series, profile, report)
    used.add(profile.name)


Content = tuple[frozenset[tuple[str, str]], frozenset[str]]


def _content(p: DesktopProfile) -> Content:
    return frozenset((ph, tr) for ph, tr, _ in p.glossary), frozenset(w.lower() for w in p.words)


def _series_contents(db: Session, user_id: int) -> set[Content]:
    """Each of the account's series as (glossary pairs, lower-cased series words)."""
    pairs: dict[int, set[tuple[str, str]]] = {}
    words: dict[int, set[str]] = {}
    for sid in db.scalars(select(Series.id).where(Series.user_id == user_id)):
        pairs[sid], words[sid] = set(), set()
    rows = db.execute(
        select(GlossaryEntry.series_id, GlossaryEntry.phrase, GlossaryEntry.translation)
        .join(Series, Series.id == GlossaryEntry.series_id)
        .where(Series.user_id == user_id)
    )
    for sid, phrase, translation in rows:
        pairs[sid].add((phrase, translation))
    rows = db.execute(
        select(CustomWord.series_id, CustomWord.word).where(
            CustomWord.user_id == user_id, CustomWord.series_id.is_not(None)
        )
    )
    for sid, word in rows:
        words.setdefault(sid, set()).add(word.lower())
        pairs.setdefault(sid, set())
    return {(frozenset(pairs[s]), frozenset(words[s])) for s in pairs}


def keep_unused(
    db: Session,
    user_id: int,
    profiles: dict[str, DesktopProfile],
    used: set[str],
    report: ImportReport,
) -> None:
    """A profile copied to no series: dropped when empty, already present when a series
    of the account has the same glossary pairs and words (a forced re-import), else a
    series of its own."""
    from api.core import tadb_rows  # imports this module; resolved at call time

    for p in profiles.values():
        if p.name in used or not (p.glossary or p.words):
            continue
        if _content(p) in _series_contents(db, user_id):
            report.already_present["series"] += 1
            report.messages.append(
                f"profile {p.name!r} is used by no imported series; a series with the same "
                "glossary and words is already in this account, kept as is"
            )
            continue
        taken = set(db.scalars(select(func.lower(Series.title)).where(Series.user_id == user_id)))
        title = free_glossary_title(taken, p.name)
        series = Series(user_id=user_id, title=title)
        if not tadb_rows._add(db, series, "series", repr(title), report):
            continue
        report.messages.append(
            f"profile {p.name!r} is used by no imported series; kept as series {title!r}"
        )
        copy_to_series(db, series, p, report)


def import_parse_chars(
    db: Session, user_id: int, profiles: dict[str, DesktopProfile], report: ImportReport
) -> None:
    """Set the user's parse_chars from the desktop default profile, unless the user already
    has the setting or the value is the default."""
    from api.core import tadb_rows  # imports this module; resolved at call time

    profile = fallback(profiles)
    if profile is None or profile.parse_chars == DEFAULT_PARSE_CHARS:
        return
    has = db.scalar(
        select(UserSetting.key).where(
            UserSetting.user_id == user_id, UserSetting.key == "parse_chars"
        )
    )
    if has is None:
        setting = UserSetting(user_id=user_id, key="parse_chars", value_json=profile.parse_chars)
        tadb_rows._add(db, setting, "settings", "parse_chars", report)
