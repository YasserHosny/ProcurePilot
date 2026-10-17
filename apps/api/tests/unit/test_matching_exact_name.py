from __future__ import annotations

import pytest

from procurepilot_api.modules.matching.exact import is_exact_name_match, normalise_name


@pytest.mark.parametrize(
    ("line", "product"),
    [
        ("سكر (شيكارة 25 كجم)", "سكر (شيكارة 25 كجم)"),
        ("  Sugar   25kg ", "sugar 25KG"),
        ("Ｓugar 25kg", "Sugar 25kg"),
    ],
)
def test_exact_after_normalisation(line: str, product: str) -> None:
    assert is_exact_name_match(line, product)


@pytest.mark.parametrize(
    ("line", "product"),
    [
        ("Sugar 25kg", "Sugar 50kg"),
        ("Sugar 25kg", "Sugar 25kg white"),
        ("", ""),
        (None, None),
    ],
)
def test_near_or_empty_is_not_exact(line: object, product: object) -> None:
    assert not is_exact_name_match(line, product)


def test_normalise_collapses_whitespace_and_case() -> None:
    assert normalise_name(" A\tB\n c ") == "a b c"
