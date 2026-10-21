"""Volumes are named by kind, decimal index and subtitle (spec 2026-10-21-volume-naming)."""

import io
from decimal import Decimal
from urllib.parse import quote

import pytest

from api.core.epub_read import open_book
from api.models import Volume
from api.routers.volumes import NAME_TAKEN


@pytest.fixture
def series(me, make_series):
    return make_series(me, "Mushoku")


def _post(client, series, **body):
    return client.post(f"/series/{series.id}/volumes", json=body)


def test_create_returns_names(app_client, series):
    r = _post(app_client, series, kind="Volume", volume_index="3.5", subtitle="Dawn")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["volume_index"] == "3.5"
    assert body["label"] == "Volume 3.5 · Dawn"
    assert body["full_title"] == "Mushoku - Volume 3.5 - Dawn"
    assert (body["kind"], body["subtitle"], body["wp_volume_title"]) == ("Volume", "Dawn", None)
    assert "title" not in body


def test_whole_index_is_serialised_without_zeros(app_client, series):
    r = _post(app_client, series, kind="Volume", volume_index="3.000")
    assert (r.status_code, r.json()["volume_index"], r.json()["label"]) == (201, "3", "Volume 3")


def test_minus_zero_index_is_zero(app_client, series):
    r = _post(app_client, series, kind="Volume", volume_index="-0")
    assert (r.status_code, r.json()["volume_index"], r.json()["label"]) == (201, "0", "Volume 0")
    vid = r.json()["id"]
    r = app_client.patch(f"/volumes/{vid}", json={"volume_index": "-0.000"})
    assert (r.status_code, r.json()["volume_index"]) == (200, "0")
    assert _post(app_client, series, kind="Volume", volume_index="0").status_code == 409


@pytest.mark.parametrize("index", ["3,5", "3.1234"])
def test_index_rejects_comma_and_four_decimals(app_client, series, index):
    assert _post(app_client, series, kind="Volume", volume_index=index).status_code == 422


def test_kind_is_trimmed_and_case_insensitive_unique(app_client, series):
    assert _post(app_client, series, kind="Volume", volume_index="1").status_code == 201
    r = _post(app_client, series, kind=" volume ", volume_index="1")
    assert r.status_code == 409 and r.json()["detail"] == NAME_TAKEN


def test_unnumbered_needs_distinct_subtitle(app_client, series):
    assert _post(app_client, series, kind="Extra", subtitle="Q&A").status_code == 201
    r = _post(app_client, series, kind="Extra", subtitle="Q&A")
    assert r.status_code == 409 and r.json()["detail"] == NAME_TAKEN
    assert _post(app_client, series, kind="Extra", subtitle="Afterword").status_code == 201


def test_all_empty_refused(app_client, series):
    assert _post(app_client, series, kind="", subtitle="").status_code == 422
    vid = _post(app_client, series, kind="Extra", subtitle="Q&A").json()["id"]
    r = app_client.patch(f"/volumes/{vid}", json={"kind": "", "subtitle": ""})
    assert r.status_code == 422


def test_patch_can_clear_the_index(app_client, series):
    vid = _post(app_client, series, kind="Volume", volume_index="2", subtitle="X").json()["id"]
    r = app_client.patch(f"/volumes/{vid}", json={"volume_index": None})
    assert (r.status_code, r.json()["volume_index"], r.json()["label"]) == (200, None, "Volume · X")


def test_patch_onto_an_existing_name_is_409(app_client, series):
    _post(app_client, series, kind="Volume", volume_index="1")
    vid = _post(app_client, series, kind="Volume", volume_index="2").json()["id"]
    r = app_client.patch(f"/volumes/{vid}", json={"volume_index": "1"})
    assert r.status_code == 409 and r.json()["detail"] == NAME_TAKEN


def test_epub_title_override_and_filename(app_client, db, me, make_series, make_doc):
    s = make_series(me, "S")
    v = Volume(series_id=s.id, kind="Vol", volume_index=Decimal(3), subtitle="A/B")
    db.add(v)
    db.flush()
    make_doc(me, ["一行目です。"], series=s, order=1, volume=v, translated=True)
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert r.status_code == 200, r.text
    assert quote("S - Vol 3 - A_B.epub") in r.headers["content-disposition"]
    assert open_book(io.BytesIO(r.content))["title"] == "S - Vol 3 - A/B"

    assert app_client.patch(f"/volumes/{v.id}", json={"epub_title": "Mine"}).status_code == 200
    r = app_client.get(f"/volumes/{v.id}/export/epub")
    assert quote("Mine.epub") in r.headers["content-disposition"]
    assert open_book(io.BytesIO(r.content))["title"] == "Mine"


def test_markdown_export_label_uses_full_title(app_client, db, me, make_series, make_doc):
    s = make_series(me, "S")
    v = Volume(series_id=s.id, kind="Volume", volume_index=Decimal(1), subtitle="Dawn",
               volume_order=1)
    db.add(v)
    db.flush()
    make_doc(me, ["a"], series=s, order=1, title="a1", volume=v)
    r = app_client.get(f"/series/{s.id}/export/markdown", params={"volume_id": v.id})
    assert r.status_code == 200
    assert quote("S - Volume 1 - Dawn.zip") in r.headers["content-disposition"]


def test_wp_name_prefers_the_frozen_title(db, me, make_series):
    s = make_series(me, "S")
    v = Volume(series_id=s.id, kind="Volume", volume_index=Decimal(3), subtitle="Journey")
    db.add(v)
    db.flush()
    assert v.wp_name == "Volume 3 - Journey"
    v.wp_volume_title = "Vol. 3"
    assert v.wp_name == "Vol. 3"


def test_series_template_drives_full_title(db, me, make_series):
    s = make_series(me, "S")
    assert s.volume_title_template == ""
    assert s.volume_title_template_effective == "{series} - {kind} {index} - {subtitle}"
    s.volume_title_template = "{kind} {index}: {subtitle}"
    v = Volume(series_id=s.id, kind="Volume", volume_index=Decimal(2), subtitle="X")
    db.add(v)
    db.flush()
    assert v.full_title == "Volume 2: X"
