from __future__ import annotations

from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from psycopg.types.json import Jsonb

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    act_as,
    connection,
    make_workspace,
    make_workspace_product,
    psycopg,
)
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    ensure_quotation_reference_data,
    make_document,
    make_line,
    make_quotation,
    make_supplier,
)
from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.matching.service import MatchingService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with chunk 4.4 matching migrations",
)


class _NoopLandedCost:
    def compute_for_line_with_client(self, **_kwargs: object) -> None:
        return None


class _RoutingSettings:
    matching_embedding_model = "stub-hash-v1"
    matching_trigram_threshold = 0.30
    matching_auto_accept_threshold = 0.92
    matching_review_margin = 0.05


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_top_candidate_at_threshold_without_close_competitor_auto_accepts(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        workspace, line_id = _reviewed_line(cur, "routing-auto")
        product_id = make_workspace_product(cur, workspace, name="Routing accepted product")
        candidate = _candidate(cur, workspace, line_id, product_id, confidence=Decimal("0.9200"))
        service = _service()

        act_as(cur, workspace)
        service._route_or_accept(  # noqa: SLF001
            PsycopgSupabaseClient(conn), _member(workspace), _line(cur, line_id), [candidate]
        )

        assert _count(cur, "match_decision", line_id) == 1
        assert _count(cur, "match_task", line_id) == 0


def test_close_competitor_routes_to_review_even_above_auto_accept_threshold(
    conn: object,
) -> None:
    with conn.cursor() as cur:
        workspace, line_id = _reviewed_line(cur, "routing-close")
        top_product_id = make_workspace_product(cur, workspace, name="Routing top product")
        second_product_id = make_workspace_product(cur, workspace, name="Routing close product")
        candidates = [
            _candidate(
                cur, workspace, line_id, top_product_id, confidence=Decimal("0.9400"), rank=1
            ),
            _candidate(
                cur,
                workspace,
                line_id,
                second_product_id,
                confidence=Decimal("0.9100"),
                rank=2,
            ),
        ]
        service = _service()

        act_as(cur, workspace)
        service._route_or_accept(  # noqa: SLF001
            PsycopgSupabaseClient(conn), _member(workspace), _line(cur, line_id), candidates
        )

        assert _count(cur, "match_decision", line_id) == 0
        assert _task_reason(cur, line_id) == "close_candidates"


def test_no_candidates_routes_to_no_candidate_task(conn: object) -> None:
    with conn.cursor() as cur:
        workspace, line_id = _reviewed_line(cur, "routing-none")
        service = _service()

        act_as(cur, workspace)
        service._route_or_accept(  # noqa: SLF001
            PsycopgSupabaseClient(conn), _member(workspace), _line(cur, line_id), []
        )

        assert _count(cur, "match_decision", line_id) == 0
        assert _task_reason(cur, line_id) == "no_candidate"


def _service() -> MatchingService:
    service = MatchingService(cast(Settings, _RoutingSettings()))
    service._landed_cost = _NoopLandedCost()  # noqa: SLF001
    return service


def _reviewed_line(cur: psycopg.Cursor, label: str) -> tuple[object, UUID]:
    ensure_quotation_reference_data(cur)
    workspace = make_workspace(cur, label)
    supplier_id = make_supplier(cur, workspace, name=f"{label} supplier")
    quotation_id = make_quotation(
        cur,
        workspace,
        document_id=make_document(cur, workspace, filename=f"{label}.pdf"),
        supplier_id=supplier_id,
        status="reviewed",
        arithmetic_status="reconciled",
    )
    line_id = make_line(cur, workspace, quotation_id)
    return workspace, line_id


def _member(workspace: object) -> CurrentMember:
    return CurrentMember(
        membership_id=workspace.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        email=f"{workspace.label}@example.test",
        role=MemberRole.owner,
    )


def _line(cur: psycopg.Cursor, line_id: UUID) -> dict[str, object]:
    cur.execute("select * from quotation_line where id = %s", (line_id,))
    row = cur.fetchone()
    assert row is not None
    columns = [column.name for column in cur.description or []]
    return dict(zip(columns, row, strict=True))


def _candidate(
    cur: psycopg.Cursor,
    workspace: object,
    line_id: UUID,
    product_id: UUID,
    *,
    confidence: Decimal,
    rank: int = 1,
) -> dict[str, object]:
    candidate_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        """
        insert into match_candidate (
          id, tenant_id, quotation_line_id, candidate_workspace_product_id,
          confidence, reasons, rank, scoring_version, embedding_model
        ) values (%s, %s, %s, %s, %s, %s, %s, 'matching-score-v2', 'stub-hash-v1')
        returning *
        """,
        (
            candidate_id,
            workspace.tenant_id,
            line_id,
            product_id,
            confidence,
            Jsonb(
                {
                    "alias_hit": False,
                    "gtin_match": False,
                    "supplier_code_match": False,
                    "lexical_similarity": "1.0000",
                    "semantic_similarity": "0.0000",
                    "feature_score": {
                        "brand_match": "0.5000",
                        "variant_match": "0.5000",
                        "pack_unit_match": "0.5000",
                        "pack_size_plausibility": "0.5000",
                        "price_plausibility": "0.5000",
                    },
                }
            ),
            rank,
        ),
    )
    row = cur.fetchone()
    assert row is not None
    columns = [column.name for column in cur.description or []]
    return dict(zip(columns, row, strict=True))


def _count(cur: psycopg.Cursor, table: str, line_id: UUID) -> int:
    cur.execute(
        f"select count(*) from {table} where quotation_line_id = %s",  # noqa: S608
        (line_id,),
    )
    row = cur.fetchone()
    assert row is not None
    return int(row[0])


def _task_reason(cur: psycopg.Cursor, line_id: UUID) -> str:
    cur.execute("select reason from match_task where quotation_line_id = %s", (line_id,))
    row = cur.fetchone()
    assert row is not None
    return str(row[0])
