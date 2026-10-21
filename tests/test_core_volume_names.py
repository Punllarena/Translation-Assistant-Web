import json
from decimal import Decimal
from pathlib import Path

import pytest

from api.core.volume_names import (
    DEFAULT_TEMPLATE,
    ParsedName,
    format_index,
    label,
    parse_title,
    render,
    sort_key,
    validate_template,
    wp_label,
)

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "web/src/library/volumeNames.cases.json").read_text(
        encoding="utf-8"
    )
)


def _dec(s):
    return Decimal(s) if s is not None else None


@pytest.mark.parametrize("case", CASES["format_index"])
def test_format_index(case):
    assert format_index(_dec(case["in"])) == case["out"]


@pytest.mark.parametrize("case", CASES["render"])
def test_render(case):
    got = render(
        case["template"],
        series=case["series"],
        kind=case["kind"],
        index=_dec(case["index"]),
        subtitle=case["subtitle"],
    )
    assert got == case["out"]


@pytest.mark.parametrize("case", CASES["label"])
def test_label(case):
    args = (case["kind"], _dec(case["index"]), case["subtitle"])
    assert label(*args) == case["out"]
    assert wp_label(*args) == case["wp"]


@pytest.mark.parametrize("case", CASES["parse"])
def test_parse(case):
    got = parse_title(case["title"], case["series"])
    assert got == ParsedName(case["kind"], _dec(case["index"]), case["subtitle"])


@pytest.mark.parametrize("t", CASES["templates_invalid"])
def test_invalid_template(t):
    with pytest.raises(ValueError):
        validate_template(t)


def test_default_template_valid():
    assert validate_template(DEFAULT_TEMPLATE) is None


def test_sort_key_orders_kinds():
    items = [
        ("Volume", Decimal(2)),
        ("Volume", Decimal(10)),
        ("Volume", None),
        ("extra", Decimal(1)),
        ("Side Story", Decimal(1)),
        ("", Decimal(1)),
    ]
    shuffled = [items[i] for i in (4, 2, 5, 0, 3, 1)]
    assert sorted(shuffled, key=lambda kv: sort_key(*kv)) == items
