from datetime import UTC, datetime

import pytest

from api.core.wp import (
    _ILLUS_BATCH_BYTES,
    build_chapter_body,
    build_illustrations_payloads,
    build_image_payload,
    build_payload,
    compute_auto_schedule,
    compute_password_fields,
    get_first_line,
    resolve_wp_password_enabled,
    site_base,
    slugify,
    toc_page_url,
)


def test_slugify_basic():
    assert slugify("Sword of the Wanderer") == "sword-of-the-wanderer"

def test_slugify_special_chars():
    assert slugify("Héros & Villain!") == "hros-villain"

def test_slugify_extra_dashes():
    assert slugify("  hello   world  ") == "hello-world"

def test_build_chapter_body_basic():
    lines = [
        {"translated_text": "Hello world"},
        {"translated_text": ""},
        {"translated_text": "Second line"},
    ]
    result = build_chapter_body(lines)
    assert result == "<p>Hello world</p>\n<p>Second line</p>"

def test_build_chapter_body_all_empty():
    lines = [{"translated_text": ""}, {"translated_text": "   "}]
    assert build_chapter_body(lines) == ""

def test_build_chapter_body_merges_continuations():
    lines = [
        {"prefix": "%", "translated_text": "「That makes it sound like all we do is sex."},
        {"prefix": "$", "translated_text": "That's not our relationship」"},
        {"prefix": "%", "translated_text": "Mikiri shows a wide smile."},
    ]
    result = build_chapter_body(lines)
    assert result == (
        "<p>「That makes it sound like all we do is sex. That's not our relationship」</p>\n"
        "<p>Mikiri shows a wide smile.</p>"
    )

def test_get_first_line_skips_continuation():
    lines = [
        {"prefix": "$", "translated_text": "orphan continuation"},
        {"prefix": "%", "translated_text": "Real first"},
    ]
    assert get_first_line(lines) == "Real first"

def test_get_first_line_returns_first_nonempty():
    lines = [
        {"translated_text": ""},
        {"translated_text": "First real line"},
        {"translated_text": "Second line"},
    ]
    assert get_first_line(lines) == "First real line"

def test_get_first_line_all_empty():
    lines = [{"translated_text": ""}, {"translated_text": "   "}]
    assert get_first_line(lines) == ""

def _sample_meta():
    doc_meta = {
        "series_title": "Sword of the Wanderer",
        "series_order": 1,
        "chapter_title": "The Beginning",
    }
    series_meta = {
        "series_slug": "sword-of-the-wanderer",
        "series_title_short": "SotW",
        "syosetu_url": "https://ncode.syosetu.com/n1234ab/",
    }
    lines = [{"translated_text": "Hello"}, {"translated_text": "World"}]
    return doc_meta, series_meta, lines

def test_build_payload_chapter():
    doc_meta, series_meta, lines = _sample_meta()
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123")
    assert payload["api_key"] == "key123"
    assert payload["series_title"] == "Sword of the Wanderer"
    assert payload["series_slug"] == "sword-of-the-wanderer"
    assert payload["series_title_short"] == "SotW"
    assert payload["series_link"] == "https://ncode.syosetu.com/n1234ab/"
    assert payload["chapter_index"] == 1
    assert payload["chapter_title"] == "SotW The Beginning"
    assert payload["chapter_body"].startswith("<p>Hello</p>\n<p>World</p>")
    assert "Translation Assistant" in payload["chapter_body"]
    assert payload["first_line"] == "Hello"

def test_build_payload_synopsis_omits_first_line():
    doc_meta, series_meta, lines = _sample_meta()
    doc_meta["series_order"] = 0
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123")
    assert "first_line" not in payload

def test_build_payload_attribution_disabled():
    doc_meta, series_meta, lines = _sample_meta()
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123", attribution=False)
    assert payload["chapter_body"] == "<p>Hello</p>\n<p>World</p>"

def test_build_payload_missing_series_slug_raises():
    doc_meta, series_meta, lines = _sample_meta()
    series_meta["series_slug"] = ""
    with pytest.raises(ValueError, match="series_slug"):
        build_payload(doc_meta, series_meta, lines, api_key="key123")

def test_build_payload_missing_series_title_short_raises():
    doc_meta, series_meta, lines = _sample_meta()
    series_meta["series_title_short"] = ""
    with pytest.raises(ValueError, match="series_title_short"):
        build_payload(doc_meta, series_meta, lines, api_key="key123")




@pytest.mark.parametrize("chapter_index,unlock_after,expect_pw,expect_unlock", [
    (0,  3, False, None),   # synopsis — always free
    (1,  3, False, None),   # within free window
    (3,  3, False, None),   # boundary — still free
    (4,  3, True,  None),   # first locked chapter, no unlock yet
    (6,  3, True,  None),   # 6-3=3, 3>3 is False — no unlock
    (7,  3, True,  4),      # 7-3=4, 4>3 — unlock ch4
    (11, 5, True,  6),      # 11-5=6, 6>5 — unlock ch6
])
def test_compute_password_fields(chapter_index, unlock_after, expect_pw, expect_unlock):
    pw, unlock_idx = compute_password_fields(chapter_index, unlock_after)
    assert (pw is not None) == expect_pw
    assert unlock_idx == expect_unlock
    if expect_pw:
        assert len(pw) > 0


def test_compute_password_fields_password_is_random():
    pw1, _ = compute_password_fields(5, 3)
    pw2, _ = compute_password_fields(5, 3)
    assert pw1 != pw2


def test_compute_password_fields_password_is_alphanumeric():
    import string
    pw, _ = compute_password_fields(5, 3)
    assert pw is not None
    assert len(pw) == 12
    assert all(c in string.ascii_letters + string.digits for c in pw)


def test_build_payload_includes_password_and_unlock():
    doc_meta = {"series_title": "T", "series_order": 7, "chapter_title": "Ch7"}
    series_meta = {"series_slug": "t", "series_title_short": "T", "syosetu_url": ""}
    lines = [{"prefix": "%", "translated_text": "Hello"}]
    payload = build_payload(doc_meta, series_meta, lines, "key",
                            password="abc123", unlock_chapter_index=4)
    assert payload["password"] == "abc123"
    assert payload["unlock_chapter_index"] == 4


def test_build_payload_omits_password_fields_when_none():
    doc_meta = {"series_title": "T", "series_order": 1, "chapter_title": "Ch1"}
    series_meta = {"series_slug": "t", "series_title_short": "T", "syosetu_url": ""}
    lines = [{"prefix": "%", "translated_text": "Hello"}]
    payload = build_payload(doc_meta, series_meta, lines, "key")
    assert "password" not in payload
    assert "unlock_chapter_index" not in payload


def test_build_payload_includes_previous_chapter_index_when_differs():
    doc_meta, series_meta, lines = _sample_meta()
    doc_meta["series_order"] = 3
    payload = build_payload(
        doc_meta, series_meta, lines, api_key="key123", previous_chapter_index=2,
    )
    assert payload["previous_chapter_index"] == 2


def test_build_payload_omits_previous_chapter_index_when_same():
    doc_meta, series_meta, lines = _sample_meta()
    doc_meta["series_order"] = 1
    payload = build_payload(
        doc_meta, series_meta, lines, api_key="key123", previous_chapter_index=1,
    )
    assert "previous_chapter_index" not in payload


def test_build_payload_omits_previous_chapter_index_when_none():
    doc_meta, series_meta, lines = _sample_meta()
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123")
    assert "previous_chapter_index" not in payload


# ---------------------------------------------------------------------------
# resolve_wp_password_enabled — series override vs. global fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("series", "global_on", "expected"), [
    (True, False, True), (False, True, False), (None, True, True), (None, False, False),
])
def test_password_resolution_series_override_then_global(series, global_on, expected):
    assert resolve_wp_password_enabled(series, global_enabled=global_on) is expected


@pytest.mark.parametrize("url", [
    "https://example.com", "https://example.com/",
    "https://example.com/wp-json/ta-publisher/v1/publish",
    "https://example.com/wp-json/ta-publisher/v1/publish/",
])
def test_site_base_strips_the_publish_path_and_slashes(url):
    assert site_base(url) == "https://example.com"




# ---------------------------------------------------------------------------



def test_toc_page_url_from_bare_site():
    assert toc_page_url("https://site.com", "my-series") == "https://site.com/my-series/"


def test_toc_page_url_strips_endpoint_path_and_trailing_slash():
    assert (
        toc_page_url("https://site.com/wp-json/ta-publisher/v1/publish/", "my-series")
        == "https://site.com/my-series/"
    )


# ---------------------------------------------------------------------------
# compute_auto_schedule
# ---------------------------------------------------------------------------





def test_auto_schedule_joins_same_day_when_capacity_left():
    dt = compute_auto_schedule(
        "2026-07-20T12:00:00Z", ["2026-07-20T12:00:00Z"], 2, "20:00", tz=UTC
    )
    assert dt == datetime(2026, 7, 20, 13, 0)


def test_auto_schedule_staggers_from_latest_same_day_slot():
    dt = compute_auto_schedule(
        "2026-07-20T12:00:00Z",
        ["2026-07-20T12:00:00Z", "2026-07-20T15:00:00Z"],
        3, "20:00", tz=UTC,
    )
    assert dt == datetime(2026, 7, 20, 16, 0)


def test_auto_schedule_overflows_to_next_day_at_default_time():
    dt = compute_auto_schedule(
        "2026-07-20T12:00:00Z",
        ["2026-07-20T10:00:00Z", "2026-07-20T12:00:00Z"],
        2, "20:00", tz=UTC,
    )
    assert dt == datetime(2026, 7, 21, 20, 0)


def test_auto_schedule_overflow_falls_back_to_prev_time_without_default():
    dt = compute_auto_schedule(
        "2026-07-20T12:30:00Z", ["2026-07-20T12:30:00Z"], 1, "", tz=UTC
    )
    assert dt == datetime(2026, 7, 21, 12, 30)


def test_auto_schedule_bad_default_time_falls_back_to_prev_time():
    dt = compute_auto_schedule(
        "2026-07-20T12:30:00Z", ["2026-07-20T12:30:00Z"], 1, "bogus", tz=UTC
    )
    assert dt == datetime(2026, 7, 21, 12, 30)


def test_auto_schedule_empty_dates_uses_prev_plus_hour():
    dt = compute_auto_schedule("2026-07-20T12:00:00Z", [], 1, "20:00", tz=UTC)
    assert dt == datetime(2026, 7, 20, 13, 0)


def test_auto_schedule_ignores_other_days_in_count():
    dt = compute_auto_schedule(
        "2026-07-20T12:00:00Z",
        ["2026-07-19T12:00:00Z", "2026-07-20T12:00:00Z", "2026-07-21T12:00:00Z"],
        2, "20:00", tz=UTC,
    )
    assert dt == datetime(2026, 7, 20, 13, 0)


# ---------------------------------------------------------------------------
# build_image_payload — anchor-to-paragraph mapping
# ---------------------------------------------------------------------------

def test_build_image_payload_simple_paragraph_boundary():
    lines = [
        {"prefix": "%", "translated_text": "First paragraph."},
        {"prefix": "%", "translated_text": "Second paragraph."},
    ]
    images = [
        {"id": 1, "anchor_position": 1, "src_path": "img1.jpg", "data": b"JPEGDATA"},
    ]
    result = build_image_payload(lines, images)
    assert result == [
        {
            "position": 1,
            "filename": "img1.jpg",
            "mime": "image/jpeg",
            "data_base64": "SlBFR0RBVEE=",
        }
    ]

def test_build_image_payload_accounts_for_sentence_split():
    # One source paragraph split into two sentence lines (% + $) — an
    # image anchored after raw_lines[2] must land at paragraph position 1
    # (after the merged first <p>), not 2.
    lines = [
        {"prefix": "%", "translated_text": "Sentence one."},
        {"prefix": "$", "translated_text": "Sentence two, same paragraph."},
        {"prefix": "%", "translated_text": "Next paragraph."},
    ]
    images = [
        {"id": 5, "anchor_position": 2, "src_path": "img2.png", "data": b"PNGDATA"},
    ]
    result = build_image_payload(lines, images)
    assert result[0]["position"] == 1

def test_build_image_payload_before_first_and_after_last():
    lines = [
        {"prefix": "%", "translated_text": "Only paragraph."},
    ]
    images = [
        {"id": 2, "anchor_position": 1, "src_path": "after.jpg", "data": b"A"},
        {"id": 1, "anchor_position": 0, "src_path": "before.jpg", "data": b"B"},
    ]
    result = build_image_payload(lines, images)
    assert [im["filename"] for im in result] == ["before.jpg", "after.jpg"]
    assert result[0]["position"] == 0
    assert result[1]["position"] == 1

def test_build_image_payload_ties_break_on_id():
    lines = [{"prefix": "%", "translated_text": "Paragraph."}]
    images = [
        {"id": 9, "anchor_position": 1, "src_path": "second.jpg", "data": b"X"},
        {"id": 3, "anchor_position": 1, "src_path": "first.jpg", "data": b"Y"},
    ]
    result = build_image_payload(lines, images)
    assert [im["filename"] for im in result] == ["first.jpg", "second.jpg"]

def test_build_image_payload_empty_images():
    assert build_image_payload([{"translated_text": "x"}], []) == []


def test_build_payload_includes_images_when_present():
    doc_meta, series_meta, lines = _sample_meta()
    images = [{"id": 1, "anchor_position": 1, "src_path": "a.jpg", "data": b"X"}]
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123", images=images)
    assert payload["images"] == [
        {"position": 1, "filename": "a.jpg", "mime": "image/jpeg", "data_base64": "WA=="}
    ]

def test_build_payload_omits_images_when_absent():
    doc_meta, series_meta, lines = _sample_meta()
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123")
    assert "images" not in payload

def test_build_payload_includes_cover_when_present():
    doc_meta, series_meta, lines = _sample_meta()
    cover = {"src_path": "cover.png", "data": b"COVERBYTES"}
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123", cover=cover)
    assert payload["cover"]["filename"] == "cover.png"
    assert payload["cover"]["mime"] == "image/png"

def test_build_payload_omits_cover_when_absent():
    doc_meta, series_meta, lines = _sample_meta()
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123")
    assert "cover" not in payload

def test_build_payload_omits_cover_past_chapter_one():
    doc_meta, series_meta, lines = _sample_meta()
    doc_meta["series_order"] = 2
    cover = {"src_path": "cover.png", "data": b"COVERBYTES"}
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123", cover=cover)
    assert "cover" not in payload


def test_build_payload_includes_volume_title():
    doc_meta, series_meta, lines = _sample_meta()
    doc_meta["volume_title"] = "Volume 2: The Long Road"
    payload = build_payload(doc_meta, series_meta, lines, api_key="key123")
    assert payload["volume_title"] == "Volume 2: The Long Road"


def test_build_payload_omits_blank_volume_title():
    doc_meta, series_meta, lines = _sample_meta()
    assert "volume_title" not in doc_meta  # helper has no volume_title key
    assert "volume_title" not in build_payload(doc_meta, series_meta, lines, api_key="key123")
    doc_meta["volume_title"] = ""
    assert "volume_title" not in build_payload(doc_meta, series_meta, lines, api_key="key123")




def _illus_meta():
    doc_meta = {"series_title": "Sword of the Wanderer", "volume_title": "Volume 1"}
    series_meta = {
        "series_slug": "sword-of-the-wanderer",
        "series_title_short": "SotW",
        "syosetu_url": "https://ncode.syosetu.com/n1234ab/",
    }
    return doc_meta, series_meta


def _img(name, nbytes):
    return {"src_path": name, "data": b"x" * nbytes}


def test_illus_payloads_single_batch_when_small():
    doc_meta, series_meta = _illus_meta()
    out = build_illustrations_payloads(
        doc_meta, series_meta, [_img("a.png", 10), _img("b.png", 10)], api_key="K"
    )
    assert len(out) == 1
    assert out[0]["mode"] == "replace"
    assert out[0]["volume_title"] == "Volume 1"
    assert out[0]["series_link"] == "https://ncode.syosetu.com/n1234ab/"
    assert [i["filename"] for i in out[0]["images"]] == ["a.png", "b.png"]
    assert "position" not in out[0]["images"][0]


def test_illus_payloads_splits_over_budget():
    doc_meta, series_meta = _illus_meta()
    # each image base64-inflates ~4/3; make three that each blow ~half the budget
    half = int(_ILLUS_BATCH_BYTES * 0.5)
    imgs = [_img(f"{i}.png", half) for i in range(3)]
    out = build_illustrations_payloads(doc_meta, series_meta, imgs, api_key="K")
    assert len(out) >= 2
    assert out[0]["mode"] == "replace"
    assert all(p["mode"] == "append" for p in out[1:])
    seen = [i["filename"] for p in out for i in p["images"]]
    assert seen == ["0.png", "1.png", "2.png"]


def test_illus_payloads_cover_only_on_first_batch():
    doc_meta, series_meta = _illus_meta()
    half = int(_ILLUS_BATCH_BYTES * 0.5)
    imgs = [_img(f"{i}.png", half) for i in range(3)]
    out = build_illustrations_payloads(
        doc_meta, series_meta, imgs, api_key="K", cover=_img("cover.png", 10)
    )
    assert "cover" in out[0]
    assert out[0]["cover"]["filename"] == "cover.png"
    assert all("cover" not in p for p in out[1:])


def test_illus_payloads_omits_volume_title_when_blank():
    doc_meta, series_meta = _illus_meta()
    doc_meta["volume_title"] = ""
    out = build_illustrations_payloads(doc_meta, series_meta, [_img("a.png", 10)], api_key="K")
    assert "volume_title" not in out[0]


def test_illus_payloads_missing_series_link_key_ok():
    doc_meta, series_meta = _illus_meta()
    del series_meta["syosetu_url"]
    out = build_illustrations_payloads(doc_meta, series_meta, [_img("a.png", 10)], api_key="K")
    assert out[0]["series_link"] == ""


def test_illus_payloads_requires_slug_and_short_title():
    doc_meta, series_meta = _illus_meta()
    with pytest.raises(ValueError):
        build_illustrations_payloads(
            doc_meta, {"series_slug": "", "series_title_short": "X"},
            [_img("a.png", 1)], api_key="K"
        )
    with pytest.raises(ValueError):
        build_illustrations_payloads(
            doc_meta, {"series_slug": "x", "series_title_short": ""},
            [_img("a.png", 1)], api_key="K"
        )


def test_illus_payloads_cover_only_volume():
    doc_meta, series_meta = _illus_meta()
    out = build_illustrations_payloads(
        doc_meta, series_meta, [], api_key="K", cover=_img("cover.png", 10)
    )
    assert len(out) == 1
    assert out[0]["mode"] == "replace"
    assert out[0]["images"] == []
    assert out[0]["cover"]["filename"] == "cover.png"


def test_illus_payloads_big_cover_splits_before_first_image():
    doc_meta, series_meta = _illus_meta()
    big = int(_ILLUS_BATCH_BYTES * 0.6)
    out = build_illustrations_payloads(
        doc_meta, series_meta, [_img("a.png", big), _img("b.png", 10)],
        api_key="K", cover=_img("cover.png", big),
    )
    assert len(out) == 2
    assert out[0]["mode"] == "replace" and out[0]["images"] == [] and "cover" in out[0]
    assert [i["filename"] for i in out[1]["images"]] == ["a.png", "b.png"]
    assert all("cover" not in p for p in out[1:])