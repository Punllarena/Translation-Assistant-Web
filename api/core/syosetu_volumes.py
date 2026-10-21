"""Which syosetu chapter-title headings start a volume (spec 2026-10-21 syosetu heading
volumes). Syosetu has one heading level, so authors mark a second with a leading symbol
(n0280z: ★ days, ◇ arcs); a series picks every heading, one marker, or none.

A heading sequence is the index's headings in order, ``[[first_num, heading], ...]``: a
chapter's heading is the entry with the greatest first_num <= its number. Pure: no DB."""

import unicodedata
from collections.abc import Iterable


def marker_of(heading: str) -> str | None:
    """The heading's leading symbol or punctuation character, if it has one."""
    text = heading.lstrip()
    if text and unicodedata.category(text[0])[0] in "SP":
        return text[0]
    return None


def heading_sequence(chapters: list[dict]) -> list[list]:
    """From ``fetch_series_index`` output (index order): one entry per heading run."""
    seq: list[list] = []
    current = None
    for ch in chapters:
        group = ch.get("group")
        if group is not None and group != current:
            seq.append([ch["num"], group])
        current = group
    return seq


def offered_markers(sequence: list[list], saved: str = "") -> list[dict]:
    """Markers that start at least two headings, in first-appearance order; the saved
    marker is kept (with its real count) even when the index no longer uses it."""
    counts: dict[str, int] = {}
    for _, heading in sequence:
        m = marker_of(heading)
        if m is not None:
            counts[m] = counts.get(m, 0) + 1
    offered = [{"marker": m, "headings": n} for m, n in counts.items() if n >= 2]
    if saved and all(o["marker"] != saved for o in offered):
        offered.append({"marker": saved, "headings": counts.get(saved, 0)})
    return offered


def _starts(heading: str, mode: str, marker: str) -> bool:
    if mode == "all":
        return True
    return mode == "marker" and marker_of(heading) == marker


def targets(
    sequence: list[list], nums: Iterable[int], mode: str, marker: str
) -> dict[int, str | None]:
    """Each chapter's volume heading: the latest starting heading at or before the
    chapter's own heading, or None (No volume)."""
    # starting[i] = the starting heading in force at sequence entry i
    starting: list[str | None] = []
    latest = None
    for _, heading in sequence:
        if _starts(heading, mode, marker):
            latest = heading
        starting.append(latest)
    out: dict[int, str | None] = {}
    for num in nums:
        i = max((k for k, (first, _) in enumerate(sequence) if first <= num), default=None)
        out[num] = None if i is None else starting[i]
    return out
