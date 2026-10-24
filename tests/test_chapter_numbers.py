from api.library import chapter_number, chapter_numbers, previous_chapter
from api.models import Series, Volume


def _vols(db, series, n=2):
    vols = [Volume(series_id=series.id, subtitle=f"V{i}", volume_order=i) for i in range(1, n + 1)]
    db.add_all(vols)
    db.flush()
    return vols


def test_numbers_skip_the_illustrations_chapter(db, me, make_series, make_doc):
    series = make_series(me)
    v1, v2 = _vols(db, series)
    illus = make_doc(me, series=series, volume=v1, order=1, title="i")
    a = make_doc(me, series=series, volume=v1, order=2, title="a")
    b = make_doc(me, series=series, volume=v1, order=3, title="b")
    illus2 = make_doc(me, series=series, volume=v2, order=4, title="i2")
    c = make_doc(me, series=series, volume=v2, order=5, title="c")
    illus.is_illustrations = illus2.is_illustrations = True
    db.flush()
    docs = [c, illus2, b, a, illus]
    assert chapter_numbers(docs, set()) == {
        illus.id: None, a.id: 1, b.id: 2, illus2.id: None, c.id: 3,
    }
    assert chapter_number(db, c) == 3 and chapter_number(db, illus) is None
    assert chapter_number(db, a) == 1


def test_syosetu_series_number_is_series_order(db, me, make_series, make_doc):
    series = make_series(me)
    series.syosetu_url = "https://ncode.syosetu.com/n0000a/"
    (v1,) = _vols(db, series, 1)
    illus = make_doc(me, series=series, volume=v1, order=1, title="i")
    a = make_doc(me, series=series, volume=v1, order=5, title="a")
    illus.is_illustrations = True
    db.flush()
    assert chapter_number(db, a) == 5
    assert chapter_numbers([illus, a], {series.id}) == {illus.id: None, a.id: 5}


def test_synopsis_zero_stays_zero(db, me, make_series, make_doc):
    series = make_series(me)
    syn = make_doc(me, series=series, order=0, title="syn")
    a = make_doc(me, series=series, order=1, title="a")
    assert chapter_number(db, syn) == 0
    assert chapter_numbers([syn, a], set()) == {syn.id: 0, a.id: 1}


def test_previous_chapter_skips_illustrations(db, me, make_series, make_doc):
    series = make_series(me)
    v1, v2 = _vols(db, series)
    make_doc(me, series=series, volume=v1, order=1, title="a")
    b = make_doc(me, series=series, volume=v1, order=2, title="b")
    illus2 = make_doc(me, series=series, volume=v2, order=3, title="i2")
    c = make_doc(me, series=series, volume=v2, order=4, title="c")
    illus2.is_illustrations = True
    db.flush()
    assert previous_chapter(db, c) is b
    assert previous_chapter(db, b).title == "a"


def test_previous_chapter_syosetu_needs_exact_minus_one(db, me, make_series, make_doc):
    series = make_series(me)
    series.syosetu_url = "https://ncode.syosetu.com/n0000a/"
    make_doc(me, series=series, order=1, title="a")
    b = make_doc(me, series=series, order=2, title="b")
    d = make_doc(me, series=series, order=4, title="d")
    db.flush()
    assert previous_chapter(db, b).title == "a"
    assert previous_chapter(db, d) is None


def test_list_documents_reports_chapter_number(app_client, db, me, make_series, make_doc):
    series = make_series(me)
    (v1,) = _vols(db, series, 1)
    illus = make_doc(me, series=series, volume=v1, order=1, title="i")
    a = make_doc(me, series=series, volume=v1, order=2, title="a")
    illus.is_illustrations = True
    db.flush()
    rows = {r["id"]: r for r in app_client.get("/documents").json()}
    assert rows[illus.id]["chapter_number"] is None and rows[illus.id]["is_illustrations"]
    assert rows[a.id]["chapter_number"] == 1 and not rows[a.id]["is_illustrations"]
    assert isinstance(db.get(Series, series.id), Series)
