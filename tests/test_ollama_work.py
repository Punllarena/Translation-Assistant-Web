from sqlalchemy import select

from api.models import Document, Line, Volume
from api.models.ollama import OllamaChunk, OllamaQueueItem, OllamaSuggestion
from api.ollama.chunks import RequestStats
from api.ollama.prefs import OllamaPrefs
from api.ollama.work import lines_left, next_plan, plan_for_line, raw_sha, rows_for, save

P = OllamaPrefs("small", 2, 1, None)


def _lines(db, doc):
    return {ln.line_number: ln for ln in db.scalars(select(Line).where(Line.document_id == doc.id))}


def _chunk(db, line):
    doc = db.get(Document, line.document_id)
    c = OllamaChunk(
        user_id=doc.user_id, document_id=doc.id, series_id=doc.series_id, source="run", ok=True,
        clamped=False, depth=0, model="m", preset="small", chunk_lines=2, context_lines=1,
        first_line=0, last_line=1, asked=1, prompt_tokens=1, output_tokens=1,
    )
    db.add(c)
    db.flush()
    return c


def _suggest(db, line, text="s", sha=None):
    db.add(
        OllamaSuggestion(
            line_id=line.id, chunk_id=_chunk(db, line).id, text=text,
            raw_sha=sha or raw_sha(line.raw_text),
        )
    )
    db.flush()


def _queue(db, user, kind, series, position, volume=None, ids=()):
    item = OllamaQueueItem(
        user_id=user.id, kind=kind, series_id=series.id, volume_id=volume.id if volume else None,
        document_ids=list(ids), position=position,
    )
    db.add(item)
    db.flush()
    return item


def _stats(first, last, ok=True, asked=1):
    return RequestStats(
        first_line=first, last_line=last, asked=asked, ok=ok, clamped=False, depth=0,
        reasoning="", prompt="[]", prompt_tokens=5, output_tokens=7,
    )


def _save(db, user, plan, requests, lines):
    save(db, user.id, plan, requests, lines, source="run", job_id=None, p=P, model="m")


def test_raw_sha_ignores_line_endings_and_outer_whitespace():
    assert raw_sha("猫\r\n") == raw_sha("猫")
    assert raw_sha(" 猫\r") == raw_sha("猫")
    assert raw_sha("猫") != raw_sha("犬")


def test_rows_known_from_translation_or_current_suggestion(db, make_user, make_doc):
    u = make_user()
    doc = make_doc(u, ["a", "b", "c", "d"], translated=False)
    ls = _lines(db, doc)
    ls[0].translated_text = "done"
    _suggest(db, ls[1], "sug")
    _suggest(db, ls[2], "old", sha="0" * 64)  # stale
    db.flush()
    rows = rows_for(db, u.id, doc)
    assert [r.known for r in rows] == ["done", "sug", None, None]
    assert rows[1].line_id == ls[1].id and rows[1].raw_sha == raw_sha("b")


def test_rows_blank_line_has_empty_text(db, make_user, make_doc):
    u = make_user()
    doc = make_doc(u, ["a", "", "c"], translated=False)
    ls = _lines(db, doc)
    ls[1].prefix = ""
    db.flush()
    rows = rows_for(db, u.id, doc)
    assert [r.text for r in rows] == ["a", "", "c"]
    assert rows[1].prefix == ""


def test_next_plan_skips_translated_and_suggested_lines(db, make_user, make_series, make_doc):
    u = make_user()
    s = make_series(u)
    doc = make_doc(u, ["a", "b", "c", "d", "e"], series=s, translated=False)
    ls = _lines(db, doc)
    ls[0].translated_text = "x"
    ls[1].translated_text = "y"
    _suggest(db, ls[2], "z")
    db.flush()
    _queue(db, u, "series", s, 1)
    plan = next_plan(db, u.id, P)
    assert plan.document_id == doc.id and plan.series_id == s.id
    assert [r.line_number for r in plan.chunk] == [2, 3]  # c is suggested, d is asked
    assert [r.line_number for r in plan.asked] == [3]
    assert [r.line_number for r in plan.before] == [1]


def test_next_plan_follows_queue_position_and_series_order(db, make_user, make_series, make_doc):
    u = make_user()
    s1, s2 = make_series(u, "one"), make_series(u, "two")
    late = make_doc(u, ["a"], series=s1, order=2, translated=False)
    early = make_doc(u, ["a"], series=s1, order=1, translated=False)
    other = make_doc(u, ["a"], series=s2, translated=False)
    first = _queue(db, u, "series", s2, 1)
    _queue(db, u, "series", s1, 2)
    assert next_plan(db, u.id, P).document_id == other.id
    db.delete(first)
    db.flush()
    assert next_plan(db, u.id, P).document_id == early.id
    _lines(db, early)[0].translated_text = "t"
    db.flush()
    assert next_plan(db, u.id, P).document_id == late.id


def test_next_plan_skips_illustrations_and_other_users(db, make_user, make_series, make_doc):
    u, v = make_user(), make_user("v@example.com")
    s = make_series(u)
    ill = make_doc(u, ["a"], series=s, order=1, translated=False)
    ill.is_illustrations = True
    ok = make_doc(u, ["a"], series=s, order=2, translated=False)
    db.flush()
    _queue(db, u, "series", s, 1)
    assert next_plan(db, u.id, P).document_id == ok.id
    assert next_plan(db, v.id, P) is None


def test_next_chunk_drops_items_whose_target_is_gone(db, make_user, make_series, make_doc):
    u = make_user()
    s = make_series(u)
    vol = Volume(series_id=s.id, subtitle="V", volume_order=1)
    db.add(vol)
    db.flush()
    make_doc(u, ["a"], series=s, volume=vol, translated=True)  # nothing to ask
    d = make_doc(u, ["a"], series=s, order=5, translated=False)
    _queue(db, u, "volume", s, 1, volume=vol)
    _queue(db, u, "documents", s, 2, ids=[999999])
    _queue(db, u, "documents", s, 3, ids=[999999, d.id])
    plan = next_plan(db, u.id, P)
    assert plan.document_id == d.id
    assert db.scalars(select(OllamaQueueItem.position)).all() == [3]


def test_next_plan_none_keeps_series_item(db, make_user, make_series, make_doc):
    u = make_user()
    s = make_series(u)
    make_doc(u, ["a"], series=s, translated=True)
    _queue(db, u, "series", s, 1)
    assert next_plan(db, u.id, P) is None
    assert db.scalar(select(OllamaQueueItem.id)) is not None


def test_plan_for_line_asks_the_line_even_if_translated(db, make_user, make_doc):
    u = make_user()
    doc = make_doc(u, ["a", "b", "c", "d"], translated=True)
    plan = plan_for_line(db, u.id, doc, 2, P, reroll=False)
    assert [r.line_number for r in plan.chunk] == [2, 3]
    assert [r.line_number for r in plan.asked] == [2]
    assert plan.chunk[1].known == "tr:d"
    assert [r.line_number for r in plan.before] == [1]


def test_reroll_asks_all_untranslated_lines(db, make_user, make_doc):
    u = make_user()
    doc = make_doc(u, ["a", "b", "c", "d"], translated=False)
    ls = _lines(db, doc)
    ls[0].translated_text = "t"
    _suggest(db, ls[1], "sug")
    db.flush()
    plan = plan_for_line(db, u.id, doc, 1, P, reroll=True)
    assert [r.line_number for r in plan.chunk] == [0, 1]
    assert [r.line_number for r in plan.asked] == [1]  # line 0 is translated
    plan = plan_for_line(db, u.id, doc, 2, P, reroll=True)
    assert [r.line_number for r in plan.asked] == [2, 3]
    plan = plan_for_line(db, u.id, doc, 2, P, reroll=False)
    assert [r.line_number for r in plan.asked] == [2, 3]  # d has no suggestion either
    plan = plan_for_line(db, u.id, doc, 0, P, reroll=False)
    assert [r.line_number for r in plan.asked] == [0]  # translated, asked anyway
    assert plan.chunk[1].known == "sug"


def test_save_replaces_existing_suggestion_and_keeps_stats(db, make_user, make_doc):
    u = make_user()
    doc = make_doc(u, ["a", "b", "c", "d"], translated=False)
    ls = _lines(db, doc)
    _suggest(db, ls[0], "old")
    db.scalar(select(OllamaSuggestion)).scored = True
    db.flush()
    plan = plan_for_line(db, u.id, doc, 0, P, reroll=True)
    _save(db, u, plan, [_stats(0, 1, asked=2)], {0: "new", 1: "two"})
    c = db.scalars(select(OllamaChunk).where(OllamaChunk.id > 0).order_by(OllamaChunk.id)).all()[-1]
    assert (c.document_id, c.series_id, c.model, c.preset, c.chunk_lines, c.context_lines) == (
        doc.id, doc.series_id, "m", "small", 2, 1)
    assert (c.prompt_tokens, c.output_tokens, c.first_line, c.last_line) == (5, 7, 0, 1)
    sugs = {s.line_id: s for s in db.scalars(select(OllamaSuggestion))}
    assert len(sugs) == 2
    s0 = sugs[ls[0].id]
    assert s0.text == "new" and s0.chunk_id == c.id and s0.scored is False
    assert s0.raw_sha == raw_sha("a")


def test_save_points_each_line_at_its_ok_request(db, make_user, make_doc):
    u = make_user()
    doc = make_doc(u, ["a", "b", "c", "d"], translated=False)
    ls = _lines(db, doc)
    plan = plan_for_line(db, u.id, doc, 0, P, reroll=True)
    _save(db, u, plan, [_stats(0, 1, ok=False), _stats(0, 1), _stats(0, 0)], {0: "x", 1: "y"})
    chunks = db.scalars(select(OllamaChunk).order_by(OllamaChunk.id)).all()
    assert [c.ok for c in chunks] == [False, True, True]
    sugs = {s.line_id: s.chunk_id for s in db.scalars(select(OllamaSuggestion))}
    assert sugs[ls[0].id] == chunks[2].id
    assert sugs[ls[1].id] == chunks[1].id


def test_save_skips_lines_changed_since_plan(db, make_user, make_doc):
    u = make_user()
    doc = make_doc(u, ["a", "b", "c"], translated=False)
    ls = _lines(db, doc)
    plan = plan_for_line(db, u.id, doc, 0, P, reroll=True)
    ls[0].translated_text = "typed"
    ls[1].raw_text = "changed"
    db.flush()
    _save(db, u, plan, [_stats(0, 1, asked=2)], {0: "x", 1: "y"})
    assert db.scalar(select(OllamaSuggestion.id)) is None
    assert db.scalar(select(OllamaChunk.id)) is not None


def test_lines_left(db, make_user, make_series, make_doc):
    u = make_user()
    s = make_series(u)
    doc = make_doc(u, ["a", "b", "c", " ", "e"], series=s, translated=False)
    ls = _lines(db, doc)
    ls[0].translated_text = "t"
    _suggest(db, ls[1], "s")
    _suggest(db, ls[2], "stale", sha="0" * 64)
    db.flush()
    item = _queue(db, u, "series", s, 1)
    assert lines_left(db, u.id, item) == 2  # c (stale suggestion) and e
