import io
import zipfile

import pytest

from api.core.epub_build import build_epub
from api.models import Document, DocumentImage, Volume

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def book(chapters=(("One", "一行目です。"), ("Two", "二行目です。")), cover=True) -> bytes:
    items = [(t, [("text", body)], []) for t, body in chapters]
    png = {"data": PNG, "media_type": "image/png"} if cover else None
    return build_epub("Book", items, cover=png, creator="Author")


def upload(data: bytes):
    return {"file": ("book.epub", data, "application/epub+zip")}


def _hrefs(client):
    chapters = client.post("/epub/inspect", files=upload(book())).json()["chapters"]
    return [c["href"] for c in chapters]


def test_inspect_lists_chapters_and_metadata(app_client, me):
    body = app_client.post("/epub/inspect", files=upload(book())).json()
    assert body["title"] == "Book" and body["author"] == "Author" and body["has_cover"] is True
    assert [c["title"] for c in body["chapters"]] == ["One", "Two"]


def test_import_creates_series_volume_chapters_and_cover(app_client, me, db):
    hrefs = _hrefs(app_client)
    r = app_client.post("/epub/import", files=upload(book()), data={
        "series_title": "New S", "volume_title": "Vol 1", "author": "Author", "hrefs": hrefs})
    out = r.json()
    assert r.status_code == 201 and out["imported"] == ["One", "Two"] and out["errors"] == []
    docs = (
        db.query(Document).filter_by(series_id=out["series_id"]).order_by(Document.series_order).all()
    )
    vid = out["volume_id"]
    assert [(d.chapter_title, d.volume_id) for d in docs] == [("One", vid), ("Two", vid)]
    assert db.get(Volume, out["volume_id"]).epub_author == "Author"
    covers = db.query(DocumentImage).filter_by(document_id=docs[0].id, is_cover=True).count()
    assert covers == 1


def test_reimport_skips_chapters_already_in_the_volume(app_client, me):
    hrefs = _hrefs(app_client)
    form = {"series_title": "S", "volume_title": "V", "hrefs": hrefs}
    app_client.post("/epub/import", files=upload(book()), data=form)
    again = app_client.post("/epub/import", files=upload(book()), data=form).json()
    assert again["imported"] == [] and again["skipped"] == ["One", "Two"]


def test_an_href_not_in_the_book_is_an_error_not_a_crash(app_client, me):
    out = app_client.post("/epub/import", files=upload(book()), data={
        "series_title": "S", "volume_title": "V", "hrefs": ["OEBPS/../../etc/passwd"]}).json()
    assert out["imported"] == [] and len(out["errors"]) == 1


def evil(name: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/container.xml", "<container/>")
        zf.writestr(name, "x")
    return buf.getvalue()


@pytest.mark.parametrize("data", [b"not a zip", evil("../x"), evil("/abs")])
def test_hostile_files_are_422_on_both_endpoints(app_client, me, db, data):
    assert app_client.post("/epub/inspect", files=upload(data)).status_code == 422
    r = app_client.post("/epub/import", files=upload(data),
                        data={"series_title": "S", "volume_title": "V", "hrefs": ["x"]})
    assert r.status_code == 422 and db.query(Document).count() == 0


def test_series_rules(app_client, me, make_user, make_series):
    data = {"volume_title": "V", "hrefs": ["x"]}
    assert app_client.post("/epub/import", files=upload(book()), data=data).status_code == 422
    theirs = make_series(make_user(email="o@example.com"), "T")
    r = app_client.post("/epub/import", files=upload(book()), data={**data, "series_id": theirs.id})
    assert r.status_code == 422


def _import(client, data, hrefs, **extra):
    form = {"series_title": "S", "volume_title": "V", "hrefs": hrefs, **extra}
    return client.post("/epub/import", files=upload(data), data=form)


def _book_hrefs(client, data):
    chapters = client.post("/epub/inspect", files=upload(data)).json()["chapters"]
    return [c["href"] for c in chapters]


def test_nul_in_one_chapter_does_not_sink_the_import(app_client, me, db):
    data = book((("Bad", "NUL\x00here。"), ("Good", "二行目です。")))
    out = _import(app_client, data, _book_hrefs(app_client, data)).json()
    assert out["imported"] == ["Bad", "Good"] and out["errors"] == []
    assert db.query(Document).count() == 2


def test_same_title_twice_in_one_book_imports_both(app_client, me, db):
    data = book((("Same", "一。"), ("Same", "二。")))
    out = _import(app_client, data, _book_hrefs(app_client, data)).json()
    assert out["imported"] == ["Same", "Same"] and out["skipped"] == []
    assert db.query(Document).count() == 2


def test_empty_hrefs_is_422(app_client, me):
    r = app_client.post("/epub/import", files=upload(book()),
                        data={"series_title": "S", "volume_title": "V"})
    assert r.status_code == 422


def test_oversized_upload_is_413(app_client, me, monkeypatch):
    monkeypatch.setattr("api.routers.epub.MAX_EPUB_BYTES", 100)
    assert app_client.post("/epub/inspect", files=upload(book())).status_code == 413
    assert _import(app_client, book(), ["x"]).status_code == 413


def test_image_budget_exhausted_rolls_back_the_whole_import(app_client, me, db, monkeypatch):
    img = {"src_path": "pic.png", "data": PNG + b"\x00" * 560}
    items = [(t, [("text", "本文。"), ("image", "pic.png")], [img]) for t in ("A", "B")]
    data = build_epub("Book", items, creator="Author")
    hrefs = _book_hrefs(app_client, data)
    monkeypatch.setattr("api.routers.epub.MAX_UNCOMPRESSED", 1000)
    r = _import(app_client, data, hrefs)
    assert r.status_code == 413
    db.rollback()  # what db_session's teardown does on a failed request
    assert db.query(Document).count() == 0


def test_chapter_files_count_against_the_budget(app_client, me, db, monkeypatch):
    data = book(cover=False)
    hrefs = _book_hrefs(app_client, data)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        one = zf.getinfo(hrefs[0]).file_size
    monkeypatch.setattr("api.routers.epub.MAX_UNCOMPRESSED", one + 1)
    assert _import(app_client, data, hrefs).status_code == 413


def test_oversized_text_entry_is_422(app_client, me, monkeypatch):
    monkeypatch.setattr("api.core.epub_read.MAX_TEXT_ENTRY", 10)
    assert app_client.post("/epub/inspect", files=upload(book())).status_code == 422


def test_nul_in_epub_titles_is_422(app_client, me):
    data = book()
    hrefs = _book_hrefs(app_client, data)
    assert _import(app_client, data, hrefs, series_title="a\x00b").status_code == 422
    assert _import(app_client, data, hrefs, volume_title="a\x00b").status_code == 422
