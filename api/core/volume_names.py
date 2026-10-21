"""Volume naming rules: kind + decimal index + subtitle.

Pure functions (no DB, no FastAPI). The TypeScript twin in
``web/src/library/volumeNames.ts`` is checked against the same case table,
``web/src/library/volumeNames.cases.json``.
"""

import re
import unicodedata
from decimal import Decimal
from typing import NamedTuple

DEFAULT_TEMPLATE = "{series} - {kind} {index} - {subtitle}"
PLACEHOLDERS = ("series", "kind", "index", "subtitle")

_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
_WS_RE = re.compile(r"\s+")


class ParsedName(NamedTuple):
    kind: str
    index: Decimal | None
    subtitle: str


def format_index(index: Decimal | None) -> str:
    """'' for None; trailing zeros and a bare point are dropped."""
    if index is None:
        return ""
    return format(index.normalize(), "f")


def validate_template(template: str) -> None:
    for name in _PLACEHOLDER_RE.findall(template):
        if name not in PLACEHOLDERS:
            raise ValueError(f"unknown placeholder {{{name}}}")
    stray = _PLACEHOLDER_RE.sub("", template)
    for ch in "{}":
        if ch in stray:
            raise ValueError(f"stray brace {ch!r} in template")


def render(
    template: str,
    *,
    series: str,
    kind: str,
    index: Decimal | None,
    subtitle: str,
    sep: str = " - ",
) -> str:
    values = {
        "series": series,
        "kind": kind,
        "index": format_index(index),
        "subtitle": subtitle,
    }
    # Split on the literal separator first so a separator inside a value
    # (a subtitle like "Re:Start - Part 1") is never split.
    parts: list[str] = []
    for segment in template.split(sep):
        names = _PLACEHOLDER_RE.findall(segment)
        if names and not any(values.get(n, "") for n in names):
            continue
        text = _PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), ""), segment)
        text = _WS_RE.sub(" ", text).strip()
        if text:
            parts.append(text)
    return sep.join(parts)


def label(kind: str, index: Decimal | None, subtitle: str) -> str:
    """Display label, e.g. 'Side Story 1 · Roxy'."""
    return render(
        "{kind} {index} · {subtitle}",
        series="", kind=kind, index=index, subtitle=subtitle, sep=" · ",
    )


def wp_label(kind: str, index: Decimal | None, subtitle: str) -> str:
    """Same as label() with a plain ' - ' separator, for WordPress."""
    return render(
        "{kind} {index} - {subtitle}",
        series="", kind=kind, index=index, subtitle=subtitle,
    )


_NUM = r"(\d+(?:\.\d+)?)"
# The number must end the string or be followed by whitespace or a separator,
# so "3rd Arc" is not volume 3.
_END = r"(?=$|[\s\-–—:.])"
_SHAPES = (
    ("Volume", re.compile(rf"(?:volume|vol\.?|v)\s*{_NUM}{_END}", re.I)),
    ("Volume", re.compile(rf"第\s*{_NUM}\s*巻")),
    ("Side Story", re.compile(rf"(?:side story|ss)\s*{_NUM}{_END}", re.I)),
    ("Short Stories", re.compile(rf"short stories\s*{_NUM}{_END}", re.I)),
    ("Volume", re.compile(rf"{_NUM}{_END}")),
)
_SEP_RE = re.compile(r"\s*[-–—:.]?\s*")


def _strip_series(text: str, series: str) -> str:
    series = unicodedata.normalize("NFKC", series).strip()
    if not series or not text.lower().startswith(series.lower()):
        return text
    rest = text[len(series):]
    for lead in (" - ", ":", " "):
        if rest.startswith(lead):
            return rest[len(lead):].strip() or text
    return text


def parse_title(title: str, series_title: str = "") -> ParsedName:
    """Split a legacy single-string volume title into kind, index, subtitle."""
    text = _strip_series(unicodedata.normalize("NFKC", title).strip(), series_title)
    for kind, rx in _SHAPES:
        m = rx.match(text)
        if m:
            rest = text[m.end():]
            rest = rest[_SEP_RE.match(rest).end():].strip()
            return ParsedName(kind, Decimal(m.group(1)), rest)
    return ParsedName("", None, title.strip())


_STEP = Decimal("0.001")
_LIMIT = Decimal(10) ** 7  # volumes.volume_index is Numeric(10, 3)


def quantize_index(index: Decimal) -> Decimal:
    """Round to the column's 3 places, so '1.0004' finds the stored 1.000."""
    return index.quantize(_STEP)


def index_fits(index: Decimal) -> bool:
    """True when the quantized index fits Numeric(10, 3)."""
    # The first test also keeps quantize() from overflowing on a hundred-digit number.
    return abs(index) < _LIMIT and abs(quantize_index(index)) < _LIMIT


def parse_title_fit(title: str, series_title: str = "") -> ParsedName:
    """parse_title for storage: index quantized; a number the column cannot hold keeps
    the whole title as an unnumbered subtitle (the migration's rule)."""
    parsed = parse_title(title, series_title)
    if parsed.index is None:
        return parsed
    if not index_fits(parsed.index):
        return ParsedName("", None, title.strip())
    return parsed._replace(index=quantize_index(parsed.index))


def sort_key(kind: str, index: Decimal | None) -> tuple:
    """Volume first, other named kinds next, unkinded last."""
    folded = kind.strip().casefold()
    group = 0 if folded == "volume" else 2 if folded == "" else 1
    return (group, folded, index is None, index or 0)
