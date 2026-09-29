from __future__ import annotations

import json
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
from procurepilot_api.modules.matching import resolution_service as resolution_module
from procurepilot_api.modules.matching.resolution_service import MatchResolutionService
from procurepilot_api.modules.matching.schemas import MatchResolutionRequest
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


class _Settings:
    matching_embedding_model = "stub-hash-v1"


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


def test_persisted_landed_cost_raw_inputs_contain_complete_audit_snapshot(
    conn: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        workspace = make_workspace(cur, "landed-cost-audit")
        supplier_id = make_supplier(cur, workspace)
        quotation_id = make_quotation(
            cur,
            workspace,
            document_id=make_document(cur, workspace),
            supplier_id=supplier_id,
            status="reviewed",
            arithmetic_status="reconciled",
        )
        line_id = make_line(cur, workspace, quotation_id)
        product_id = make_workspace_product(cur, workspace, name="Audit Product")
        candidate_id = _candidate(cur, workspace, line_id, product_id)
        act_as(cur, workspace)
        cur.execute("update quotation_line set vat_rate = 0.2000 where id = %s", (line_id,))
        client = PsycopgSupabaseClient(conn)
        monkeypatch.setattr(resolution_module, "authenticated_client", lambda *_args: client)
        monkeypatch.setattr(
            resolution_module, "get_audit_writer", lambda: _PsycopgAuditWriter(conn)
        )
        monkeypatch.setattr(
            resolution_module, "enqueue_guardrail_evaluation", lambda *_args, **_kwargs: None
        )
        MatchResolutionService(cast(Settings, _Settings())).resolve(
            bearer_token="test-token",
            member=_member(workspace),
            line_id=line_id,
            payload=MatchResolutionRequest(
                outcome="same_product", selected_match_candidate_id=candidate_id
            ),
        )

        cur.execute("select raw_inputs from landed_cost where quotation_line_id = %s", (line_id,))
        row = cur.fetchone()
        assert row is not None
        raw_inputs = row[0]
        assert set(raw_inputs) == {
            "quantity",
            "normalised_base_quantity",
            "base_unit",
            "unit_price",
            "vat_rate",
            "vat_amount",
            "delivery_fee",
            "discount",
            "other_charges",
        }
        assert raw_inputs["other_charges"] == {"amount": "0.0000", "currency": "GBP"}


def _member(workspace: object) -> CurrentMember:
    return CurrentMember(
        membership_id=workspace.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        email=f"{workspace.label}@example.test",
        role=MemberRole.owner,
    )


def _candidate(cur: psycopg.Cursor, workspace: object, line_id: UUID, product_id: UUID) -> UUID:
    candidate_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        """
        insert into match_candidate (
          id, tenant_id, quotation_line_id, candidate_workspace_product_id,
          confidence, reasons, rank, scoring_version, embedding_model
        ) values (%s,%s,%s,%s,%s,%s,1,'matching-score-v2','stub-hash-v1')
        """,
        (
            candidate_id,
            workspace.tenant_id,
            line_id,
            product_id,
            Decimal("0.7000"),
            Jsonb(
                {
                    "alias_hit": False,
                    "gtin_match": False,
                    "supplier_code_match": False,
                    "lexical_similarity": "0.7000",
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
        ),
    )
    return candidate_id
