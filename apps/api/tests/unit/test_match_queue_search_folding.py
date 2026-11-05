"""P-152: the match-queue search folds Arabic/Persian letter variants and matches word starts."""

from __future__ import annotations

import pytest

from procurepilot_api.modules.matching.search_text import (
    fold_search_text,
    search_matches,
    sql_fold_expression,
)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("زيت", "زیت"),  # Arabic yeh vs Persian yeh
        ("كريم", "کریم"),  # Arabic kaf vs Persian keheh
        ("أرز", "ارز"),  # alef with hamza vs bare alef
        ("إناء", "اناء"),
        ("آلة", "اله"),  # alef madda, teh marbuta vs heh
        ("مُلْح", "ملح"),  # tashkeel is dropped
        ("Olive OIL", "olive oil"),
    ],
)
def test_fold_collapses_letter_variants(left: str, right: str) -> None:
    assert fold_search_text(left) == fold_search_text(right)


def test_search_matches_word_prefix_not_substring() -> None:
    assert search_matches("oil", ["Olive oil 5L"])
    assert search_matches("oli", ["Olive oil 5L"])
    assert not search_matches("live", ["Olive oil 5L"])


def test_search_matches_phrase_prefix_across_words() -> None:
    assert search_matches("olive oi", ["Olive oil 5L"])
    assert not search_matches("oil olive", ["Olive oil 5L"])


def test_search_matches_folded_arabic() -> None:
    assert search_matches("زيت", ["زیت زيتون ٥ لتر"])
    assert search_matches("ارز", ["أرز بسمتي"])


def test_search_matches_any_haystack_and_ignores_none() -> None:
    assert search_matches("acme", [None, "Acme Foods"])
    assert not search_matches("acme", [None, ""])


def test_empty_term_matches_everything() -> None:
    assert search_matches("  ", ["anything"])


def test_sql_fold_expression_mirrors_python_fold() -> None:
    expr = sql_fold_expression("original_text")
    assert "translate(" in expr
    assert "regexp_replace(" in expr
    assert "original_text" in expr


def _ctx(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "original_text": "زیت زيتون ٥ لتر",
        "line_number": 12,
        "quotation_id": "ab12cd34-0000-0000-0000-000000000000",
        "supplier_name": "مطاعم رواق",
    }
    base.update(over)
    return base


def test_line_context_match_folds_and_uses_word_prefix() -> None:
    from procurepilot_api.modules.matching.service import _line_context_matches

    assert _line_context_matches("زيت", _ctx())  # Arabic yeh finds the Persian-yeh spelling
    assert _line_context_matches("رواق", _ctx())  # supplier name
    assert _line_context_matches("#12", _ctx())  # line number kept as substring
    assert _line_context_matches("ab12cd", _ctx())  # quotation id kept as substring
    assert not _line_context_matches("يتون", _ctx())  # mid-word is no longer a hit


def test_queue_sql_filter_folds_columns_and_skips_the_reason_code() -> None:
    from procurepilot_api.modules.matching.service import queue_search_filter_sql

    sql = queue_search_filter_sql()
    assert "reason" not in sql  # an internal code, not something a buyer reads
    assert "translate(" in sql
    assert "%(search_folded)s" in sql
    assert "original_text" in sql and "supplier_name" in sql
