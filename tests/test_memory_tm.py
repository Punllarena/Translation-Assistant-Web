from datetime import UTC, datetime

from api.models import Document


def tm(client, doc, n=0):
    return client.get("/tm/matches", params={"document_id": doc.id, "line_number": n})


def test_exact_source_matches_from_other_documents_newest_first(app_client, db, me, make_doc):
    old = make_doc(me, ["同じ文。"], title="old")
    make_doc(me, ["同じ文。"], title="new")
    db.get(Document, old.id).updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    db.flush()
    current = make_doc(me, ["同じ文。", "違う。"], translated=False, title="cur")
    body = tm(app_client, current).json()
    assert [(m["document_title"], m["translated_text"]) for m in body] == [
        ("new", "tr:同じ文。"), ("old", "tr:同じ文。")
    ]
    assert tm(app_client, current, 1).json() == []


def test_excludes_current_document_and_untranslated(app_client, me, make_doc):
    make_doc(me, ["文。"], translated=False, title="blank")
    current = make_doc(me, ["文。", "文。"], title="cur")  # its own line 1 is translated
    assert tm(app_client, current).json() == []


def test_limit_is_five(app_client, me, make_doc):
    for i in range(7):
        make_doc(me, ["文。"], title=f"d{i}")
    current = make_doc(me, ["文。"], translated=False)
    assert len(tm(app_client, current).json()) == 5


def test_blank_source_line_has_no_matches(app_client, me, make_doc):
    make_doc(me, [""], title="other")
    current = make_doc(me, [""], translated=False)
    assert tm(app_client, current).json() == []


def test_symbol_only_line_has_no_matches(app_client, me, make_doc):
    make_doc(me, ["■"], title="other")
    make_doc(me, ["文。"], title="text")
    current = make_doc(me, ["■", "文。"], translated=False)
    assert tm(app_client, current, 0).json() == []
    assert [m["translated_text"] for m in tm(app_client, current, 1).json()] == ["tr:文。"]


def test_never_returns_another_users_lines(app_client, me, make_user, make_doc):
    other = make_user(email="other@example.com")
    make_doc(other, ["秘密。"], title="theirs")
    current = make_doc(me, ["秘密。"], translated=False)
    assert tm(app_client, current).json() == []


def test_another_users_document_is_404(app_client, me, make_user, make_doc):
    other = make_user(email="other@example.com")
    theirs = make_doc(other, ["文。"])
    assert tm(app_client, theirs).status_code == 404


def test_missing_line_is_404(app_client, me, make_doc):
    current = make_doc(me, ["文。"])
    assert tm(app_client, current, 5).status_code == 404
