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


def test_word_start_after_any_separator() -> None:
    assert search_matches("oil", ["Olive\noil 5L"])  # newline
    assert search_matches("oil", ["Olive/oil"])
    assert search_matches("oil", ["Olive (oil)"])
    assert search_matches("زيت", ["زيتون،زيت"])  # Arabic comma
    assert search_matches("olive  oil", ["Olive - oil"])  # needle spacing is collapsed
    assert not search_matches("live", ["Olive/oil"])


def test_sql_filter_escapes_id_arms_and_matches_hash_line_number() -> None:
    from procurepilot_api.modules.matching.service import queue_search_filter_sql

    sql = queue_search_filter_sql()
    assert "'#' || line_number::text" in sql
    assert "%(search_ids)s" in sql  # escaped term for the id arms
    assert "%(search)s" not in sql


def test_line_context_match_hash_number_in_python_and_sql_agree() -> None:
    from procurepilot_api.modules.matching.service import _line_context_matches

    assert _line_context_matches("#12", _ctx())


@pytest.mark.parametrize("term", ["%", "-", ".", "#", " ", "ً"])
def test_separator_only_term_does_not_match_every_name(term: str) -> None:
    from procurepilot_api.modules.matching.service import (
        _line_context_matches,
        queue_search_filter_sql,
    )

    assert not _line_context_matches(term, _ctx(line_number=7, quotation_id="zz"))
    # The SQL predicate for a term with no word keeps only the id arms.
    assert "original_text" not in queue_search_filter_sql(has_words=False)
    assert queue_search_filter_sql(has_words=False, has_ids=False) == "false"
    assert "original_text" in queue_search_filter_sql(has_words=True)


def test_needle_matches_after_the_attached_definite_article() -> None:
    assert search_matches("شمس", ["زيت عباد الشمس"])
    assert search_matches("أرز", ["الأرز البسمتي"])
    assert search_matches("الشمس", ["زيت عباد الشمس"])
    assert not search_matches("مس", ["زيت عباد الشمس"])


def test_sql_filter_has_the_article_arm() -> None:
    from procurepilot_api.modules.matching.service import queue_search_filter_sql

    assert "'%% ال'" in queue_search_filter_sql(has_words=True)
