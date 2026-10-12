import json

from api.models import MtCache
from api.mt import cache
from api.mt.base import sse
from api.mt.languages import LANGUAGES, deepl_code, display


def test_sse_frames_json_so_newlines_cannot_break_framing():
    frame = sse(("chunk", {"text": "a\n\nevent: x"}))
    assert frame.startswith("event: chunk\ndata: ") and frame.endswith("\n\n")
    assert frame.count("\n\n") == 1
    assert json.loads(frame.split("data: ", 1)[1]) == {"text": "a\n\nevent: x"}


def test_languages_ported_from_the_desktop():
    assert LANGUAGES["ja"] == "Japanese" and LANGUAGES["zh-CN"] == "Chinese Simplified"
    assert LANGUAGES["es"] == "Spanish"
    assert (deepl_code("en"), deepl_code("ja"), deepl_code("pt"), deepl_code("la")) == (
        "EN-US", "JA", "PT-PT", ""
    )
    assert display("ja") == "Japanese (ja)"


def test_cache_round_trip_and_first_write_wins(db):
    assert cache.get(db, "deepl", "ja", "en", "猫") is None
    cache.put(db, "deepl", "ja", "en", "猫", "cat")
    cache.put(db, "deepl", "ja", "en", "猫", "kitty")
    assert cache.get(db, "deepl", "ja", "en", "猫") == "cat"
    assert cache.get(db, "deepl", "ja", "de", "猫") is None
    row = db.query(MtCache).one()
    assert row.source_sha256 == cache.key_text("猫") and len(row.source_sha256) == 64
