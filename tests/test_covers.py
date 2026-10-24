import httpx
import pytest

from api import covers
from api.models import Volume, VolumeCover
from api.routers import covers as covers_router

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPG = b"\xff\xd8\xff" + b"\x00" * 16


@pytest.fixture
def vol(db, me, make_series):
    series = make_series(me, "S")
    v1 = Volume(series_id=series.id, subtitle="One", volume_order=1)
    v2 = Volume(series_id=series.id, subtitle="Two", volume_order=2)
    db.add_all([v1, v2])
    db.flush()
    return series, v1, v2


def _vols(client, series_id):
    return {v["subtitle"]: v for v in client.get(f"/series/{series_id}/volumes").json()}


def _put(client, volume_id, data=PNG, name="c.png"):
    return client.put(f"/volumes/{volume_id}/cover", files={"file": (name, data, "image/png")})


@pytest.fixture
def site(monkeypatch):
    """A fake web: url -> httpx.Response (or a callable). Hosts named private-* resolve
    private; requests that reach the transport are recorded."""
    pages: dict[str, object] = {}
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        answer = pages.get(str(request.url))
        if answer is None:
            return httpx.Response(404)
        if callable(answer):
            return answer(request)
        if answer.is_stream_consumed:  # built with content=: re-serve as a
            return httpx.Response(answer.status_code, headers=answer.headers,  # raw stream
                                  stream=httpx.ByteStream(answer.content))
        return answer

    def check(url, allow_private, label):
        host = httpx.URL(url).host
        return "private" if host.startswith("private") or host == "127.0.0.1" else None

    monkeypatch.setattr(covers, "check_url", check)
    monkeypatch.setattr(covers_router, "http_client",
                        lambda: covers.client(transport=httpx.MockTransport(handle)))
    return pages, seen


def test_upload_sets_the_cover_and_serves_it(app_client, vol):
    series, v1, _ = vol
    r = _put(app_client, v1.id)
    assert r.status_code == 200 and r.json()["volume_id"] == v1.id
    assert _vols(app_client, series.id)["One"]["cover_id"] == r.json()["id"]
    img = app_client.get(f"/covers/{r.json()['id']}")
    assert img.status_code == 200 and img.content == PNG
    assert img.headers["content-type"] == "image/png"
    assert "immutable" in img.headers["cache-control"]


def test_replacing_makes_a_new_id_and_keeps_one_row(app_client, db, vol):
    _, v1, _ = vol
    first = _put(app_client, v1.id).json()["id"]
    second = _put(app_client, v1.id, JPG, "c.jpg").json()["id"]
    assert first != second
    assert [c.src_path for c in db.query(VolumeCover).filter_by(volume_id=v1.id)] == ["cover.jpg"]
    assert app_client.get(f"/covers/{first}").status_code == 404


def test_a_non_image_is_415(app_client, vol):
    assert _put(app_client, vol[1].id, b"<svg/>").status_code == 415


def test_upload_size_is_capped(app_client, vol, monkeypatch):
    monkeypatch.setattr(covers, "MAX_IMAGE_BYTES", 8)
    assert _put(app_client, vol[1].id).status_code == 413


def test_clear_is_idempotent(app_client, vol):
    series, v1, _ = vol
    _put(app_client, v1.id)
    assert app_client.delete(f"/volumes/{v1.id}/cover").status_code == 204
    assert app_client.delete(f"/volumes/{v1.id}/cover").status_code == 204
    assert _vols(app_client, series.id)["One"]["cover_id"] is None


def test_another_users_volume_and_cover_are_404(app_client, db, me, make_user, make_series):
    theirs = make_series(make_user(email="other@example.com"), "Theirs")
    v = Volume(series_id=theirs.id, subtitle="X")
    db.add(v)
    db.flush()
    cover = covers.set_cover(db, v.id, PNG, "cover.png")
    assert _put(app_client, v.id).status_code == 404
    assert app_client.delete(f"/volumes/{v.id}/cover").status_code == 404
    assert app_client.post(f"/volumes/{v.id}/cover/url", json={"url": "https://x/a.png"}
                           ).status_code == 404
    assert app_client.get(f"/covers/{cover.id}").status_code == 404
    assert app_client.put(f"/series/{theirs.id}/cover-volume",
                          json={"volume_id": v.id}).status_code == 404


def test_fetch_by_image_address(app_client, vol, site):
    pages, _ = site
    series, v1, _ = vol
    pages["https://img.example/c.jpg"] = httpx.Response(200, content=JPG,
                                                        headers={"content-type": "image/jpeg"})
    r = app_client.post(f"/volumes/{v1.id}/cover/url", json={"url": " https://img.example/c.jpg "})
    assert r.status_code == 200 and r.json()["src_path"] == "cover.jpg"
    assert app_client.get(f"/covers/{r.json()['id']}").content == JPG


def test_a_page_link_is_a_clear_422(app_client, vol, site):
    pages, _ = site
    pages["https://shop.example/dp/1"] = httpx.Response(
        200, text="<html></html>", headers={"content-type": "text/html; charset=utf-8"})
    r = app_client.post(f"/volumes/{vol[1].id}/cover/url", json={"url": "https://shop.example/dp/1"})
    assert r.status_code == 422 and r.json()["detail"] == covers.PAGE_LINK


def test_other_non_images_are_415(app_client, vol, site):
    pages, _ = site
    pages["https://img.example/x.bin"] = httpx.Response(200, content=b"nope")
    r = app_client.post(f"/volumes/{vol[1].id}/cover/url", json={"url": "https://img.example/x.bin"})
    assert r.status_code == 415


def test_a_body_past_the_cap_is_413(app_client, vol, site, monkeypatch):
    pages, _ = site
    monkeypatch.setattr(covers, "MAX_IMAGE_BYTES", 32)
    pages["https://img.example/big.png"] = httpx.Response(
        200, stream=httpx.ByteStream(PNG + b"\x00" * 64))  # no Content-Length
    r = app_client.post(f"/volumes/{vol[1].id}/cover/url",
                        json={"url": "https://img.example/big.png"})
    assert r.status_code == 413


def test_a_redirect_to_a_private_address_is_refused_before_it_is_sent(app_client, vol, site):
    pages, seen = site
    pages["https://img.example/r"] = httpx.Response(
        302, headers={"location": "http://127.0.0.1/secret.png"})
    r = app_client.post(f"/volumes/{vol[1].id}/cover/url", json={"url": "https://img.example/r"})
    assert r.status_code == 422 and r.json()["detail"] == "private"
    assert seen == ["https://img.example/r"]


def test_a_private_address_is_refused(app_client, vol, site):
    _, seen = site
    r = app_client.post(f"/volumes/{vol[1].id}/cover/url",
                        json={"url": "http://private-nas/c.png"})
    assert r.status_code == 422 and seen == []


def test_too_many_redirects_is_422(app_client, vol, site):
    pages, _ = site
    for n in range(5):
        pages[f"https://img.example/{n}"] = httpx.Response(
            302, headers={"location": f"https://img.example/{n + 1}"})
    r = app_client.post(f"/volumes/{vol[1].id}/cover/url", json={"url": "https://img.example/0"})
    assert r.status_code == 422


def test_an_upstream_error_is_502(app_client, vol, site):
    r = app_client.post(f"/volumes/{vol[1].id}/cover/url", json={"url": "https://img.example/gone"})
    assert r.status_code == 502 and "404" in r.json()["detail"]


def test_choosing_the_series_cover(app_client, db, vol, make_series, me):
    series, v1, v2 = vol
    url = f"/series/{series.id}/cover-volume"
    assert app_client.put(url, json={"volume_id": v1.id}).status_code == 204
    assert app_client.put(url, json={"volume_id": v2.id}).status_code == 204
    flags = {k: v["is_series_cover"] for k, v in _vols(app_client, series.id).items()}
    assert flags == {"One": False, "Two": True}
    assert app_client.put(url, json={"volume_id": None}).status_code == 204
    assert not any(v["is_series_cover"] for v in _vols(app_client, series.id).values())
    other = Volume(series_id=make_series(me, "Other").id, subtitle="X")
    db.add(other)
    db.flush()
    assert app_client.put(url, json={"volume_id": other.id}).status_code == 422


def test_effective_series_cover_falls_back(app_client, db, vol):
    series, v1, v2 = vol
    assert covers.effective_series_cover(db, series.id) is None
    two = covers.set_cover(db, v2.id, PNG, "two.png")
    assert covers.effective_series_cover(db, series.id).id == two.id
    one = covers.set_cover(db, v1.id, PNG, "one.png")
    assert covers.effective_series_cover(db, series.id).id == one.id  # first by order
    app_client.put(f"/series/{series.id}/cover-volume", json={"volume_id": v2.id})
    assert covers.effective_series_cover(db, series.id).id == two.id
    db.query(VolumeCover).filter_by(volume_id=v2.id).delete()
    assert covers.effective_series_cover(db, series.id).id == one.id  # chosen has none


def test_merge_keeps_one_cover_and_the_choice(app_client, db, vol):
    series, v1, v2 = vol
    two = covers.set_cover(db, v2.id, PNG, "two.png")
    v3 = Volume(series_id=series.id, subtitle="Three", volume_order=3)
    db.add(v3)
    db.flush()
    covers.set_cover(db, v3.id, PNG, "three.png")
    app_client.put(f"/series/{series.id}/cover-volume", json={"volume_id": v3.id})
    r = app_client.post(f"/series/{series.id}/volumes/merge",
                        json={"volume_ids": [v1.id, v2.id, v3.id], "into": v1.id})
    assert r.status_code == 200
    assert r.json()["cover_id"] == two.id and r.json()["is_series_cover"] is True
    assert db.query(VolumeCover).count() == 1


def test_deleting_the_volume_takes_its_cover(app_client, db, vol):
    _, v1, _ = vol
    _put(app_client, v1.id)
    assert app_client.delete(f"/volumes/{v1.id}").status_code == 204
    assert db.query(VolumeCover).count() == 0


def test_a_download_past_the_deadline_is_502(app_client, vol, site, monkeypatch):
    pages, _ = site
    monkeypatch.setattr(covers, "TOTAL_SECONDS", -1)
    pages["https://img.example/slow.png"] = httpx.Response(200, content=PNG)
    r = app_client.post(f"/volumes/{vol[1].id}/cover/url",
                        json={"url": "https://img.example/slow.png"})
    assert r.status_code == 502 and "too long" in r.json()["detail"]
