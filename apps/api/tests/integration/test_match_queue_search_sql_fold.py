"""P-152: the SQL fold executes on real Postgres and agrees with ``fold_search_text``."""

from __future__ import annotations

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from procurepilot_api.db import connect
from procurepilot_api.modules.matching.search_text import (
    fold_search_text,
    search_matches,
    search_words,
    sql_fold_expression,
)

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="needs TEST_DATABASE_URL")

SAMPLES = [
    "زیت زيتون",
    "كريم کریم",
    "أرز إناء آلة ٱبن",
    "مُلْح ـــ طعام",
    "Olive OIL 5L",
    "بیض",
]


def test_sql_fold_equals_python_fold() -> None:
    expr = sql_fold_expression("t")
    with connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
        for text in SAMPLES:
            cur.execute(f"select {expr} from (select %s::text as t) v", (text,))
            row = cur.fetchone()
            assert row is not None
            assert row[0] == fold_search_text(text), text


def test_sql_word_start_agrees_with_python() -> None:
    from procurepilot_api.modules.matching.service import (
        _escape_like,
        queue_search_filter_sql,
    )

    sql = queue_search_filter_sql(has_words=True)
    cases = [
        ("زيت", "زیت زيتون", "x"),
        ("oil", "Olive\noil", "x"),
        ("live", "Olive/oil", "x"),
        ("يتون", "زيتون", "x"),
        ("olive-oil", "Olive / oil", "x"),
        ("شمس", "زيت عباد الشمس", "x"),
        ("أرز", "الأرز البسمتي", "x"),
        ("مس", "زيت عباد الشمس", "x"),
    ]
    with connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
        for term, text, supplier in cases:
            cur.execute(
                "select " + sql + " from (select %(t)s::text as original_text, "
                "%(s)s::text as supplier_name, '00000000-0000-0000-0000-000000000000'::uuid "
                "as quotation_id, 1 as line_number) v",
                {
                    "t": text,
                    "s": supplier,
                    "search_ids": _escape_like(term.lower()),
                    "search_folded": _escape_like(search_words(term)),
                },
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == search_matches(term, [text, supplier]), (term, text)
