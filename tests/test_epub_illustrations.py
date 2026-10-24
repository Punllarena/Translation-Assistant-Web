"""EPUB import gathers image-only chapters into the volume's one Illustrations chapter."""
import zipfile

from api.core.epub_build import build_epub
from api.models import Document, DocumentImage, Series
from api.routers import epub as epub_router
from tests.fixtures import epub as fx
from tests.test_epub_api import PNG, upload

PLATES = ["OEBPS/images/plate1.jpg", "OEBPS/images/plate2.jpg", "OEBPS/images/plate3.jpg"]
FORM = {"series_title": "S", "volume_kind": "V"}


def _chapters(client, data: bytes) -> list[dict]:
    return client.post("/epub/inspect", files=upload(data)).json()["chapters"]


def _import(client, data: bytes, hrefs: list[str], **extra):
    return client.post("/epub/import", files=upload(data), data={**FORM, "hrefs": hrefs, **extra})


def _hrefs(client, data: bytes, *titles: str) -> list[str]:
    return [c["href"] for c in _chapters(client, data) if not titles or c["title"] in titles]


def _images(db, doc_id: int) -> list[str]:
    rows = db.query(DocumentImage).filter_by(document_id=doc_id, is_cover=False)
    return [im.src_path for im in rows.order_by(DocumentImage.id)]


def _marked(db) -> list[Document]:
    return db.query(Document).filter_by(is_illustrations=True).all()


def test_image_only_chapters_become_one_first_chapter(app_client, me, db, tmp_path):
    data = fx.split_book(tmp_path).read_bytes()
    r = _import(app_client, data, _hrefs(app_client, data))
    out = r.json()
    assert r.status_code == 201 and out["errors"] == []
    assert out["imported"].count("Illustrations") == 1
    assert "plate1" not in out["imported"] and "cover" not in out["imported"]
    docs = [d for d in app_client.get("/documents").json() if d["series_id"] == out["series_id"]]
    docs.sort(key=lambda d: d["series_order"])
    first = docs[0]
    assert first["is_illustrations"] and first["title"] == first["chapter_title"] == "Illustrations"
    assert [d["is_illustrations"] for d in docs].count(True) == 1
    assert first["line_count"] == 0
    assert _images(db, first["id"]) == PLATES
    prologue = next(d for d in docs if d["chapter_title"] == "Prologue")
    assert _images(db, prologue["id"]) == ["OEBPS/images/inline.jpg"]


def test_cover_only_page_is_dropped(app_client, me, db, tmp_path):
    data = fx.split_book(tmp_path).read_bytes()
    out = _import(app_client, data, _hrefs(app_client, data, "cover", "Prologue")).json()
    assert out["imported"] == ["Prologue"] and out["errors"] == []
    assert _marked(db) == []
    docs = db.query(Document).filter_by(series_id=out["series_id"]).all()
    assert [d.chapter_title for d in docs] == ["Prologue"]


def test_reimport_adds_no_duplicate_images(app_client, me, db, tmp_path):
    data = fx.split_book(tmp_path).read_bytes()
    hrefs = _hrefs(app_client, data)
    _import(app_client, data, hrefs)
    again = _import(app_client, data, hrefs).json()
    assert again["imported"] == [] and "Prologue" in again["skipped"]
    (marked,) = _marked(db)
    assert _images(db, marked.id) == PLATES


def test_no_image_only_pick_no_chapter(app_client, me, db, tmp_path):
    data = fx.split_book(tmp_path).read_bytes()
    out = _import(app_client, data, _hrefs(app_client, data, "Prologue", "Chapter 1")).json()
    assert out["imported"] == ["Prologue", "Chapter 1"]
    assert _marked(db) == []


def test_second_book_appends_to_existing(app_client, me, db, tmp_path):
    data = fx.split_book(tmp_path).read_bytes()
    _import(app_client, data, _hrefs(app_client, data, "plate1", "Prologue"))
    other = build_epub("Other", [
        ("Frontis", [("image", "front.png")], [{"src_path": "front.png", "data": PNG}]),
        ("Story", [("text", "本文です。")], []),
    ], creator="Author")
    out = _import(app_client, other, _hrefs(app_client, other)).json()
    assert out["imported"] == ["Story", "Illustrations"]
    (marked,) = _marked(db)
    images = _images(db, marked.id)
    assert images[0] == PLATES[0] and len(images) == 2 and images[1].endswith("front.png")
    docs = db.query(Document).filter_by(volume_id=marked.volume_id).order_by(Document.series_order)
    assert docs.first().id == marked.id


def test_syosetu_series_gets_no_illustrations_chapter(app_client, me, db, tmp_path):
    series = Series(user_id=me.id, title="Web", syosetu_url="https://ncode.syosetu.com/n1/")
    db.add(series)
    db.flush()
    data = fx.split_book(tmp_path).read_bytes()
    out = app_client.post("/epub/import", files=upload(data), data={
        "series_id": series.id, "volume_kind": "V",
        "hrefs": _hrefs(app_client, data, "plate1", "Prologue")}).json()
    assert out["imported"] == ["plate1", "Prologue"]
    assert _marked(db) == []


def test_budget_still_trips_413(app_client, me, db, monkeypatch, tmp_path):
    data = fx.split_book(tmp_path).read_bytes()
    hrefs = _hrefs(app_client, data, "plate1", "plate2", "plate3")
    with zipfile.ZipFile(tmp_path / "split.epub") as zf:
        pages = [f"OEBPS/text/plate{n}.xhtml" for n in (1, 2, 3)]
        cover = ["OEBPS/images/cover.jpg"]  # attached to the first document
        total = sum(zf.getinfo(p).file_size for p in pages + PLATES + cover)
    monkeypatch.setattr("api.routers.epub.MAX_UNCOMPRESSED", total)
    assert _import(app_client, data, hrefs).status_code == 201
    monkeypatch.setattr("api.routers.epub.MAX_UNCOMPRESSED", total - 1)
    assert _import(app_client, data, hrefs, volume_index="2").status_code == 413


def test_extraction_wins_even_when_not_flagged_image_only(
        app_client, me, db, monkeypatch, tmp_path):
    real = epub_router.open_book

    def unflagged(source):
        book = real(source)
        for chapter in book["chapters"]:
            chapter["image_only"] = False
        return book

    monkeypatch.setattr(epub_router, "open_book", unflagged)
    data = fx.split_book(tmp_path).read_bytes()
    out = _import(app_client, data, _hrefs(app_client, data, "plate1", "Prologue")).json()
    assert out["imported"] == ["Prologue", "Illustrations"]
    (marked,) = _marked(db)
    assert _images(db, marked.id) == PLATES[:1]


def _with_page(src, dst, name: str, body: str) -> bytes:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == f"OEBPS/text/{name}.xhtml":
                data = f"<html><body>{body}</body></html>".encode()
            zout.writestr(info, data)
    return dst.read_bytes()


def test_the_cover_is_not_repeated_among_the_plates(app_client, me, db, tmp_path):
    data = _with_page(fx.split_book(tmp_path), tmp_path / "both.epub", "plate1",
                      fx._img("cover.jpg") + fx._img("plate1.jpg"))
    out = _import(app_client, data, _hrefs(app_client, data, "plate1", "Prologue")).json()
    assert out["imported"] == ["Prologue", "Illustrations"]
    (marked,) = _marked(db)
    assert _images(db, marked.id) == PLATES[:1]  # the cover is the volume's cover only


def test_plates_follow_the_spine_whatever_order_is_posted(app_client, me, db, tmp_path):
    data = fx.split_book(tmp_path).read_bytes()
    hrefs = _hrefs(app_client, data, "plate1", "plate2", "plate3", "Prologue")
    out = _import(app_client, data, [*reversed(hrefs), "nope.xhtml"]).json()
    assert out["errors"] == [{"title": "nope.xhtml", "message": "not a chapter of this EPUB"}]
    (marked,) = _marked(db)
    assert _images(db, marked.id) == PLATES
