"""Read Postgres COPY's CSV keeping NULL apart from the empty string.

COPY writes NULL as an unquoted empty field and ``''`` as ``""``. ``csv.reader`` only tells
them apart from Python 3.13 (``QUOTE_NOTNULL``); the image runs 3.12, so this parses it.
"""


def rows(text: str) -> list[list[str | None]]:
    out: list[list[str | None]] = []
    row: list[str | None] = []
    field: list[str] = []
    quoted = in_quotes = False
    i, n = 0, len(text)

    def end_field() -> None:
        nonlocal quoted
        row.append("".join(field) if field or quoted else None)
        field.clear()
        quoted = False

    while i < n:
        c = text[i]
        if in_quotes:
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field.append('"')
                    i += 1
                else:
                    in_quotes = False
            else:
                field.append(c)
        elif c == '"':
            in_quotes = quoted = True
        elif c == ",":
            end_field()
        elif c in "\r\n":
            if c == "\r" and i + 1 < n and text[i + 1] == "\n":
                i += 1
            end_field()
            out.append(row)
            row = []
        else:
            field.append(c)
        i += 1
    if in_quotes:
        raise ValueError("unterminated quoted field")
    if field or quoted or row:
        end_field()
        out.append(row)
    return out
