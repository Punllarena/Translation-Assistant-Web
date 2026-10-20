from api.models import Document, GlossaryEntry, Profile, Series

SEP = "---SEPERATOR---"


def txt(name, raw="一行目", tr=""):
    return ("files", (name, f"%{raw}\n{SEP}\n{tr}\n".encode(), "text/plain"))


def test_imports_in_natural_order_after_existing_chapters(
    app_client, me, make_series, make_doc, db
):
    s = make_series(me, "S")
    make_doc(me, ["x"], series=s, order=1, title="Existing")
    r = app_client.post(
        "/documents/import/batch",
        data={"series_id": s.id},
        files=[txt("ch10.txt"), txt("ch2.txt"), txt("Existing.txt")],
    )
    out = r.json()
    assert r.status_code == 201
    assert out["imported"] == ["ch2", "ch10"] and out["skipped"] == ["Existing"]
    docs = db.query(Document).filter_by(series_id=s.id).order_by(Document.series_order).all()
    assert [(d.title, d.series_order) for d in docs] == [("Existing", 1), ("ch2", 2), ("ch10", 3)]


def test_bad_files_are_reported_and_the_rest_imported(app_client, me, db):
    out = app_client.post(
        "/documents/import/batch",
        data={"series_title": "S"},
        files=[
            txt("good.txt"),
            ("files", ("nosep.txt", b"just text", "text/plain")),
            ("files", ("latin.txt", "é\n".encode("latin-1"), "text/plain")),
            ("files", ("pic.png", b"\x89PNG", "image/png")),
        ],
    ).json()
    assert out["imported"] == ["good"]
    assert sorted(e["name"] for e in out["errors"]) == ["latin.txt", "nosep.txt", "pic.png"]
    assert db.query(Document).count() == 1


def test_one_csv_becomes_a_profile_for_the_new_series(app_client, me, db):
    out = app_client.post(
        "/documents/import/batch",
        data={"series_title": "Fresh"},
        files=[txt("a.txt"), ("files", ("Names.csv", "猫,Cat\n".encode(), "text/csv"))],
    ).json()
    profile = db.get(Profile, out["profile_id"])
    assert profile.name == "Names"
    assert db.query(GlossaryEntry).filter_by(profile_id=profile.id).one().translation == "Cat"
    assert db.get(Series, out["series_id"]).profile_id == profile.id


def test_two_csvs_warn_and_import_no_glossary(app_client, me, db):
    out = app_client.post(
        "/documents/import/batch",
        data={"series_title": "S"},
        files=[
            txt("a.txt"),
            ("files", ("x.csv", b"a,b\n", "text/csv")),
            ("files", ("y.csv", b"c,d\n", "text/csv")),
        ],
    ).json()
    assert out["profile_id"] is None and "CSV" in out["warnings"][0]


def test_series_rules(app_client, me, make_series, make_user):
    theirs = make_series(make_user(email="o@example.com"), "T")
    assert (
        app_client.post(
            "/documents/import/batch", data={"series_id": theirs.id}, files=[txt("a.txt")]
        ).status_code
        == 422
    )
    assert (
        app_client.post(
            "/documents/import/batch",
            data={"series_id": 1, "series_title": "x"},
            files=[txt("a.txt")],
        ).status_code
        == 422
    )


def test_nul_in_series_title_is_422(app_client, me):
    r = app_client.post(
        "/documents/import/batch", data={"series_title": "a\x00b"}, files=[txt("a.txt")]
    )
    assert r.status_code == 422


def test_batch_total_cap_is_413_and_rolls_back(app_client, me, db, monkeypatch):
    one = len(txt("a.txt")[1][1])
    monkeypatch.setattr("api.routers.transfer.MAX_BATCH_BYTES", one + 1)
    r = app_client.post(
        "/documents/import/batch", data={"series_title": "S"}, files=[txt("a.txt"), txt("b.txt")]
    )
    assert r.status_code == 413
    db.rollback()
    assert db.query(Document).count() == 0 and db.query(Series).count() == 0


def test_a_long_series_title_is_422(app_client, me, db):
    r = app_client.post("/documents/import/batch", data={"series_title": "x" * 301},
                        files=[txt("a.txt")])
    assert r.status_code == 422 and db.query(Series).count() == 0
