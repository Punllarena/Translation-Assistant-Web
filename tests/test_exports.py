import io
import zipfile
from urllib.parse import quote

import pytest

from api.models import Volume


def names_of(r):
    return zipfile.ZipFile(io.BytesIO(r.content)).namelist()


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
    names = names_of(r)
    assert names[:2] == ["001 - A.md", "002 - B.md"]
    assert len(names) == 3 and names[2].startswith("002 - B (")


def test_another_users_series_export_is_404(app_client, me, make_user, make_series, make_doc):
    other = make_user(email="other@example.com")
    series = make_series(other)
    make_doc(other, ["x"], series=series, order=1)
    assert app_client.get(f"/series/{series.id}/export/markdown").status_code == 404


def _volume(db, series, title="Vol 1", order=1):
    v = Volume(series_id=series.id, title=title, volume_order=order)
    db.add(v)
    db.flush()
    return v


def test_volume_zip_holds_only_that_volume(app_client, db, me, make_series, make_doc):
    s = make_series(me, "S")
    v1, v2 = _volume(db, s, "Vol 1", 1), _volume(db, s, "Vol 2", 2)
    make_doc(me, ["a"], series=s, order=1, title="a1", volume=v1)
    make_doc(me, ["b"], series=s, order=2, title="a2", volume=v1)
    make_doc(me, ["c"], series=s, order=3, title="b1", volume=v2)
    r = app_client.get(f"/series/{s.id}/export/markdown", params={"volume_id": v1.id})
    assert r.status_code == 200
    assert names_of(r) == ["001 - a1.md", "002 - a2.md"]
    assert quote("S - Vol 1.zip") in r.headers["content-disposition"]
    assert r.headers["x-ta-skipped-incomplete"] == "0"


def test_volume_zip_of_another_series_volume_is_404(app_client, db, me, make_series, make_doc):
    s, t = make_series(me, "S"), make_series(me, "T")
    v = _volume(db, t)
    make_doc(me, ["a"], series=t, order=1, volume=v)
    r = app_client.get(f"/series/{s.id}/export/markdown", params={"volume_id": v.id})
    assert r.status_code == 404


def test_volume_zip_of_another_users_volume_is_404(
    app_client, db, me, make_user, make_series, make_doc
):
    other = make_user(email="other@example.com")
    s = make_series(me, "S")
    t = make_series(other, "T")
    v = _volume(db, t)
    r = app_client.get(f"/series/{s.id}/export/markdown", params={"volume_id": v.id})
    assert r.status_code == 404


@pytest.mark.parametrize(
    ("fmt", "ext"), [("txt", "txt"), ("md", "md"), ("md-ruby", "md")]
)
def test_selection_zip_in_each_format(app_client, me, make_series, make_doc, fmt, ext):
    s = make_series(me, "S")
    a = make_doc(me, ["a"], series=s, order=2, title="Second")
    b = make_doc(me, ["b"], series=s, order=1, title="First")
    r = app_client.post(
        "/documents/export/zip", json={"document_ids": [a.id, b.id], "format": fmt}
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert 'filename="chapters.zip"' in r.headers["content-disposition"]
    assert names_of(r) == [f"001 - First.{ext}", f"002 - Second.{ext}"]
    if fmt == "txt":
        single = app_client.get(f"/documents/{a.id}/export", params={"format": "txt"})
        z = zipfile.ZipFile(io.BytesIO(r.content))
        assert z.read("002 - Second.txt") == single.content


def test_selection_zip_keeps_incomplete_chapters(app_client, me, make_series, make_doc):
    s = make_series(me, "S")
    a = make_doc(me, ["a"], series=s, order=1, title="A", translated=False)
    r = app_client.post("/documents/export/zip", json={"document_ids": [a.id], "format": "md"})
    assert r.status_code == 200
    assert names_of(r) == ["001 - A.md"]


def test_selection_zip_foreign_id_reads_like_missing(
    app_client, me, make_user, make_series, make_doc
):
    other = make_user(email="other@example.com")
    foreign = make_doc(other, ["x"], series=make_series(other), order=1)
    mine = make_doc(me, ["y"], order=1)
    f = app_client.post(
        "/documents/export/zip", json={"document_ids": [mine.id, foreign.id], "format": "txt"}
    )
    m = app_client.post(
        "/documents/export/zip", json={"document_ids": [mine.id, 999999], "format": "txt"}
    )
    assert f.status_code == m.status_code == 422
    assert f.json() == m.json()
    assert "document_ids: no such item" in str(f.json())


def test_selection_zip_caps_the_id_list(app_client, me):
    r = app_client.post(
        "/documents/export/zip", json={"document_ids": list(range(1, 502)), "format": "txt"}
    )
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "too_long"  # refused by the schema, not the lookup
