import io
import re
import zipfile

from api.core.epub_read import extract_chapter_content, open_book
from api.models import Volume, VolumeCover

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def volume(db, series, title="Vol 1"):
    v = Volume(series_id=series.id, kind="", subtitle=title, epub_author="A",
               epub_language="en")
    db.add(v)
    db.flush()
    return v


def test_a_finished_volume_round_trips(app_client, db, me, make_series, make_doc):
    s = make_series(me, "S")
    v = volume(db, s)
    make_doc(me, ["一行目です。"], series=s, order=1, volume=v, translated=True)
    make_doc(me, ["二行目です。"], series=s, order=2, volume=v, translated=True)
    db.add(VolumeCover(volume_id=v.id, src_path="cover.png", data=PNG))
    db.flush()
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert r.status_code == 200 and r.headers["content-type"] == "application/epub+zip"
    assert "S%20-%20Vol%201.epub" in r.headers["content-disposition"]
    book = open_book(io.BytesIO(r.content))
    assert book["title"] == "S - Vol 1" and book["author"] == "A" and book["cover_href"]
    text, _ = extract_chapter_content(io.BytesIO(r.content), book["chapters"][0]["href"])
    assert text.startswith("tr:")


def _opf(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read("OEBPS/content.opf").decode("utf-8")


def test_the_identifier_is_the_same_on_every_export(app_client, db, me, make_series, make_doc):
    s = make_series(me, "S")
    v = volume(db, s)
    make_doc(me, ["一"], series=s, order=1, volume=v, translated=True)
    first, second = (_opf(app_client.get(f"/volumes/{v.id}/export/epub").content) for _ in "12")
    ident = re.search(r'<dc:identifier id="uid">(urn:uuid:[0-9a-f-]+)</dc:identifier>', first)
    assert ident and ident.group(0) in second
    v.epub_identifier = "urn:isbn:9780000000000"
    db.flush()
    assert "urn:isbn:9780000000000" in _opf(app_client.get(f"/volumes/{v.id}/export/epub").content)


def test_translator_comes_from_the_account_unless_the_volume_says(
    app_client, db, me, make_series, make_doc
):
    s = make_series(me, "S")
    v = volume(db, s)
    v.epub_description = "Blurb"
    make_doc(me, ["一"], series=s, order=1, volume=v, translated=True)
    url = f"/volumes/{v.id}/export/epub"
    assert "dc:contributor" not in _opf(app_client.get(url).content)
    assert app_client.put("/settings", json={"epub_translator": " Me "}).status_code == 200
    opf = _opf(app_client.get(url).content)
    assert '<dc:contributor id="contributor-trl">Me</dc:contributor>' in opf
    assert "<dc:description>Blurb</dc:description>" in opf
    patched = app_client.patch(f"/volumes/{v.id}", json={"epub_translator": "Vol T"})
    assert patched.status_code == 200
    assert ">Vol T</dc:contributor>" in _opf(app_client.get(url).content)


def test_an_incomplete_chapter_is_a_409_naming_it(app_client, db, me, make_series, make_doc):
    s = make_series(me, "S")
    v = volume(db, s)
    make_doc(me, ["一"], series=s, order=1, volume=v, title="Done", translated=True)
    make_doc(me, ["二"], series=s, order=2, volume=v, title="Todo", translated=False)
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert r.status_code == 409 and "Todo" in r.json()["detail"]


def test_an_empty_volume_is_422_and_another_users_is_404(
    app_client, db, me, make_series, make_user
):
    v = volume(db, make_series(me, "S"))
    assert app_client.get(f"/volumes/{v.id}/export/epub").status_code == 422
    theirs = volume(db, make_series(make_user(email="o@example.com"), "T"))
    assert app_client.get(f"/volumes/{theirs.id}/export/epub").status_code == 404


def test_a_chapter_of_blank_lines_is_skipped_not_incomplete(
    app_client, db, me, make_series, make_doc
):
    s = make_series(me, "S")
    v = volume(db, s)
    make_doc(me, ["一"], series=s, order=1, volume=v, title="Done", translated=True)
    make_doc(me, ["", "  "], series=s, order=2, volume=v, title="Blank", translated=False)
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert r.status_code == 200
    assert [c["title"] for c in open_book(io.BytesIO(r.content))["chapters"]] == ["Done"]


def _opf(content):
    import zipfile

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return zf.read("OEBPS/content.opf").decode("utf-8")


def _finished(db, me, make_series, make_doc, **series_fields):
    s = make_series(me, "S")
    for k, val in series_fields.items():
        setattr(s, k, val)
    v = volume(db, s)
    make_doc(me, ["一行目です。"], series=s, order=1, volume=v, translated=True)
    db.flush()
    return v


def test_series_romaji_is_the_fallback_author(app_client, db, me, make_series, make_doc):
    v = _finished(db, me, make_series, make_doc, author_romaji="Yamada")
    v.epub_author = ""
    db.flush()
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert '<dc:creator id="creator-aut">Yamada</dc:creator>' in _opf(r.content)
    v.epub_author = "A"
    db.flush()
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert '<dc:creator id="creator-aut">A</dc:creator>' in _opf(r.content)


def test_original_title_is_credited(app_client, db, me, make_series, make_doc):
    v = _finished(db, me, make_series, make_doc, original_title="勇者", original_author="山田")
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert "<dc:source>勇者 (山田)</dc:source>" in _opf(r.content)
