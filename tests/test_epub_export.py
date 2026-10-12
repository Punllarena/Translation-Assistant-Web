import io

from api.core.epub_read import extract_chapter_content, open_book
from api.models import DocumentImage, Volume

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def volume(db, series, title="Vol 1"):
    v = Volume(series_id=series.id, title=title, epub_author="A", epub_language="en")
    db.add(v)
    db.flush()
    return v


def test_a_finished_volume_round_trips(app_client, db, me, make_series, make_doc):
    s = make_series(me, "S")
    v = volume(db, s)
    d1 = make_doc(me, ["一行目です。"], series=s, order=1, volume=v, translated=True)
    make_doc(me, ["二行目です。"], series=s, order=2, volume=v, translated=True)
    db.add(DocumentImage(document_id=d1.id, anchor_position=0, is_cover=True,
                         src_path="cover.png", data=PNG))
    db.flush()
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert r.status_code == 200 and r.headers["content-type"] == "application/epub+zip"
    assert "Vol%201.epub" in r.headers["content-disposition"]
    book = open_book(io.BytesIO(r.content))
    assert book["title"] == "Vol 1" and book["author"] == "A" and book["cover_href"]
    text, _ = extract_chapter_content(io.BytesIO(r.content), book["chapters"][0]["href"])
    assert text.startswith("tr:")


def test_an_incomplete_chapter_is_a_409_naming_it(app_client, db, me, make_series, make_doc):
    s = make_series(me, "S")
    v = volume(db, s)
    make_doc(me, ["一"], series=s, order=1, volume=v, title="Done", translated=True)
    make_doc(me, ["二"], series=s, order=2, volume=v, title="Todo", translated=False)
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert r.status_code == 409 and "Todo" in r.json()["detail"]


def test_an_empty_volume_is_422_and_another_users_is_404(app_client, db, me, make_series, make_user):
    v = volume(db, make_series(me, "S"))
    assert app_client.get(f"/volumes/{v.id}/export/epub").status_code == 422
    theirs = volume(db, make_series(make_user(email="o@example.com"), "T"))
    assert app_client.get(f"/volumes/{theirs.id}/export/epub").status_code == 404
