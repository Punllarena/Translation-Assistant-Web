from api.core.yomitan_gloss import MAX_DEPTH, meanings, short_gloss

# Real JMdict (CC BY-SA) 食べる sense 2 glossary, plus a sibling references list (ignored).
JMDICT_TABERU_2 = [
    {
        "content": [
            {
                "content": [
                    {"content": "to live on (e.g. a salary)", "tag": "li"},
                    {"content": "to live off", "tag": "li"},
                    {"content": "to subsist on", "tag": "li"},
                ],
                "data": {"content": "glossary"},
                "lang": "en",
                "style": {"listStyleType": "circle"},
                "tag": "ul",
            },
            {
                "content": {"content": "references", "tag": "li"},
                "data": {"content": "references"},
                "tag": "ul",
            },
        ],
        "type": "structured-content",
    }
]

# Real JMdict ヾ row: only an infoGlossary list, no glossary marker.
JMDICT_VOICED_REPETITION = [
    {
        "content": {
            "content": {"content": "voiced repetition mark in katakana", "tag": "li"},
            "data": {"content": "infoGlossary"},
            "lang": "en",
            "style": {"listStyleType": "'ℹ️ '"},
            "tag": "ul",
        },
        "type": "structured-content",
    }
]

UNMARKED = [
    {
        "type": "structured-content",
        "content": [
            {"tag": "ul", "content": [
                {"tag": "li", "content": "to eat"},
                {"tag": "li", "content": {"tag": "ruby", "content": [
                    "食", {"tag": "rt", "content": "た"}, "べる"]}},
            ]},
            {"tag": "table", "content": {"tag": "tr", "content": "table text"}},
            {"tag": "div", "data": {"content": "notes"}, "content": "a note"},
        ],
    }
]


def test_plain_and_text_items_images_and_deinflections_skipped():
    assert meanings(["cat", {"type": "text", "text": "feline"},
                     {"type": "image", "path": "x.png"}, ["食べる", ["v1"]]]) == ["cat", "feline"]


def test_structured_content_takes_only_glossary_marked_li():
    assert meanings(JMDICT_TABERU_2) == [
        "to live on (e.g. a salary)", "to live off", "to subsist on"]


def test_structured_content_without_markers_takes_li_and_skips_tables_ruby_and_notes():
    assert meanings(UNMARKED) == ["to eat", "食べる"]


def test_info_glossary_only_falls_back_to_all_text():
    assert meanings(JMDICT_VOICED_REPETITION) == ["voiced repetition mark in katakana"]


def test_multiline_string_drops_headword_xref_phrase_and_label_lines():
    text = ("ねこ【猫】 [ローマ字](neko)\n1 〔動物〕 a cat; 《口》 a puss.\n"
            "2 〔芸者〕 a geisha. [⇒げいしゃ]\n13 【俗】\n猫の手も借りたい　be extremely busy.\n")
    assert meanings([text]) == ["〔動物〕 a cat; 《口》 a puss.", "〔芸者〕 a geisha."]


def test_multiline_one_line_entry_keeps_sense_after_headword_ideographic_space():
    assert meanings(["ほげふが　a made-up thing.\n"]) == ["a made-up thing."]
    assert meanings(["ほげ　1 〔試験〕 a probe; a test.\n"]) == ["〔試験〕 a probe; a test."]


def test_multiline_trailing_next_headword_and_xref_only_rows_give_nothing_extra():
    text = "ほげ　a stand-in.\nふが１【譜画】 [ローマ字](fuga)\n"
    assert meanings([text]) == ["a stand-in."]
    assert meanings(["ほげ [ローマ字](hoge)\n＝ふが.\n"]) == []


def test_multiline_numbered_sense_may_hold_ideographic_space():
    text = "ほげ [ローマ字](hoge)\n1 Foo, Bar (1930-　; 作家).\n〜に　phrase only.\n"
    assert meanings([text]) == ["Foo, Bar (1930- ; 作家)."]


def test_deep_nesting_is_cut_at_max_depth():
    assert MAX_DEPTH == 64
    node = "deep"
    for _ in range(5000):
        node = {"tag": "span", "content": node}
    assert meanings([{"type": "structured-content", "content": node}]) == []


def test_short_gloss_first_two_joined_and_capped_at_a_boundary():
    assert short_gloss(["to eat", "to live on", "third"]) == "to eat; to live on"
    long = "; ".join(f"word{i}" for i in range(60))
    out = short_gloss([long])
    assert len(out) <= 160 and out.endswith("…") and not out[:-1].endswith(";")


def test_unhashable_tag_and_data_content_do_not_raise():
    content = [{"tag": ["x"], "content": "a"}, {"data": {"content": []}, "content": "b"}]
    assert meanings([{"type": "structured-content", "content": content}]) == ["ab"]
    li = [{"tag": "li", "data": {"content": {}}, "content": "c"}]
    assert meanings([{"type": "structured-content", "content": li}]) == ["c"]
