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
from procurepilot_api.modules.matching import resolution_service as resolution_module
from procurepilot_api.modules.matching import service as matching_module
from procurepilot_api.modules.matching.resolution_service import MatchResolutionService
from procurepilot_api.modules.matching.schemas import MatchResolutionRequest
from procurepilot_api.modules.matching.service import MatchingService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a Postgres with chunk 4.4 matching migrations",
)


class _NoopLandedCost:
    def compute_for_line_with_client(self, **_kwargs: object) -> None:
        return None

    def get_landed_cost_or_none(self, **_kwargs: object) -> None:
        return None


class _MatchingSettings:
    matching_embedding_model = "stub-hash-v1"
    matching_trigram_threshold = 0.30
    matching_auto_accept_threshold = 0.92
    matching_review_margin = 0.05


@pytest.fixture
def conn() -> object:
    yield from connection()


def test_human_resolution_learns_exact_alias_and_next_identical_wording_auto_matches(
    conn: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        ensure_quotation_reference_data(cur)
        workspace = make_workspace(cur, "alias-learning")
        supplier_id = make_supplier(cur, workspace, name="Alias Learning Supplier")
        product_id = make_workspace_product(cur, workspace, name="Alias Learned Product")
        first_line_id = _reviewed_line(
            cur,
            workspace,
            supplier_id,
            original_text="Supplier exact milk wording 2 litre",
            line_number=1,
        )
        candidate_id = _candidate(cur, workspace, first_line_id, product_id)
        member = _member(workspace)
        db_client = PsycopgSupabaseClient(conn)
        monkeypatch.setattr(
            resolution_module,
            "authenticated_client",
            lambda _settings, _bearer_token: db_client,
        )
        resolution = MatchResolutionService(cast(Settings, _MatchingSettings()))
        resolution._landed_cost = _NoopLandedCost()  # noqa: SLF001

        act_as(cur, workspace)
        decision = resolution.resolve(
            bearer_token="test-token",
            member=member,
            line_id=first_line_id,
            payload=MatchResolutionRequest(
                outcome="same_product", selected_match_candidate_id=candidate_id
            ),
        )

        alias = _alias_for_text(cur, "Supplier exact milk wording 2 litre")
        assert alias["workspace_product_id"] == product_id
        assert alias["alias_text"] == "Supplier exact milk wording 2 litre"
        assert decision.alias_id == alias["id"]

        second_line_id = _reviewed_line(
            cur,
            workspace,
            supplier_id,
            original_text="Supplier exact milk wording 2 litre",
            line_number=2,
        )
        monkeypatch.setattr(
            matching_module,
            "authenticated_client",
            lambda _settings, _bearer_token: db_client,
        )
        matching = MatchingService(cast(Settings, _MatchingSettings()))
        matching._landed_cost = _NoopLandedCost()  # noqa: SLF001
        monkeypatch.setattr(matching, "_backfill_missing_embeddings", lambda _client: None)

        act_as(cur, workspace)
        state = matching.quotation_matches(
            bearer_token="test-token",
            member=member,
            quotation_id=_quotation_id_for_line(cur, second_line_id),
        )

        assert len(state.lines) == 1
        assert state.lines[0].decision is not None
        assert state.lines[0].decision.is_automatic is True
        assert state.lines[0].task is None
        assert len(state.lines[0].candidates) == 1
        assert state.lines[0].candidates[0].reasons.alias_hit is True
        assert _count(cur, "match_task", second_line_id) == 0
        assert _count(cur, "match_decision", second_line_id) == 1


def _member(workspace: object) -> CurrentMember:
    return CurrentMember(
        membership_id=workspace.membership_id,
        tenant_id=workspace.tenant_id,
        user_id=workspace.user_id,
        email=f"{workspace.label}@example.test",
        role=MemberRole.owner,
    )


def _reviewed_line(
    cur: psycopg.Cursor,
    workspace: object,
    supplier_id: UUID,
    *,
    original_text: str,
    line_number: int,
) -> UUID:
    quotation_id = make_quotation(
        cur,
        workspace,
        document_id=make_document(cur, workspace, filename=f"alias-{line_number}.pdf"),
        supplier_id=supplier_id,
        status="reviewed",
        arithmetic_status="reconciled",
    )
    line_id = make_line(cur, workspace, quotation_id)
    act_as(cur, workspace)
    cur.execute(
        """
        update quotation_line
        set original_text = %s, line_number = %s
        where id = %s
        """,
        (original_text, line_number, line_id),
    )
    return line_id


def _candidate(
    cur: psycopg.Cursor,
    workspace: object,
    line_id: UUID,
    product_id: UUID,
) -> UUID:
    candidate_id = uuid4()
    act_as(cur, workspace)
    cur.execute(
        """
        insert into match_candidate (
          id, tenant_id, quotation_line_id, candidate_workspace_product_id,
          confidence, reasons, rank, scoring_version, embedding_model
        ) values (%s, %s, %s, %s, %s, %s, 1, 'matching-score-v2', 'stub-hash-v1')
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


def _alias_for_text(cur: psycopg.Cursor, alias_text: str) -> dict[str, object]:
    cur.execute("select * from product_alias where alias_text = %s", (alias_text,))
    row = cur.fetchone()
    assert row is not None
    columns = [column.name for column in cur.description or []]
    return dict(zip(columns, row, strict=True))


def _quotation_id_for_line(cur: psycopg.Cursor, line_id: UUID) -> UUID:
    cur.execute("select quotation_id from quotation_line where id = %s", (line_id,))
    row = cur.fetchone()
    assert row is not None
    return UUID(str(row[0]))


def _count(cur: psycopg.Cursor, table: str, line_id: UUID) -> int:
    cur.execute(
        f"select count(*) from {table} where quotation_line_id = %s",  # noqa: S608
        (line_id,),
    )
    row = cur.fetchone()
    assert row is not None
    return int(row[0])
