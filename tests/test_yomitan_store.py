import pytest

from api import server_settings
from api import yomitan_store as ys
from api.core.yomitan_read import FlatEntry, Meta, Parsed
from api.mt.jparser import DictEntry


def parsed(key="A", revision="r1", terms=None):
    entry = FlatEntry(("食べる",), "たべる", frozenset({"v1"}), "to eat")
    terms = terms if terms is not None else {"食べる": entry, "たべる": entry}
    meta = Meta(f"Dict {key}", revision, "attr", "auth", "http://x", key)
    return Parsed(meta, terms, len(terms), 0)


def test_install_then_fetch_returns_entries_by_token(db):
    inst = ys.install(db, parsed("A"))
    assert inst.replaced_revision is None
    tok = ys.token(inst.dictionary.id)
    assert tok == f"yomitan:{inst.dictionary.id}"
    got = ys.fetch(db, {"食べる", "nope"})
    assert got == {tok: {"食べる": DictEntry(
        ("食べる",), "たべる", frozenset({"v1"}), "to eat", False, True)}}
    assert ys.fetch(db, set()) == {}


def test_entry_without_pos_cannot_deconjugate(db):
    e = FlatEntry(("犬",), "いぬ", frozenset(), "dog")
    inst = ys.install(db, parsed("A", terms={"犬": e}))
    entry = ys.fetch(db, ["犬"])[ys.token(inst.dictionary.id)]["犬"]
    assert entry.deconj is False


def test_same_identity_replaces_in_place_and_keeps_position(db, make_user):
    uid = make_user().id
    a = ys.install(db, parsed("A", "r1")).dictionary
    b = ys.install(db, parsed("B")).dictionary
    ta, tb = ys.token(a.id), ys.token(b.id)
    ys.set_order(db, [tb, "edict", ta], uid)
    e = FlatEntry(("走る",), "はしる", frozenset({"v5r"}), "to run")
    again = ys.install(db, parsed("A", "r2", terms={"走る": e}))
    assert again.dictionary.id == a.id
    assert again.replaced_revision == "r1"
    assert again.dictionary.revision == "r2"
    assert ys.fetch(db, ["食べる"]).get(ta) is None
    assert "走る" in ys.fetch(db, ["走る"])[ta]
    assert ys.order(db) == [tb, "edict", ta]


def test_order_normalises_after_removal_and_for_new_installs(db, make_user):
    uid = make_user().id
    a = ys.install(db, parsed("A")).dictionary
    b = ys.install(db, parsed("B")).dictionary
    ys.set_order(db, [ys.token(a.id), "edict", ys.token(b.id)], uid)
    assert ys.remove(db, a.id) is True
    assert ys.remove(db, a.id) is False
    assert ys.order(db) == ["edict", ys.token(b.id)]
    c = ys.install(db, parsed("C")).dictionary
    assert ys.order(db) == ["edict", ys.token(b.id), ys.token(c.id)]


def test_set_order_rejects_non_permutations(db, make_user):
    uid = make_user().id
    a = ys.install(db, parsed("A")).dictionary
    ta = ys.token(a.id)
    for bad in (["edict"], ["edict", ta, ta], ["edict", ta, "yomitan:99999"], ["edict", ta, "x"]):
        with pytest.raises(ValueError, match="exactly once"):
            ys.set_order(db, bad, uid)


def test_order_row_is_not_an_admin_setting(db, make_user):
    uid = make_user().id
    ys.install(db, parsed("A"))
    ys.set_order(db, ys.order(db), uid)
    assert "dictionary_order" not in [r["key"] for r in server_settings.listing(db)]


def test_fetch_sends_one_array_parameter_for_huge_key_sets(db):
    inst = ys.install(db, parsed("A"))
    keys = [f"k{i}" for i in range(70_000)] + ["食べる"]
    got = ys.fetch(db, keys)
    assert list(got[ys.token(inst.dictionary.id)]) == ["食べる"]


def test_install_batches_and_remove_clears_terms(db):
    e = FlatEntry(("x",), "x", frozenset({"n"}), "g")
    terms = {f"w{i}": e for i in range(2500)}
    inst = ys.install(db, parsed("A", terms=terms))
    tok = ys.token(inst.dictionary.id)
    assert len(ys.fetch(db, list(terms))[tok]) == 2500
    ys.remove(db, inst.dictionary.id)
    assert ys.fetch(db, list(terms)) == {}
