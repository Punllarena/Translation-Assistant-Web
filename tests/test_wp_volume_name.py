# ruff: noqa: E501
import json
from contextlib import contextmanager
from decimal import Decimal

import httpx
import pytest

from api import jobs, publish_job
from api.models import DocumentImage, Volume
from api.routers import wp as wp_router

SITE = "https://blog.example.com"
PUBLISH = "/wp-json/ta-publisher/v1/publish"
STATUS = "/wp-json/ta-publisher/v1/status"
ILLUS = "/wp-json/ta-publisher/v1/illustrations"
NAME = "Volume 3 - The Journey"


@pytest.fixture
def wp(monkeypatch, db):
    """One fake WordPress behind both the request handler and the job handlers."""
    state = {"posted": [], "publish": {"created": True, "updated": False, "page_url": "pg", "post_url": "po"}}

    def handle(request):
        if request.url.path == STATUS:
            return httpx.Response(200, json={"status": "not_found", "post_url": None})
        state["posted"].append((request.url.path, json.loads(request.content)))
        if request.url.path == ILLUS:
            return httpx.Response(200, json={"created": True, "page_url": "pg"})
        return httpx.Response(200, json=state["publish"])

    def client():
        return wp_router.wp_http.client(transport=httpx.MockTransport(handle))

    monkeypatch.setattr(wp_router, "http_client", client)
    monkeypatch.setattr(publish_job, "http_client", client)
    monkeypatch.setattr("api.publish.check_user_url", lambda url, allow, label: None)

    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    return state


@pytest.fixture
def vol(app_client, me, make_series, make_doc, db):
    app_client.post("/credentials", json={"kind": "wordpress", "secret": "k" * 12, "endpoint_url": SITE})
    s = make_series(me, "Sword")
    s.wp_series_slug, s.wp_series_title_short = "sword", "SotW"
    v = Volume(series_id=s.id, kind="Volume", volume_index=Decimal(3), subtitle="The Journey")
    db.add(v)
    db.flush()
    doc = make_doc(me, ["一"], series=s, order=1, volume=v)
    db.add(DocumentImage(document_id=doc.id, anchor_position=0, src_path="a.png", data=b"A"))
    db.flush()
    return v, s, doc


def sent_titles(wp):
    return [b["doc_meta"]["volume_title"] if "doc_meta" in b else b["volume_title"] for _, b in wp["posted"]]


def marked(me, make_doc, s, v, db):
    doc = make_doc(me, [], series=s, order=0, volume=v, title="Illustrations")
    doc.is_illustrations = True
    db.flush()
    return doc


def test_first_chapter_publish_freezes_name(app_client, vol, wp, db):
    v, _, doc = vol
    assert v.wp_volume_title is None
    assert app_client.post(f"/documents/{doc.id}/wp/publish", json={}).status_code == 200
    assert sent_titles(wp) == [NAME]
    db.refresh(v)
    assert v.wp_volume_title == NAME


def test_frozen_name_survives_renames(app_client, me, make_doc, vol, wp, db):
    v, s, doc = vol
    app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert app_client.patch(f"/volumes/{v.id}", json={"subtitle": "New"}).status_code == 200
    assert app_client.patch(f"/series/{s.id}", json={"volume_title_template": "{kind} {index}: {subtitle}"}).status_code == 200
    app_client.post(f"/documents/{doc.id}/wp/publish", json={"confirm_republish": True})
    r = app_client.post(f"/documents/{marked(me, make_doc, s, v, db).id}/wp/illustrations", json={})
    assert r.status_code == 202
    jobs.run_next()
    assert sent_titles(wp) == [NAME, NAME, NAME]


def test_failed_or_409_publish_does_not_freeze(app_client, vol, wp, db):
    v, _, doc = vol
    wp["publish"] = {"created": False, "updated": False, "page_url": "", "post_url": ""}
    app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    db.refresh(v)
    assert v.wp_volume_title is None


def test_batch_publish_freezes_name(app_client, vol, wp, db):
    v, _, doc = vol
    r = app_client.post("/wp/batch", json={"document_ids": [doc.id], "schedule": False})
    assert r.status_code == 202
    jobs.run_next()
    db.refresh(v)
    assert v.wp_volume_title == NAME


def test_illustrations_first_publish_freezes(app_client, me, make_doc, vol, wp, db):
    v, s, _ = vol
    r = app_client.post(f"/documents/{marked(me, make_doc, s, v, db).id}/wp/illustrations", json={})
    assert r.status_code == 202
    jobs.run_next()
    assert sent_titles(wp) == [NAME]
    db.refresh(v)
    assert v.wp_volume_title == NAME


def test_volume_out_shows_frozen_name(app_client, vol, wp, db):
    v, s, doc = vol
    assert app_client.get(f"/series/{s.id}/volumes").json()[0]["wp_volume_title"] is None
    app_client.post(f"/documents/{doc.id}/wp/publish", json={})
    assert app_client.get(f"/series/{s.id}/volumes").json()[0]["wp_volume_title"] == NAME
