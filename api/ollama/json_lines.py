"""Pull finished {"id","text"} objects out of a streamed `{"lines":[...]}` answer."""

from __future__ import annotations

import json


class LineScanner:
    def __init__(self) -> None:
        self._buf = ""
        self._pos = 0
        self._depth = 0
        self._in_string = False
        self._escape = False
        self._start = 0

    def feed(self, text: str) -> list[tuple[int, str]]:
        self._buf += text
        out: list[tuple[int, str]] = []
        while self._pos < len(self._buf):
            c = self._buf[self._pos]
            if self._in_string:
                if self._escape:
                    self._escape = False
                elif c == "\\":
                    self._escape = True
                elif c == '"':
                    self._in_string = False
            elif c == '"':
                self._in_string = True
            elif c == "{":
                self._depth += 1
                if self._depth == 2:
                    self._start = self._pos
            elif c == "}":
                self._depth -= 1
                if self._depth == 1:
                    line = self._parse(self._buf[self._start:self._pos + 1])
                    if line is not None:
                        out.append(line)
            self._pos += 1
        return out

    @staticmethod
    def _parse(raw: str) -> tuple[int, str] | None:
        try:
            obj = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(obj, dict):
            return None
        n, t = obj.get("id"), obj.get("text")
        if isinstance(n, int) and not isinstance(n, bool) and isinstance(t, str):
            return n, t
        return None
