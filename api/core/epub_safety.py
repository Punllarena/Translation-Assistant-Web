"""Archive-safety checks and memory limits for reading EPUBs (ours, spec §6; not in the
desktop). epub_read.py reads every entry through these."""
import zipfile
import zlib
from contextlib import contextmanager

MAX_UNCOMPRESSED = 256 * 1024 * 1024  # cap what a book may expand to
MAX_TEXT_ENTRY = 4 * 1024 * 1024  # one XML/XHTML file BeautifulSoup will parse
# ponytail: 32 MiB of XML/XHTML parsed per open_book; giant omnibus EPUBs are refused
MAX_PARSED_TEXT = 32 * 1024 * 1024
# chapters per book (open_book refuses more; the TOC may hold 4x as many entries). The
# import form posts one field per chapter and Starlette's multipart max_fields is 1000.
MAX_CHAPTERS = 900

_MB = 1024 * 1024


class EpubError(ValueError):
    """Raised when an EPUB file can't be parsed."""


class EpubBudgetExceeded(EpubError):
    """The caller's byte budget would be overdrawn; the whole import stops."""


class TextBudgetExceeded(EpubError):
    """open_book's parsed-text total is spent; never skipped like one bad chapter."""


def check_archive(zf: zipfile.ZipFile) -> None:
    """Refuse absolute and parent-relative entry names and oversized archives
    (spec §6). Entries are only ever read by name, never extracted to disk, but a
    book that names one is not one we should trust with anything else."""
    total = 0
    for info in zf.infolist():
        parts = info.filename.replace("\\", "/").split("/")
        if info.filename.startswith(("/", "\\")) or ".." in parts:
            raise EpubError(f"unsafe path in EPUB: {info.filename!r}")
        total += info.file_size
        if total > MAX_UNCOMPRESSED:
            raise EpubError(f"EPUB expands to more than {MAX_UNCOMPRESSED // _MB} MB")


@contextmanager
def unreadable():
    """Hostile but valid zips fail in many ways below EpubError (bad encoding, a corrupt
    deflate stream, an encrypted entry, a manifest item without href); callers only ever
    handle EpubError."""
    try:
        yield
    except (KeyError, UnicodeDecodeError, zlib.error, RuntimeError, NotImplementedError,
            EOFError, zipfile.BadZipFile) as exc:
        raise EpubError(f"Not a readable EPUB: {type(exc).__name__}") from exc


def read_text(zf: zipfile.ZipFile, path: str, parsed: list[int] | None = None) -> str:
    """One XML/XHTML entry as text. ``parsed`` (one-item list, mutated) totals the
    bytes read so far in one open_book call, against MAX_PARSED_TEXT."""
    try:
        size = zf.getinfo(path).file_size
    except KeyError as exc:
        raise EpubError(f"Missing file in EPUB: {path}") from exc
    if size > MAX_TEXT_ENTRY:
        raise EpubError(f"{path} is larger than {MAX_TEXT_ENTRY // _MB} MB")
    if parsed is not None:
        parsed[0] += size
        if parsed[0] > MAX_PARSED_TEXT:
            raise TextBudgetExceeded(
                f"EPUB text is larger than {MAX_PARSED_TEXT // _MB} MB in total")
    return zf.read(path).decode("utf-8")


def charge(budget: list[int] | None, size: int) -> None:
    """Take ``size`` bytes from ``budget`` (remaining bytes, mutated), refusing first."""
    if budget is None:
        return
    if size > budget[0]:
        raise EpubBudgetExceeded("over budget")
    budget[0] -= size
