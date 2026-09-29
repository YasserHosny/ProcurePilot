from __future__ import annotations

import json
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest

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
from procurepilot_api.modules.matching import service as matching_module
from procurepilot_api.modules.matching.scoring import SCORING_VERSION, STUB_EMBEDDING_MODEL
from procurepilot_api.modules.matching.service import MatchingService
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with chunk 4.4 matching migrations",
)


class _PipelineSettings:
    matching_embedding_model = STUB_EMBEDDING_MODEL
    matching_trigram_threshold = 0.30
    matching_auto_accept_threshold = 0.99
    matching_review_margin = 0.0


class _PsycopgAuditWriter:
    def __init__(self, conn: object) -> None:
        self._conn = conn

    def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
        del bearer_token
        with self._conn.cursor() as cur:
            cur.execute(
                "select record_audit_event(%s, %s, %s::uuid, %s::uuid, %s, %s::jsonb, %s)",
                (
                    event.action,
                    event.outcome,
                    event.tenant_id,
                    event.actor_membership_id,
                    event.actor_email,
                    json.dumps(event.target),
                    event.trace_id,
                ),
            )


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_reviewed_typo_line_persists_ranked_similarity_candidates_and_routes_to_review(
    conn: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        workspace = make_workspace(cur, "matching-pipeline")
        supplier_id = make_supplier(cur, workspace, name="Pipeline Supplier")
        quotation_id = make_quotation(
            cur,
            workspace,
            document_id=make_document(cur, workspace, filename="pipeline.pdf"),
            supplier_id=supplier_id,
            status="reviewed",
            arithmetic_status="reconciled",
        )
        line_id = make_line(cur, workspace, quotation_id)
        intended_id = make_workspace_product(cur, workspace, name="Acme Organic Tomato Passata")
        plausible_id = make_workspace_product(cur, workspace, name="Acme Tomato Puree")
        distractor_id = make_workspace_product(cur, workspace, name="Office Printer Paper")
        cur.execute(
            "update quotation_line set original_text = %s, pack_unit = 'litre' where id = %s",
            ("Acme Oragnic Tomato Passatta", line_id),
        )

        db_client = PsycopgSupabaseClient(conn)
        monkeypatch.setattr(
            matching_module,
            "authenticated_client",
            lambda _settings, _token: db_client,
        )
        monkeypatch.setattr(matching_module, "get_audit_writer", lambda: _PsycopgAuditWriter(conn))
        service = MatchingService(cast(Settings, _PipelineSettings()))
        monkeypatch.setattr(
            service,
            "_service_role_client",
            lambda: PsycopgSupabaseClient(conn, service_role=True),
        )
        member = CurrentMember(
            membership_id=workspace.membership_id,
            tenant_id=workspace.tenant_id,
            user_id=workspace.user_id,
            email=f"{workspace.label}@example.test",
            role=MemberRole.owner,
        )

        act_as(cur, workspace)
        service.quotation_matches(
            bearer_token="test-token",
            member=member,
            quotation_id=quotation_id,
        )

        cur.execute(
            "select tenant_name_embedding_model from workspace_product "
            "where tenant_id = %s and id in (%s, %s, %s) order by id",
            (workspace.tenant_id, intended_id, plausible_id, distractor_id),
        )
        assert [row[0] for row in cur.fetchall()] == [STUB_EMBEDDING_MODEL] * 3

        cur.execute(
            "select wp.id, cp.canonical_embedding_model "
            "from workspace_product wp "
            "join canonical_product cp on cp.id = wp.canonical_product_id "
            "where wp.id in (%s, %s, %s)",
            (intended_id, plausible_id, distractor_id),
        )
        assert {row[0]: row[1] for row in cur.fetchall()} == {
            intended_id: STUB_EMBEDDING_MODEL,
            plausible_id: STUB_EMBEDDING_MODEL,
            distractor_id: STUB_EMBEDDING_MODEL,
        }

        cur.execute(
            "select target from audit_event "
            "where tenant_id = %s and action = 'matching.task_routed'",
            (workspace.tenant_id,),
        )
        audit_rows = cur.fetchall()
        assert len(audit_rows) == 1
        assert audit_rows[0][0]["quotation_line_id"] == str(line_id)

        cur.execute(
            "select candidate_workspace_product_id, confidence, reasons, rank, "
            "scoring_version, embedding_model from match_candidate "
            "where quotation_line_id = %s order by rank",
            (line_id,),
        )
        candidates = cur.fetchall()
        assert candidates
        assert candidates[0][0] == intended_id
        assert [row[3] for row in candidates] == list(range(1, len(candidates) + 1))
        assert all(
            Decimal(str(current[1])) >= Decimal(str(next_row[1]))
            for current, next_row in zip(candidates, candidates[1:], strict=False)
        )
        candidate_ids = {row[0] for row in candidates}
        assert (
            distractor_id not in candidate_ids
            or next(row[3] for row in candidates if row[0] == distractor_id) > 1
        )
        assert plausible_id in candidate_ids

        reasons = candidates[0][2]
        assert set(reasons) == {
            "alias_hit",
            "gtin_match",
            "supplier_code_match",
            "lexical_similarity",
            "semantic_similarity",
            "feature_score",
        }
        assert reasons["alias_hit"] is False
        assert reasons["gtin_match"] is False
        assert reasons["supplier_code_match"] is False
        assert Decimal(reasons["lexical_similarity"]) > Decimal("0.30")
        assert set(reasons["feature_score"]) == {
            "brand_match",
            "variant_match",
            "pack_unit_match",
            "pack_size_plausibility",
            "price_plausibility",
        }
        assert all(row[4] == SCORING_VERSION for row in candidates)
        assert all(row[5] == STUB_EMBEDDING_MODEL for row in candidates)

        cur.execute(
            "select status, reason from match_task where quotation_line_id = %s",
            (line_id,),
        )
        assert cur.fetchall() == [("open", "low_confidence")]
        cur.execute("select count(*) from match_decision where quotation_line_id = %s", (line_id,))
        assert cur.fetchone()[0] == 0

        counts_before = _pipeline_counts(cur, line_id)
        service.quotation_matches(
            bearer_token="test-token",
            member=member,
            quotation_id=quotation_id,
        )
        assert _pipeline_counts(cur, line_id) == counts_before
        cur.execute(
            "select count(*) from audit_event "
            "where tenant_id = %s and action = 'matching.task_routed'",
            (workspace.tenant_id,),
        )
        assert cur.fetchone()[0] == 1


def _pipeline_counts(cur: psycopg.Cursor, line_id: UUID) -> tuple[int, int]:
    cur.execute(
        "select (select count(*) from match_candidate where quotation_line_id = %s), "
        "(select count(*) from match_task where quotation_line_id = %s)",
        (line_id, line_id),
    )
    return tuple(cur.fetchone())
