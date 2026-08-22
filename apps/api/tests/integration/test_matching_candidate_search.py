from __future__ import annotations

from uuid import UUID

import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
    make_workspace,
    psycopg,
)
from procurepilot_api.modules.matching.embeddings import StubEmbeddingProvider, vector_literal

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with chunk 4.4 matching migrations",
)

PROVIDER = StubEmbeddingProvider()


@pytest.fixture
def conn() -> object:
    yield from connection()


def _make_embedded_product(
    cur: psycopg.Cursor, workspace: object, *, brand: str, name: str, tenant_name: str
) -> UUID:
    from uuid import uuid4

    canonical_id, product_id = uuid4(), uuid4()
    cur.execute("reset role")
    cur.execute(
        "insert into canonical_product (id,brand,name,base_unit,canonical_embedding,"
        "canonical_embedding_model) values (%s,%s,%s,'litre',%s,%s)",
        (
            canonical_id,
            brand,
            name,
            vector_literal(PROVIDER.embed(f"{brand} {name}")),
            PROVIDER.model,
        ),
    )
    act_as(cur, workspace)
    cur.execute(
        "insert into workspace_product "
        "(id,tenant_id,canonical_product_id,tenant_name,tenant_name_embedding,"
        "tenant_name_embedding_model) values (%s,%s,%s,%s,%s,%s)",
        (
            product_id,
            workspace.tenant_id,
            canonical_id,
            tenant_name,
            vector_literal(PROVIDER.embed(tenant_name)),
            PROVIDER.model,
        ),
    )
    return product_id


def test_trigram_similarity_catches_a_supplier_typo_a_naive_exact_match_would_miss(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "search-typo")
        product_id = _make_embedded_product(
            cur, workspace, brand="Acme", name="Widget Pro", tenant_name="Acme Widget Pro"
        )
        line_text = "ACME Wdget Pro 500ml"
        assert line_text.casefold() not in "acme widget pro"
        cur.execute(
            "select workspace_product_id, lexical_similarity, semantic_similarity "
            "from match_candidate_search(%s, %s, 0.20, 0.05, 5)",
            (line_text, vector_literal(PROVIDER.embed(line_text))),
        )
        rows = cur.fetchall()
    matched = [row for row in rows if row[0] == product_id]
    assert matched, "expected the typo'd line to surface the real product via pg_trgm similarity"
    assert matched[0][1] > 0.20


def test_unrelated_text_does_not_surface_as_a_candidate(conn: object) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "search-unrelated")
        product_id = _make_embedded_product(
            cur, workspace, brand="Acme", name="Widget Pro", tenant_name="Acme Widget Pro"
        )
        line_text = "Completely different stationery item"
        cur.execute(
            "select workspace_product_id from match_candidate_search(%s, %s, 0.20, 0.05, 5)",
            (line_text, vector_literal(PROVIDER.embed(line_text))),
        )
        rows = cur.fetchall()
    assert product_id not in {row[0] for row in rows}


def test_a_missing_embedding_scores_the_neutral_half_not_zero_or_a_false_match(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        workspace = make_workspace(cur, "search-null-embedding")
        from uuid import uuid4

        canonical_id, product_id = uuid4(), uuid4()
        cur.execute("reset role")
        cur.execute(
            "insert into canonical_product (id,brand,name,base_unit) "
            "values (%s,'Acme','Widget Pro','litre')",
            (canonical_id,),
        )
        act_as(cur, workspace)
        cur.execute(
            "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
            "values (%s,%s,%s,'Acme Widget Pro')",
            (product_id, workspace.tenant_id, canonical_id),
        )
        line_text = "Acme Widget Pro"
        cur.execute(
            "select workspace_product_id, semantic_similarity "
            "from match_candidate_search(%s, %s, 0.20, 0.05, 5)",
            (line_text, vector_literal(PROVIDER.embed(line_text))),
        )
        rows = cur.fetchall()
    matched = [row for row in rows if row[0] == product_id]
    assert matched, "an exact tenant_name match must still surface via trigram with no embedding"
    assert matched[0][1] == pytest.approx(0.5)
