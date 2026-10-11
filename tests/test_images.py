import pytest

from api.models import DocumentImage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.fixture
def doc(me, make_doc):
    return make_doc(me, ["a", "b"])


def _image(db, doc, data=PNG, anchor=0, **kw):
    image = DocumentImage(
        document_id=doc.id, anchor_position=anchor, src_path="i.png", data=data, **kw
    )
    db.add(image)
    db.flush()
    return image


def test_list_is_ordered_by_anchor_without_bytes(app_client, db, doc):
    late, early = _image(db, doc, anchor=2), _image(db, doc, anchor=1)
    body = app_client.get(f"/documents/{doc.id}/images").json()
    assert [i["id"] for i in body] == [early.id, late.id]
    assert "data" not in body[0]


def test_get_serves_bytes_with_sniffed_type(app_client, db, doc):
    r = app_client.get(f"/images/{_image(db, doc).id}")
    assert (r.status_code, r.content, r.headers["content-type"]) == (200, PNG, "image/png")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "private" in r.headers["cache-control"]


def test_unrecognised_image_is_never_served_as_svg(app_client, db, doc):
    r = app_client.get(f"/images/{_image(db, doc, data=SVG).id}")
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_patch_exclude_export(app_client, db, doc):
    image = _image(db, doc)
    r = app_client.patch(f"/images/{image.id}", json={"exclude_export": True})
    assert (r.status_code, r.json()["exclude_export"]) == (200, True)


def test_patch_null_is_422(app_client, db, doc):
    image = _image(db, doc)
    assert app_client.patch(f"/images/{image.id}", json={"exclude_export": None}).status_code == 422


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/documents/{doc}/images", {}),
        ("get", "/images/{image}", {}),
        ("patch", "/images/{image}", {"json": {"exclude_export": True}}),
    ],
)
def test_another_users_images_are_404(
    app_client, db, me, make_user, make_doc, method, path, kwargs
):
    theirs = make_doc(make_user(email="other@example.com"), ["x"])
    image = _image(db, theirs)
    url = path.format(doc=theirs.id, image=image.id)
    assert getattr(app_client, method)(url, **kwargs).status_code == 404
