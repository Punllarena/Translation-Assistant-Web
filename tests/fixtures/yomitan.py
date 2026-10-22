"""Build small Yomitan dictionary zips for tests. The JMdict rows are real (EDRDG, CC BY-SA;
see yomitan_README.md); the 新和英 look-alike rows live in the tests and are invented."""
import json
import zipfile
from pathlib import Path


def make_zip(
    path, index: dict, banks: dict[str, list], extra: dict[str, bytes] | None = None
) -> Path:
    path = Path(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.json", json.dumps(index, ensure_ascii=False))
        for name, rows in banks.items():
            zf.writestr(name, json.dumps(rows, ensure_ascii=False))
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return path


JMDICT_INDEX = {
    "title": "JMdict [2026-10-21]",
    "format": 3,
    "revision": "JMdict.2026-10-21",
    "sequenced": True,
    "author": "yomitan-import",
    "url": "https://github.com/yomidevs/yomitan-import",
    "description": "",
    "attribution": "This publication has included material from the JMdict (EDICT, etc.) "
    "dictionary files in accordance with the licence provisions of the Electronic Dictionaries "
    "Research Group. See http://www.edrdg.org/",
    "indexUrl": "https://github.com/yomidevs/jmdict-yomitan/releases/latest/download/JMdict_english.json",
}


def _ul(items: list, marker: str) -> list:
    return [{
        "type": "structured-content",
        "content": {
            "tag": "ul", "lang": "en", "style": {"listStyleType": "circle"},
            "data": {"content": marker},
            "content": items[0] if len(items) == 1 else items,
        },
    }]


def _cell(tag: str, text: str, align: str = "center") -> dict:
    return {"tag": tag, "content": text, "style": {"textAlign": align}}


def _tr(*cells: dict) -> dict:
    return {"tag": "tr", "content": list(cells)}


JMDICT_ROWS = [
    ["ヾ", "ヾ", "unc", "", -200,
     _ul([{"tag": "li", "content": "voiced repetition mark in katakana"}], "infoGlossary"),
     1000010, ""],
    ["〃", "おなじ", "forms", "", -201, [{
        "type": "structured-content",
        "content": {"tag": "table", "data": {"content": "formsTable"}, "content": [
            _tr(_cell("th", ""), _cell("th", "〃")),
            _tr(_cell("th", "おなじ", "left"), _cell("td", "㊒")),
        ]},
    }], 1000040, ""],
    ["食べる", "たべる", "1 v1 vt", "v1", 1999800,
     _ul([{"tag": "li", "content": "to eat"}], "glossary"), 1358280,
     "⭐ ichi news13k"],
    ["食べる", "たべる", "2 v1 vt", "v1", 1999799,
     _ul([{"tag": "li", "content": "to live on (e.g. a salary)"},
          {"tag": "li", "content": "to live off"},
          {"tag": "li", "content": "to subsist on"}], "glossary"), 1358280,
     "⭐ ichi news13k"],
]

JMDICT_TAGS = [
    ["v1", "partOfSpeech", -3, "Ichidan verb", 0],
    ["vt", "partOfSpeech", -3, "transitive verb", 0],
    ["forms", "", 0, "other surface forms and readings", 0],
]
