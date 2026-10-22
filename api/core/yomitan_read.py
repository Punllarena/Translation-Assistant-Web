"""Read a Yomitan dictionary zip into one flattened entry per lookup key (spec
"The Yomitan format" and "Flattening one row"). Pure: no database, no network.

Members are only ever read by name, never extracted; the archive is checked first, in
the style of epub_safety.py."""
import json
import re
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field

from api.core.yomitan_gloss import meanings, short_gloss

_MIB = 1024 * 1024
MAX_MEMBERS = 2000
MAX_UNPACKED = 512 * _MIB
MAX_BANK = 64 * _MIB
MAX_ROWS = 3_000_000

_TERM_BANK = re.compile(r"term_bank_(\d+)\.json")
_TAG_BANK = re.compile(r"tag_bank_(\d+)\.json")
_TRAILING_BRACKET = re.compile(r"\s*\[[^\]]*\]\s*$")


NOT_A_ZIP = "This is not a zip file; upload the Yomitan dictionary .zip."
NO_INDEX = "This zip has no index.json; it is not a Yomitan dictionary."
NOT_FORMAT_3 = "Only Yomitan format 3 dictionaries are supported."
NO_WORDS = (
    "This dictionary has no word definitions (kanji, frequency or pitch-accent dictionaries "
    "are not supported); use it in Yomitan instead."
)


class YomitanError(ValueError):
    """The upload is not a Yomitan dictionary we can read."""


@dataclass(frozen=True)
class Meta:
    title: str
    revision: str
    attribution: str
    author: str
    url: str
    identity_key: str


@dataclass(frozen=True)
class FlatEntry:
    headwords: tuple[str, ...]
    reading: str
    pos: frozenset[str]
    gloss: str


@dataclass
class Parsed:
    meta: Meta
    terms: dict[str, FlatEntry]
    entry_count: int
    skipped_rows: int


@dataclass
class _Group:
    sequence: int  # 0 when the rows were grouped by form
    first_order: int
    headwords: list[str] = field(default_factory=list)
    reading: str = ""
    pos: set[str] = field(default_factory=set)
    rows: list[tuple[int, int, list[str]]] = field(default_factory=list)
    max_score: int | None = None
    popular: bool = False


def identity_key(index: dict) -> str:
    url = index.get("indexUrl")
    if isinstance(url, str) and url:
        return f"url:{url}"
    title = index.get("title")
    title = title if isinstance(title, str) else ""
    return f"title:{_TRAILING_BRACKET.sub('', title).strip()}"


def _text(index: dict, key: str) -> str:
    value = index.get(key)
    return value if isinstance(value, str) else ""


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _json(zf: zipfile.ZipFile, name: str):
    try:
        info = zf.getinfo(name)
        if info.file_size > MAX_BANK:
            raise YomitanError(f"{name} is larger than {MAX_BANK // _MIB} MiB")
        raw = zf.read(info)
    except (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, EOFError) as exc:
        raise YomitanError(f"{name} cannot be read from the zip") from exc
    try:
        return json.loads(raw)
    except (ValueError, RecursionError) as exc:  # JSON and UTF-8 errors are ValueErrors
        raise YomitanError(f"{name} is not valid JSON") from exc


def _check_archive(zf: zipfile.ZipFile) -> None:
    infos = zf.infolist()
    if len(infos) > MAX_MEMBERS:
        raise YomitanError(f"The zip has more than {MAX_MEMBERS} files.")
    total = 0
    for info in infos:
        parts = info.filename.replace("\\", "/").split("/")
        if info.filename.startswith(("/", "\\")) or ".." in parts:
            raise YomitanError(f"unsafe path in dictionary: {info.filename!r}")
        total += info.file_size
        if total > MAX_UNPACKED:
            raise YomitanError(f"The dictionary expands to more than {MAX_UNPACKED // _MIB} MiB")


def _numbered(names: list[str], pattern: re.Pattern) -> list[str]:
    found = [(int(m.group(1)), n) for n in names if (m := pattern.fullmatch(n))]
    return [n for _, n in sorted(found)]


def _read_index(zf: zipfile.ZipFile) -> dict:
    if "index.json" not in zf.namelist():
        raise YomitanError(NO_INDEX)
    index = _json(zf, "index.json")
    if not isinstance(index, dict):
        raise YomitanError("index.json is not valid JSON")
    if index.get("format", index.get("version")) != 3:
        raise YomitanError(NOT_FORMAT_3)
    if not _text(index, "title") or not _text(index, "revision"):
        raise YomitanError("index.json needs a title and a revision")
    return index


def _pos_names(zf: zipfile.ZipFile, banks: list[str]) -> set[str]:
    names: set[str] = set()
    for bank in banks:
        rows = _json(zf, bank)
        if not isinstance(rows, list):
            raise YomitanError(f"{bank} is not valid JSON")
        for row in rows:
            if (isinstance(row, list) and len(row) >= 2 and row[1] == "partOfSpeech"
                    and isinstance(row[0], str)):
                names.add(row[0])
    return names


def _valid_row(row) -> bool:
    return (
        isinstance(row, list) and len(row) >= 8
        and isinstance(row[0], str) and bool(row[0])
        and isinstance(row[1], str) and isinstance(row[2], str) and isinstance(row[3], str)
        and _is_int(row[4]) and isinstance(row[5], list) and _is_int(row[6])
        and isinstance(row[7], str)
    )


def _add_row(groups: dict, row: list, order: int, sequenced: bool, pos_names: set[str]) -> None:
    expression, reading, tags, rules, score, glossary, sequence, term_tags = row[:8]
    tag_list = tags.split()
    if "forms" in tag_list:
        return
    found = meanings(glossary)
    if not found:
        return
    by_sequence = sequenced and sequence != 0
    key = ("seq", sequence) if by_sequence else ("form", expression, reading)
    group = groups.get(key)
    if group is None:
        group = groups[key] = _Group(sequence=sequence if by_sequence else 0, first_order=order)
    if expression not in group.headwords:
        group.headwords.append(expression)
    if reading and not group.reading:
        group.reading = reading
    group.pos.update(t for t in tag_list if t in pos_names)
    group.pos.update(rules.split())
    group.max_score = score if group.max_score is None else max(group.max_score, score)
    if {"⭐", "P"} & set(term_tags.split()):
        group.popular = True
    group.rows.append((score, order, found))


def _build(group: _Group) -> FlatEntry | None:
    items: list[str] = []
    for _score, _order, found in sorted(group.rows, key=lambda r: (-r[0], r[1])):
        items.extend(found)
    gloss = short_gloss(items)
    if not gloss:
        return None
    reading = group.reading or group.headwords[0]
    return FlatEntry(tuple(group.headwords), reading, frozenset(group.pos), gloss)


def _flatten(groups: dict, meta: Meta, skipped: int) -> Parsed:
    best: dict[str, tuple[tuple, FlatEntry]] = {}
    for group in groups.values():
        entry = _build(group)
        if entry is None:
            continue
        rank = (
            -(group.max_score or 0), not group.popular,
            group.sequence if group.sequence else float("inf"), group.first_order,
        )
        for key in (*entry.headwords, entry.reading):
            if key not in best or rank < best[key][0]:
                best[key] = (rank, entry)
    terms = {key: entry for key, (_rank, entry) in best.items()}
    kept = {id(entry) for entry in terms.values()}
    return Parsed(meta, terms, len(kept), skipped)


def read(path: str, on_bank: Callable[[int, int, str], None] | None = None) -> Parsed:
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
        raise YomitanError(NOT_A_ZIP) from exc
    with zf:
        _check_archive(zf)
        index = _read_index(zf)
        names = zf.namelist()
        term_banks = _numbered(names, _TERM_BANK)
        if not term_banks:
            raise YomitanError(NO_WORDS)
        pos_names = _pos_names(zf, _numbered(names, _TAG_BANK))
        sequenced = index.get("sequenced") is True
        groups: dict = {}
        skipped = order = 0
        for done, bank in enumerate(term_banks):
            if on_bank is not None:
                on_bank(done, len(term_banks), bank)
            rows = _json(zf, bank)
            if not isinstance(rows, list):
                raise YomitanError(f"{bank} is not valid JSON")
            if order + len(rows) > MAX_ROWS:
                raise YomitanError(f"The dictionary has more than {MAX_ROWS:,} rows.")
            for row in rows:
                order += 1
                if not _valid_row(row):
                    skipped += 1
                    continue
                _add_row(groups, row, order, sequenced, pos_names)
        meta = Meta(
            _text(index, "title"), _text(index, "revision"), _text(index, "attribution"),
            _text(index, "author"), _text(index, "url"), identity_key(index),
        )
    parsed = _flatten(groups, meta, skipped)
    if not parsed.terms:
        raise YomitanError(NO_WORDS)
    return parsed
