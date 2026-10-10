"""Merge and split: the desktop reference tests plus what this port fixes (# new)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update

from api.models import Document, DocumentImage, Line, Volume
from api.restructure import NotOwned, RestructureError, merge_documents, split_document

T1 = datetime(2026, 1, 1, tzinfo=UTC)
T2 = datetime(2026, 2, 2, tzinfo=UTC)


@pytest.fixture
def user(make_user):
    return make_user()


@pytest.fixture
def series(user, make_series):
    return make_series(user)


@pytest.fixture
def chapter(db, user, series, make_doc):
    """chapter(title, order, raws, prefixes=None) -> Document in `series`."""

    def _make(title, order, raws, prefixes=None):
        doc = make_doc(user, raws, series=series, order=order, title=title)
        for i, prefix in enumerate(prefixes or []):
            db.execute(
                update(Line)
                .where(Line.document_id == doc.id, Line.line_number == i)
                .values(prefix=prefix)
            )
        return doc

    return _make


def col(db, doc_id, field="raw_text"):
    return list(
        db.scalars(
            select(getattr(Line, field))
            .where(Line.document_id == doc_id)
            .order_by(Line.line_number)
        )
    )


def images(db, doc_id):
    rows = db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc_id))
    return {img.src_path: img.anchor_position for img in rows}


def add_image(db, doc, anchor, name):
    db.add(DocumentImage(document_id=doc.id, anchor_position=anchor, src_path=name, data=b"x"))
    db.flush()


def stamp(db, doc, when):
    db.execute(update(Line).where(Line.document_id == doc.id).values(translated_at=when))


def orders(db, *docs):
    db.expire_all()
    return {db.get(Document, d.id).chapter_title: db.get(Document, d.id).series_order for d in docs}


# --- merge -----------------------------------------------------------------


def test_merge_concatenates_lines_in_series_order(db, user, chapter):
    a, b = chapter("A", 1, ["a0", "a1"]), chapter("B", 2, ["b0", "b1"])
    target = merge_documents(db, user.id, [b.id, a.id], "Merged")
    assert target.id == a.id
    assert col(db, a.id) == ["a0", "a1", "b0", "b1"]
    assert col(db, a.id, "translated_text") == ["tr:a0", "tr:a1", "tr:b0", "tr:b1"]


def test_merge_renumbers_lines_contiguously(db, user, chapter):
    a, b = chapter("A", 1, ["a0", "a1"]), chapter("B", 2, ["b0"])
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert col(db, a.id, "line_number") == [0, 1, 2]


def test_merge_forces_paragraph_prefix_at_boundary(db, user, chapter):
    a, b = chapter("A", 1, ["a0"]), chapter("B", 2, ["b0", "b1"], prefixes=["$", "$"])
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert col(db, a.id, "prefix") == ["%", "%", "$"]


def test_merge_reanchors_images(db, user, chapter):
    a, b = chapter("A", 1, ["a0", "a1", "a2"]), chapter("B", 2, ["b0", "b1"])
    add_image(db, a, 1, "a.png")
    add_image(db, b, 0, "b.png")
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert images(db, a.id) == {"a.png": 1, "b.png": 3}


def test_merge_deletes_source_documents(db, user, chapter):
    a, b = chapter("A", 1, ["a0"]), chapter("B", 2, ["b0"])
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert db.get(Document, b.id) is None


def test_merge_sets_merged_title_and_keeps_target_wp_fields(db, user, chapter):
    a, b = chapter("A", 1, ["a0"]), chapter("B", 2, ["b0"])
    a.wp_status, a.wp_post_url = "publish", "http://x/a"
    b.wp_status, b.wp_post_url = "publish", "http://x/b"
    db.flush()
    target = merge_documents(db, user.id, [a.id, b.id], "Combined Chapter")
    assert (target.chapter_title, target.wp_status, target.wp_post_url) == (
        "Combined Chapter", "publish", "http://x/a",
    )


def test_merge_compacts_series_order(db, user, chapter):
    a, b, c, d = (chapter(t, i, [t]) for i, t in enumerate("ABCD", start=1))
    merge_documents(db, user.id, [b.id, c.id], "BC")
    assert orders(db, a, b, d) == {"A": 1, "BC": 2, "D": 3}


def test_merge_three_way(db, user, chapter):
    a, b, c = chapter("A", 1, ["a0"]), chapter("B", 2, ["b0"]), chapter("C", 3, ["c0"])
    assert merge_documents(db, user.id, [c.id, a.id, b.id], "ABC").id == a.id
    assert col(db, a.id) == ["a0", "b0", "c0"]


def test_merge_rejects_a_single_document(db, user, chapter):
    with pytest.raises(RestructureError):
        merge_documents(db, user.id, [chapter("A", 1, ["a0"]).id], "Merged")


def test_merge_rejects_mixed_series(db, user, chapter, make_series, make_doc):
    a = chapter("A", 1, ["a0"])
    b = make_doc(user, ["b0"], series=make_series(user, "S2"), order=1)
    with pytest.raises(RestructureError):
        merge_documents(db, user.id, [a.id, b.id], "Merged")


def test_merge_rejects_a_document_listed_twice(db, user, chapter):  # new
    a = chapter("A", 1, ["a0"])
    with pytest.raises(RestructureError):
        merge_documents(db, user.id, [a.id, a.id], "Merged")


def test_merge_keeps_every_lines_translated_at(db, user, chapter):  # new
    a, b = chapter("A", 1, ["a0", "a1"]), chapter("B", 2, ["b0"])
    stamp(db, a, T1)
    stamp(db, b, T2)
    merge_documents(db, user.id, [a.id, b.id], "Merged")
    assert col(db, a.id, "translated_at") == [T1, T1, T2]


def test_merge_with_a_foreign_document_changes_nothing(  # new
    db, user, chapter, make_user, make_doc
):
    a = chapter("A", 1, ["a0"])
    theirs = make_doc(make_user(email="other@example.com"), ["z"])
    with pytest.raises(NotOwned):
        merge_documents(db, user.id, [a.id, theirs.id], "Merged")
    assert col(db, a.id) == ["a0"]
    assert col(db, theirs.id) == ["z"]


# --- split -----------------------------------------------------------------


def test_split_partitions_lines_at_cut(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3"])
    first, second = split_document(db, user.id, doc.id, [(2, "Part 2")])
    assert first.id == doc.id
    assert (col(db, doc.id), col(db, second.id)) == (["l0", "l1"], ["l2", "l3"])


def test_split_renumbers_each_segment_from_zero(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3", "l4"])
    _, p2, p3 = split_document(db, user.id, doc.id, [(2, "P2"), (4, "P3")])
    assert (col(db, p2.id, "line_number"), col(db, p3.id, "line_number")) == ([0, 1], [0])


def test_split_preserves_translations_by_index(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3"])
    _, second = split_document(db, user.id, doc.id, [(2, "P2")])
    assert col(db, doc.id, "translated_text") == ["tr:l0", "tr:l1"]
    assert col(db, second.id, "translated_text") == ["tr:l2", "tr:l3"]


def test_split_forces_paragraph_prefix_at_segment_head(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2"], prefixes=["%", "$", "$"])
    _, second = split_document(db, user.id, doc.id, [(1, "P2")])
    assert col(db, second.id, "prefix") == ["%", "$"]


def test_split_reanchors_images_to_owning_segment(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3"])
    add_image(db, doc, 0, "a.png")
    add_image(db, doc, 3, "b.png")
    _, second = split_document(db, user.id, doc.id, [(2, "P2")])
    assert (images(db, doc.id), images(db, second.id)) == ({"a.png": 0}, {"b.png": 1})


def test_split_moves_an_end_anchored_image_to_the_last_segment(db, user, chapter):  # new
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3"])
    add_image(db, doc, 4, "closing.png")  # anchored after the last line
    _, second = split_document(db, user.id, doc.id, [(2, "P2")])
    assert (images(db, doc.id), images(db, second.id)) == ({}, {"closing.png": 2})


def test_split_new_segment_takes_typed_title(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1"])
    _, second = split_document(db, user.id, doc.id, [(1, "Second Half")])
    assert (second.title, second.chapter_title) == ("Second Half", "Second Half")


def test_split_blank_title_autonames(db, user, chapter):
    doc = chapter("My Chapter", 1, ["l0", "l1", "l2"])
    _, p2, p3 = split_document(db, user.id, doc.id, [(1, ""), (2, "  ")])
    assert (p2.chapter_title, p3.chapter_title) == ("My Chapter (2)", "My Chapter (3)")


def test_split_original_keeps_wp_fields_new_segments_unpublished(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1"])
    doc.wp_status, doc.wp_post_url = "publish", "http://x/1"
    db.flush()
    first, second = split_document(db, user.id, doc.id, [(1, "P2")])
    assert (first.wp_status, first.wp_post_url) == ("publish", "http://x/1")
    assert (second.wp_status, second.wp_post_url) == ("", "")


def test_split_new_segments_inherit_volume(db, user, series, make_doc):
    vol = Volume(series_id=series.id, title="Vol 1")
    db.add(vol)
    db.flush()
    doc = make_doc(user, ["l0", "l1", "l2", "l3"], series=series, order=1, volume=vol)
    _, second = split_document(db, user.id, doc.id, [(2, "P2")])
    assert (second.series_id, second.volume_id) == (series.id, vol.id)


def test_split_inserts_segments_after_original_in_series_order(db, user, chapter):
    a = chapter("A", 1, ["a0"])
    src = chapter("Src", 2, ["s0", "s1", "s2"])
    c = chapter("C", 3, ["c0"])
    _, s2, s3 = split_document(db, user.id, src.id, [(1, "Src2"), (2, "Src3")])
    assert orders(db, a, src, s2, s3, c) == {"A": 1, "Src": 2, "Src2": 3, "Src3": 4, "C": 5}


def test_split_three_way(db, user, chapter):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2", "l3", "l4", "l5"])
    segments = split_document(db, user.id, doc.id, [(2, "P2"), (4, "P3")])
    assert [col(db, s.id) for s in segments] == [["l0", "l1"], ["l2", "l3"], ["l4", "l5"]]


def test_split_keeps_every_lines_translated_at(db, user, chapter):  # new
    doc = chapter("Ch1", 1, ["l0", "l1", "l2"])
    stamp(db, doc, T1)
    _, second = split_document(db, user.id, doc.id, [(1, "P2")])
    assert col(db, second.id, "translated_at") == [T1, T1]


@pytest.mark.parametrize(
    "cuts", [[], [(0, "P")], [(3, "P")], [(2, "P"), (2, "Q")], [(2, "P"), (1, "Q")]]
)
def test_split_rejects_bad_cuts(db, user, chapter, cuts):
    doc = chapter("Ch1", 1, ["l0", "l1", "l2"])
    with pytest.raises(RestructureError):
        split_document(db, user.id, doc.id, cuts)


def test_split_of_a_foreign_document_is_not_owned(db, user, make_user, make_doc):  # new
    theirs = make_doc(make_user(email="other@example.com"), ["a", "b"])
    with pytest.raises(NotOwned):
        split_document(db, user.id, theirs.id, [(1, "P")])


# --- endpoints -------------------------------------------------------------


def test_merge_endpoint(app_client, db, me, make_series, make_doc):
    s = make_series(me)
    a, b = make_doc(me, ["a0"], series=s, order=1), make_doc(me, ["b0"], series=s, order=2)
    r = app_client.post("/documents/merge", json={"document_ids": [a.id, b.id], "title": "AB"})
    assert (r.status_code, r.json()["id"], r.json()["chapter_title"]) == (200, a.id, "AB")
    assert col(db, a.id) == ["a0", "b0"]


def test_merge_endpoint_422s_identically_on_foreign_and_missing_ids(
    app_client, db, me, make_user, make_doc
):
    mine = make_doc(me, ["a0"])
    theirs = make_doc(make_user(email="other@example.com"), ["z"])
    foreign = app_client.post(
        "/documents/merge", json={"document_ids": [mine.id, theirs.id], "title": "AB"}
    )
    missing = app_client.post(
        "/documents/merge", json={"document_ids": [mine.id, 999999999], "title": "AB"}
    )
    assert (foreign.status_code, missing.status_code) == (422, 422)
    assert foreign.json() == missing.json()
    assert foreign.json()["detail"] == "document_ids: no such item"
    assert col(db, theirs.id) == ["z"]


def test_merge_endpoint_422s_on_one_id(app_client, me, make_doc):
    doc = make_doc(me, ["a0"])
    r = app_client.post("/documents/merge", json={"document_ids": [doc.id], "title": "A"})
    assert r.status_code == 422


def test_split_endpoint(app_client, me, make_doc):
    doc = make_doc(me, ["l0", "l1", "l2"])
    r = app_client.post(f"/documents/{doc.id}/split", json={"cuts": [{"start": 1, "title": "B"}]})
    assert r.status_code == 200
    assert [d["chapter_title"] for d in r.json()] == ["Ch", "B"]


def test_split_endpoint_422s_out_of_range(app_client, me, make_doc):
    doc = make_doc(me, ["l0", "l1"])
    r = app_client.post(f"/documents/{doc.id}/split", json={"cuts": [{"start": 5}]})
    assert r.status_code == 422


def test_split_endpoint_404s_on_a_foreign_document(app_client, me, make_user, make_doc):
    theirs = make_doc(make_user(email="other@example.com"), ["a", "b"])
    r = app_client.post(f"/documents/{theirs.id}/split", json={"cuts": [{"start": 1}]})
    assert r.status_code == 404
