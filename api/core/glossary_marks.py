"""Glossary match offsets for the editor's glossary-ruby mode.

Mirrors ``replace_and_parse``'s sequential, replace-all glossary pass over the line
text with ``$`` / ``%`` stripped, but tracks where every piece of the shown text came
from, so the client can place ruby over the original text. ``replace_and_parse``'s own
output is untouched; ``_walk`` below reproduces it exactly (proved by the tests).

Offsets are UTF-16 code units (JavaScript string indexes), not Python code points.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Mark:
    from_: int  # UTF-16 offset into the plain text (text with $ / % stripped)
    to: int
    translation: str
    shown_from: int  # UTF-16 offset into the replaced (shown) text
    shown_to: int


def _utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _utf16(text: str, code_point_offset: int) -> int:
    """Convert a code-point offset into ``text`` to a UTF-16 code-unit offset."""
    return _utf16_len(text[:code_point_offset])


def _cut(
    pieces: list[tuple[str, int | None, int | None]], s: int, e: int
) -> tuple[
    list[tuple[str, int | None, int | None]],
    list[tuple[str, int | None, int | None]],
    list[tuple[str, int | None, int | None]],
]:
    """Split ``pieces`` at buffer offsets ``s`` and ``e`` (code points), returning
    ``(left, mid, right)``. ``mid`` holds the pieces within ``[s, e)``, with the
    boundary pieces split. Source offsets are shifted to stay relative to the plain text."""
    pos = 0
    left: list[tuple[str, int | None, int | None]] = []
    mid: list[tuple[str, int | None, int | None]] = []
    right: list[tuple[str, int | None, int | None]] = []
    for text, src, mark_id in pieces:
        end = pos + len(text)
        if end <= s:
            left.append((text, src, mark_id))
        elif pos >= e:
            right.append((text, src, mark_id))
        else:
            lo = max(pos, s) - pos
            hi = min(end, e) - pos
            if lo > 0:
                left.append((text[:lo], src, mark_id))
            mid.append((text[lo:hi], None if src is None else src + lo, mark_id))
            if hi < len(text):
                right.append(
                    (text[hi:], None if src is None else src + hi, mark_id)
                )
        pos = end
    return left, mid, right


def _walk(text: str, glossary: list[tuple[str, str]]) -> tuple[list[Mark], str]:
    """Replicate ``replace_and_parse``'s replacement pass, returning the marks and the
    reconstructed shown text. Each piece is ``(text, src_start, mark_id)``: ``src_start``
    is a code-point offset into the plain text (``None`` for inserted output), and
    ``mark_id`` indexes ``marks`` for a replacement that became a mark."""
    plain = text.replace("$", "").replace("%", "")
    pieces: list[tuple[str, int | None, int | None]] = [(plain, 0, None)]
    marks: list[tuple[int, int, str, int]] = []  # (from_cp, to_cp, translation, mark_id)

    for phrase, translation in glossary:
        if not phrase:
            continue
        buf = "".join(p[0] for p in pieces)
        if phrase not in buf:
            continue
        plen = len(phrase)
        starts: list[int] = []
        pos = 0
        while True:
            idx = buf.find(phrase, pos)
            if idx < 0:
                break
            starts.append(idx)
            pos = idx + plen

        for s in reversed(starts):
            left, mid, right = _cut(pieces, s, s + plen)
            mark_id: int | None = None
            # A mark only for an occurrence wholly inside one untouched original piece,
            # and only when the translation is non-empty (an empty one deletes, no ruby).
            if translation and len(mid) == 1 and mid[0][1] is not None:
                mark_id = len(marks)
                src = mid[0][1]
                marks.append((src, src + len(mid[0][0]), translation, mark_id))
            pieces = left + ([(translation, None, mark_id)] if translation else []) + right

    shown = "".join(p[0] for p in pieces)

    shown_from: dict[int, int] = {}
    shown_to: dict[int, int] = {}
    offset = 0
    for text, _src, mark_id in pieces:
        if mark_id is not None:
            shown_from.setdefault(mark_id, offset)
            shown_to[mark_id] = offset + len(text)
        offset += len(text)

    result: list[Mark] = []
    for from_cp, to_cp, translation, mark_id in marks:
        sf = shown_from.get(mark_id)
        st = shown_to.get(mark_id)
        if sf is None:
            # Best-effort: a later entry consumed the mark's output entirely.
            sf = st = offset
        result.append(
            Mark(
                from_=_utf16(plain, from_cp),
                to=_utf16(plain, to_cp),
                translation=translation,
                shown_from=_utf16(shown, sf),
                shown_to=_utf16(shown, st),
            )
        )
    result.sort(key=lambda m: m.from_)
    return result, shown


def glossary_marks(text: str, glossary: list[tuple[str, str]]) -> list[Mark]:
    """The glossary matches in the original text, sorted and non-overlapping, with UTF-16
    offsets into the plain text and the replaced text (see :class:`Mark`)."""
    marks, _ = _walk(text, glossary)
    return marks
