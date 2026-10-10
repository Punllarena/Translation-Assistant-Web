import io
import zipfile
from urllib.parse import quote

import pytest
from sqlalchemy import select

from api.models import Line

SEP = "---SEPERATOR---"
BODY = f"%一文目。\n$二文目。\n\n%次\n{SEP}\nOne.\nTwo.\n\nNext\n".encode()


def upload(client, body, name="ch1.txt", **form):
    return client.post(
        "/documents/import/txt", files={"file": (name, body, "text/plain")}, data=form
    )


def rows(db, doc_id):
    return [
        tuple(r)
        for r in db.execute(
            select(Line.prefix, Line.raw_text, Line.translated_text)
            .where(Line.document_id == doc_id)
            .order_by(Line.line_number)
        )
    ]


def test_import_txt_creates_document(app_client, db, me):
    r = upload(app_client, BODY, name="第1話.txt")
    assert (r.status_code, r.json()["title"]) == (201, "第1話")
    assert rows(db, r.json()["id"]) == [
        ("%", "一文目。", "One."), ("$", "二文目。", "Two."), ("%", "", ""), ("%", "次", "Next"),
    ]


def test_import_txt_tolerates_bom_and_crlf(app_client, db, me):
    body = ("﻿%行\r\n" + SEP + "\r\nLine\r\n").encode()
    r = upload(app_client, body)
    assert rows(db, r.json()["id"]) == [("%", "行", "Line")]


def test_import_txt_into_a_series_with_a_title(app_client, me, make_series, make_doc):
    series = make_series(me)
    make_doc(me, series=series, order=2)
    r = upload(app_client, BODY, title="Custom", series_id=str(series.id))
    assert (r.json()["title"], r.json()["series_id"], r.json()["series_order"]) == (
        "Custom", series.id, 3,
    )


@pytest.mark.parametrize(
    "body",
    [
        b"%no separator here\n",  # not the TXT format
        "%あ\n---SEPERATOR---\n".encode("shift_jis"),  # not UTF-8
        b"%a\x00\n---SEPERATOR---\n",  # binary
    ],
)
def test_import_txt_rejects_unreadable_files(app_client, me, body):
    r = upload(app_client, body)
    assert r.status_code == 422
    assert r.json()["detail"]


def test_import_txt_size_is_capped(app_client, me, monkeypatch):
    from api.routers import transfer

    monkeypatch.setattr(transfer, "MAX_TEXT_BYTES", 8)
    assert upload(app_client, BODY).status_code == 413


def test_import_txt_into_a_foreign_series_is_422(app_client, me, make_user, make_series):
    theirs = make_series(make_user(email="other@example.com"))
    assert upload(app_client, BODY, series_id=str(theirs.id)).status_code == 422


def test_txt_export_round_trips_the_import(app_client, me):
    doc_id = upload(app_client, BODY).json()["id"]
    r = app_client.get(f"/documents/{doc_id}/export", params={"format": "txt"})
    assert r.status_code == 200
    assert r.content == BODY


def test_markdown_exports(app_client, me):
    doc_id = upload(app_client, BODY, name="第1話.txt").json()["id"]
    md = app_client.get(f"/documents/{doc_id}/export", params={"format": "md"})
    assert md.text == "# 第1話\n\nOne. Two.\n\n\nNext\n\n"
    ruby = app_client.get(f"/documents/{doc_id}/export", params={"format": "md-ruby"})
    assert "<ruby>One. Two.<rt>一文目。二文目。</rt></ruby>" in ruby.text


def test_download_name_keeps_a_japanese_title(app_client, me):
    doc_id = upload(app_client, BODY, name="第1話.txt").json()["id"]
    r = app_client.get(f"/documents/{doc_id}/export", params={"format": "md"})
    assert f"filename*=UTF-8''{quote('第1話.md')}" in r.headers["content-disposition"]


def test_unknown_format_is_422(app_client, me, make_doc):
    doc = make_doc(me, ["a"])
    r = app_client.get(f"/documents/{doc.id}/export", params={"format": "pdf"})
    assert r.status_code == 422


def test_series_markdown_zip_skips_incomplete_chapters(app_client, me, make_series, make_doc):
    s = make_series(me, "シリーズ")
    make_doc(me, ["a"], series=s, order=1, title="A")
    make_doc(me, ["b"], series=s, order=2, title="B")
    make_doc(me, ["c"], series=s, order=3, title="C", translated=False)
    make_doc(me, ["d"], series=s, order=2, title="B")  # same order and title as B
    r = app_client.get(f"/series/{s.id}/export/markdown", params={"variant": "plain"})
    assert r.status_code == 200
    assert r.headers["x-ta-skipped-incomplete"] == "1"
    assert quote("シリーズ.zip") in r.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert names[:2] == ["001 - A.md", "002 - B.md"]
    assert len(names) == 3 and names[2].startswith("002 - B (")


@pytest.mark.parametrize(
    "path", ["/documents/{doc}/export", "/series/{series}/export/markdown"]
)
def test_another_users_exports_are_404(app_client, me, make_user, make_series, make_doc, path):
    other = make_user(email="other@example.com")
    series = make_series(other)
    doc = make_doc(other, ["x"], series=series, order=1)
    assert app_client.get(path.format(doc=doc.id, series=series.id)).status_code == 404


def test_import_txt_line_count_is_capped(app_client, db, me, monkeypatch):
    from api import library

    monkeypatch.setattr(library, "MAX_LINES", 2)
    r = upload(app_client, f"a\nb\nc\n{SEP}\nA\nB\nC\n".encode())
    assert (r.status_code, r.json()["detail"]) == (422, "too many lines (max 2)")
    assert app_client.get("/documents").json() == []
