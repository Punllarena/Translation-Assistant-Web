"""Plan EPUB chapters from table-of-contents anchors across spine files. Pure: no zip, no
database. The reader (epub_read.py) feeds it the spine, the TOC and the anchor ids found in
each file, then cuts each file's paragraphs and images with ``units``."""
import posixpath
from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import Tag


@dataclass(frozen=True)
class Piece:
    href: str              # zip path
    start: str | None      # element id to start at; None = top of file
    end: str | None        # element id to stop before; None = end of file


@dataclass(frozen=True)
class Planned:
    title: str
    key: str               # href, or href + "#" + fragment; what the picker sends back
    pieces: tuple[Piece, ...]


def _key(href: str, fragment: str | None) -> str:
    return href if fragment is None else f"{href}#{fragment}"


def _file_title(href: str) -> str:
    return posixpath.splitext(posixpath.basename(href))[0]


def _whole_file(href: str) -> Planned:
    return Planned(_file_title(href), href, (Piece(href, None, None),))


def plan_chapters(
    spine: list[str],
    toc: list[tuple[str, str, str | None]],
    anchors: dict[str, list[str]],
) -> list[Planned]:
    index = {href: i for i, href in enumerate(spine)}

    on_spine: list[tuple[str, str, str | None]] = []
    off_spine: list[tuple[str, str, str | None]] = []
    for title, href, fragment in toc:
        if fragment is not None and fragment not in anchors.get(href, []):
            fragment = None
        (on_spine if href in index else off_spine).append((title, href, fragment))

    def order(entry: tuple[str, str, str | None]) -> tuple[int, int]:
        _, href, fragment = entry
        return index[href], anchors[href].index(fragment) if fragment is not None else -1

    starts: list[tuple[str, str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for entry in sorted(on_spine, key=order):  # stable: TOC order breaks ties
        if entry[1:] in seen:
            continue
        seen.add(entry[1:])
        starts.append(entry)

    planned: list[Planned] = []
    if not starts:
        planned.extend(_whole_file(href) for href in spine)
    else:
        first_href, first_frag = starts[0][1], starts[0][2]
        planned.extend(_whole_file(href) for href in spine[: index[first_href]])
        if first_frag is not None:
            planned.append(Planned(
                _file_title(first_href), first_href, (Piece(first_href, None, first_frag),),
            ))

    for i, (title, href, frag) in enumerate(starts):
        if i + 1 == len(starts):
            pieces = [Piece(href, frag, None)]
            pieces += [Piece(h, None, None) for h in spine[index[href] + 1:]]
        else:
            _, next_href, next_frag = starts[i + 1]
            if next_href == href:
                pieces = [Piece(href, frag, next_frag)]
            else:
                pieces = [Piece(href, frag, None)]
                pieces += [
                    Piece(h, None, None) for h in spine[index[href] + 1: index[next_href]]
                ]
                if next_frag is not None:
                    pieces.append(Piece(next_href, None, next_frag))
        planned.append(Planned(title, _key(href, frag), tuple(pieces)))

    seen_off: set[tuple[str, str | None]] = set()
    for title, href, frag in off_spine:
        if (href, frag) in seen_off:
            continue
        seen_off.add((href, frag))
        planned.append(Planned(title, _key(href, frag), (Piece(href, frag, None),)))
    return planned


def units(soup: BeautifulSoup, start: str | None, end: str | None) -> list[Tag]:
    """The reader's paragraph/image units between two element ids, in document order."""
    position = {id(tag): n for n, tag in enumerate(soup.find_all(True))}
    unit_list = soup.find_all(["p", "image"])
    unit_ids = {id(tag) for tag in unit_list}

    def boundary(element_id: str | None, default: int) -> int:
        if element_id is None:
            return default
        el = soup.find(id=element_id)
        if el is None:
            return default
        node = el
        while node is not None and id(node) not in unit_ids:
            node = node.parent
        return position[id(node if node is not None else el)]

    low = boundary(start, -1)
    high = boundary(end, len(position) + 1)
    return [t for t in unit_list if low <= position[id(t)] < high]
