import io

from api.core.series_titles import free_title
from api.models import Document


def test_free_title_appends_the_first_free_suffix():
    assert free_title(set(), "Oneshot") == "Oneshot"
    assert free_title({"Oneshot"}, "Oneshot") == "Oneshot (2)"
    assert free_title({"Oneshot", "Oneshot (2)"}, "Oneshot") == "Oneshot (3)"


def test_create_without_series_is_422(app_client, me):
    assert app_client.post("/documents", json={"title": "T"}).status_code == 422


def test_patch_series_null_is_422(app_client, me, make_doc):
    doc = make_doc(me)
    assert app_client.patch(f"/documents/{doc.id}", json={"series_id": None}).status_code == 422


def test_txt_import_without_series_is_422(app_client, me):
    files = {"file": ("a.txt", io.BytesIO("一\n".encode()), "text/plain")}
    assert app_client.post("/documents/import/txt", files=files).status_code == 422


def test_batch_import_without_series_is_422(app_client, me):
    files = [("files", ("a.txt", io.BytesIO("一\n".encode()), "text/plain"))]
    assert app_client.post("/documents/import/batch", files=files).status_code == 422


def test_deleting_a_series_deletes_its_chapters(app_client, db, me, make_series, make_doc):
    series = make_series(me)
    doc = make_doc(me, ["一"], series=series)
    doc_id = doc.id
    assert app_client.delete(f"/series/{series.id}").status_code == 204
    db.expire_all()
    assert db.get(Document, doc_id) is None  # lines and images go by existing cascades
