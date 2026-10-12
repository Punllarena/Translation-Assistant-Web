"""Qt-free text logic ported verbatim from the desktop ``translation_assistant/core.py``
(commit f1a96ce). Only the functions phases 2-6 use are here; later phases append theirs.
No database imports: callers convert rows at the edge (see api/library.py)."""

import re

SEPARATOR = "---SEPERATOR---"


def parse_file_content(text: str) -> tuple[list[str], list[str], str]:
    """
    Split a SEPERATOR-format file into (raw_lines, translated_lines, raw_section).

    raw_section is the verbatim text before the separator — passed unchanged to
    save_file so the source text is never touched on a save round-trip.

    Raises ValueError if the separator is absent.
    """
    parts = text.split(SEPARATOR, 1)
    if len(parts) != 2:
        raise ValueError(f"File is missing the '{SEPARATOR}' marker.")

    raw_section = parts[0]
    translated_half = parts[1]

    # Normalise line endings and split raw section into lines
    raw_lines = [line.rstrip("\r") for line in raw_section.split("\n")]

    # The translated half opens with the newline immediately after the separator
    # (VB: Mid(str, 3, ...) skips the leading \r\n).  Drop only that first blank.
    t_lines = [line.rstrip("\r") for line in translated_half.split("\n")]
    if t_lines and t_lines[0] == "":
        t_lines.pop(0)

    # Drop trailing empty lines from raw; keep both arrays the same length
    while raw_lines and not raw_lines[-1]:
        raw_lines.pop()

    # Pad / truncate translated array to match raw
    if len(t_lines) < len(raw_lines):
        t_lines.extend("" for _ in range(len(raw_lines) - len(t_lines)))
    translated_lines = t_lines[: len(raw_lines)]

    return raw_lines, translated_lines, raw_section


def build_new_file(raw_input: str) -> str:
    """
    Convert a block of raw Japanese/Chinese text into the ---SEPERATOR--- format.

    Multi-sentence lines (split on 。) produce:
        %first_sentence。
        $continuation。
        ...
    Single-sentence lines produce a single %line entry.

    Equivalent to frmNew.btnCreate_Click.
    """
    # VB: Split(text, vbCr) then strip vbLf from each piece.
    # splitlines() handles \r\n, \n, and \r equivalently.
    lines = raw_input.splitlines()

    raw_parts: list[str] = []
    blank_count = 0  # one blank translated line per output line

    for line in lines:
        pieces = line.split("。")
        # VB: senCount = Split(line, "。").GetUpperBound(0) = len(pieces) - 1
        sen_count = len(pieces) - 1

        if sen_count < 1:
            # No 。 — single entry prefixed with %
            raw_parts.append(f"%{line}")
            blank_count += 1
            continue

        # Remove empty pieces produced by trailing 。 (VB: RemoveAll IsNullOrEmpty)
        non_empty = [p for p in pieces if p]
        if not non_empty:
            raw_parts.append(f"%{line}")
            blank_count += 1
            continue

        # First piece always prefixed with % and given its 。 back
        raw_parts.append(f"%{non_empty[0]}。")
        blank_count += 1

        for x, piece in enumerate(non_empty[1:], start=1):
            is_last = x == len(non_empty) - 1
            # Add 。 back unless this is the last piece of a line that didn't end with 。
            if not is_last or (is_last and line.endswith("。")):
                ender = "。"
            else:
                ender = ""
            raw_parts.append(f"${piece}{ender}")
            blank_count += 1

    raw_section = "\n".join(raw_parts) + "\n"
    blank_section = "\n" * blank_count
    return raw_section + "\n" + SEPARATOR + "\n" + blank_section


def lines_to_db_rows(
    raw_lines: list[str], translated_lines: list[str]
) -> list[dict]:
    """Convert in-memory arrays to the shape expected by db.save_lines()."""
    rows = []
    for i, ln in enumerate(raw_lines):
        if not ln:
            prefix, raw_text = "", ""
        elif ln[0] in ("%", "$"):
            prefix, raw_text = ln[0], ln[1:]
        else:
            prefix, raw_text = "%", ln
        rows.append({
            "line_number": i,
            "prefix": prefix,
            "raw_text": raw_text,
            "translated_text": translated_lines[i] if i < len(translated_lines) else "",
        })
    return rows


def db_rows_to_arrays(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Convert db.get_lines() output back to (raw_lines, translated_lines).

    Rows are sorted by line_number. Prefixes are prepended to raw_text for
    compatibility with the existing parse/display functions.
    """
    sorted_rows = sorted(rows, key=lambda r: r["line_number"])
    raw_lines = [r["prefix"] + r["raw_text"] for r in sorted_rows]
    translated_lines = [r["translated_text"] for r in sorted_rows]
    return raw_lines, translated_lines


def line_has_content(raw: str) -> bool:
    """True if a raw line has translatable text (not a blank/marker-only line)."""
    return bool(raw.lstrip("%$").strip())


def calculate_progress(
    raw_lines: list[str], translated_lines: list[str]
) -> tuple[int, int]:
    """
    Return (completion_percent, word_count).

    completion_percent: lines with both raw and translated non-empty, expressed
    as a percentage of total non-empty raw lines.

    word_count: sum of token counts across all translated lines where tokens are
    split by a single space — matching VB's Split(str, " ").Count behaviour
    (empty tokens from leading / trailing spaces are included).
    """
    total_raw = sum(1 for r in raw_lines if line_has_content(r))
    if total_raw == 0:
        return 0, 0

    done = sum(
        1 for r, t in zip(raw_lines, translated_lines, strict=False)
        if line_has_content(r) and t
    )
    word_count = sum(len(t.split(" ")) for t in translated_lines)
    percent = int((done / total_raw) * 100)
    return percent, word_count


def build_markdown_translation(
    raw_lines: list[str],
    translated_lines: list[str],
    title: str = "",
) -> str:
    """
    Render translated lines as a plain Markdown document.

    Follows the same %/$ grouping as build_clipboard_output:
    consecutive $-prefixed lines merge with their % head.
    Untranslated groups are omitted. Empty raw lines become blank lines.
    """
    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n\n")
    count = 0
    n = len(raw_lines)
    while count < n:
        line = raw_lines[count]
        if line:
            group_size = 1
            while (count + group_size < n
                   and raw_lines[count + group_size].startswith("$")):
                group_size += 1
            translations = [translated_lines[count + x] for x in range(group_size)]
            text = " ".join(t for t in translations if t).strip()
            if text:
                parts.append(text + "\n\n")
            count += group_size
        else:
            parts.append("\n")
            count += 1
    return "".join(parts)


def build_markdown_ruby(
    raw_lines: list[str],
    translated_lines: list[str],
    title: str = "",
) -> str:
    """
    Render an HTML ruby-annotated Markdown document.

    Each %/$ group becomes <ruby>translation<rt>original</rt></ruby>.
    Groups with no translation emit the raw text without a ruby wrapper.
    """
    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n\n")
    count = 0
    n = len(raw_lines)
    while count < n:
        line = raw_lines[count]
        if line:
            group_size = 1
            while (count + group_size < n
                   and raw_lines[count + group_size].startswith("$")):
                group_size += 1
            raw_text = "".join(
                raw_lines[count + x].lstrip("%$") for x in range(group_size)
            )
            translations = [translated_lines[count + x] for x in range(group_size)]
            translation = " ".join(t for t in translations if t).strip()
            if raw_text:
                if translation:
                    parts.append(
                        f"<ruby>{translation}<rt>{raw_text}</rt></ruby>\n\n"
                    )
                else:
                    parts.append(f"{raw_text}\n\n")
            count += group_size
        else:
            parts.append("\n")
            count += 1
    return "".join(parts)


def natural_key(s: str) -> list:
    """Sort key that orders embedded numbers numerically ('ch2' < 'ch10')."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def sanitize_filename(name: str) -> str:
    """From the desktop ``ui/main_widget._sanitize_filename``: safe as one path component."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")


def replace_and_parse(
    text: str,
    glossary: list[tuple[str, str]],
    parse_chars: list[str],
) -> tuple[str, list[str], bool]:
    """
    Strip markers, apply glossary substitutions, and split into sentences.

    Returns (display_text, sentences, replaced) where:
    - display_text : the line with $ / % stripped and glossary applied
    - sentences    : sub-phrases split on the configured parse characters
    - replaced     : True if at least one glossary substitution was made
                     (the Ctrl+Left nav uses this to know whether a pre-
                     replacement state exists to revert to)
    """
    buf = text.replace("$", "").replace("%", "")

    replaced = False
    for phrase, translation in glossary:
        if phrase and phrase in buf:
            buf = buf.replace(phrase, translation)
            replaced = True

    # Split by each parse character; drop empty results (VB: RemoveEmptyEntries)
    sentences: list[str] = []
    if parse_chars:
        pattern = "|".join(re.escape(c) for c in parse_chars if c)
        if pattern:
            sentences = [s for s in re.split(pattern, buf) if s]
    if not sentences and buf:
        sentences = [buf]

    return buf, sentences, replaced


def split_parse_chars(setting: str) -> list[str]:
    """A profile's parse_chars setting as a list (desktop main_widget._update_parse_chars)."""
    return [c for c in setting.split(" ") if c]


def load_glossary(text: str) -> list[tuple[str, str]]:
    """From the desktop ``core.load_glossary``, taking the file's text instead of a path.

    Lines are "phrase,translation"; a missing translation is "". Blank lines are ignored.
    """
    result: list[tuple[str, str]] = []
    for line in text.removeprefix("﻿").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(",", 1)
        result.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return result


def needle_pattern(needle: str, case_sensitive: bool) -> re.Pattern[str]:
    """Find and replace in a series (desktop FindReplaceDialog): literal text, optionally
    ignoring case."""
    return re.compile(re.escape(needle), 0 if case_sensitive else re.IGNORECASE)


def replace_all(pattern: re.Pattern[str], text: str, replacement: str) -> str:
    """Every match replaced by `replacement` taken literally (no \\1 or $1 expansion)."""
    return pattern.sub(lambda _m: replacement, text)


# ---------------------------------------------------------------------------
# build_epub_content
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------


def build_epub_content(
    raw_lines: list[str], translated_lines: list[str], images: list[dict],
) -> list[tuple[str, str]]:
    """
    Returns ordered [("text", paragraph), ("image", src_path), ...]. Uses the
    same %/$ grouping and empty-group skipping as build_markdown_translation,
    merged with images at their anchor_position.
    images: [{"anchor_position": int, "src_path": str}, ...]. Callers pass
    them pre-sorted by (anchor_position, id) -- db.get_document_images()
    already returns that order -- so equal anchors here simply preserve
    input order (stable sort is not needed; we just iterate in order).
    """
    result: list[tuple[str, str]] = []
    count = 0
    n = len(raw_lines)
    img_idx = 0

    def _flush_images_up_to(position: int) -> None:
        nonlocal img_idx
        while img_idx < len(images) and images[img_idx]["anchor_position"] <= position:
            result.append(("image", images[img_idx]["src_path"]))
            img_idx += 1

    while count < n:
        line = raw_lines[count]
        if line:
            _flush_images_up_to(count)
            group_size = 1
            while (count + group_size < n
                   and raw_lines[count + group_size].startswith("$")):
                group_size += 1
            translations = [translated_lines[count + x] for x in range(group_size)]
            text = " ".join(t for t in translations if t).strip()
            if text:
                result.append(("text", text))
            count += group_size
        else:
            count += 1

    _flush_images_up_to(n)
    return result
