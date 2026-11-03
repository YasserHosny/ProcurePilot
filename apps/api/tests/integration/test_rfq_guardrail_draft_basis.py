"""PPS-192: guardrails must evaluate the requested draft and actual product coverage."""

from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from integration.test_rfq_guardrail_deferred import _baseline_and_guardrail
from integration.test_rfq_service_e2e import (
    _patch_requests_service_for_test,
    _seed_rfq_and_responses,
    _seed_tenant,
)
from procurepilot_api.config import get_settings
from procurepilot_api.modules.ingestion.orchestrator import _evaluate_guardrails_for_rfq
from procurepilot_api.modules.rfq.guardrail_evaluation import (
    GuardrailEvaluationSnapshot,
    compute_guardrail_evaluation,
)

DraftBasisFixture = tuple[UUID, UUID, UUID, list[UUID]]


@pytest.fixture
def draft_basis_fixture(monkeypatch: pytest.MonkeyPatch) -> DraftBasisFixture:
    settings = get_settings()
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            tenant_id, user_id, membership_id = _seed_tenant(cur, email_suffix=uuid4().hex)
            rfq_id, response_id, other_response, _ = _seed_rfq_and_responses(
                cur, tenant_id, membership_id
            )
            guardrail_id, products = _baseline_and_guardrail(
                cur, tenant_id=tenant_id, membership_id=membership_id, rfq_id=rfq_id
            )
            cur.execute(
                "update auto_preparation_guardrail set created_at = now() - interval '1 hour' "
                "where id = %s",
                (guardrail_id,),
            )
            cur.execute(
                "update quotation set status = 'refused' where id = "
                "(select quotation_id from rfq_response where id = %s)",
                (other_response,),
            )
            # Deliberately quote just one pack of each requested product.
            cur.execute(
                "update quotation_line set quantity = 1 where quotation_id = "
                "(select quotation_id from rfq_response where id = %s)",
                (response_id,),
            )
    _patch_requests_service_for_test(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )
    return tenant_id, rfq_id, response_id, products


def _snapshot(tenant_id: UUID, rfq_id: UUID) -> GuardrailEvaluationSnapshot:
    with psycopg.connect(get_settings().database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            snapshot = compute_guardrail_evaluation(cur, tenant_id=tenant_id, rfq_id=rfq_id)
            assert snapshot is not None
            return snapshot


def _run_and_assert_blocked(tenant_id: UUID, rfq_id: UUID) -> None:
    settings = get_settings()
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute("select status from rfq where id = %s", (rfq_id,))
            assert cur.fetchone()[0] == "responded"
            cur.execute("select count(*) from purchase_request where tenant_id = %s", (tenant_id,))
            assert cur.fetchone()[0] == 0
            cur.execute(
                "select count(*) from auto_preparation_event where tenant_id = %s", (tenant_id,)
            )
            assert cur.fetchone()[0] == 0


@pytest.mark.parametrize("duplicate", [False, True])
def test_guardrail_cap_uses_requested_packs(
    draft_basis_fixture: DraftBasisFixture, duplicate: bool
) -> None:
    tenant_id, rfq_id, response_id, products = draft_basis_fixture
    with psycopg.connect(get_settings().database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "update rfq_line set quantity = %s where rfq_id = %s and workspace_product_id = %s",
                (60 if duplicate else 100, rfq_id, products[0]),
            )
            if duplicate:
                cur.execute(
                    "insert into rfq_line (id,tenant_id,rfq_id,workspace_product_id,quantity) "
                    "values (%s,%s,%s,%s,40)",
                    (uuid4(), tenant_id, rfq_id, products[0]),
                )
    snapshot = _snapshot(tenant_id, rfq_id)
    candidate = next(c for c in snapshot.candidates if c.rfq_response_id == response_id)
    assert candidate.total_amount == Decimal("2050")  # 100 * 15.5 + 20 * 25, cap 1000.
    assert next(iter(snapshot.decisions.values())).reason == "exceeds_max_order_value"
    _run_and_assert_blocked(tenant_id, rfq_id)

    # The same requested quantities pass at the inclusive cap and create only a human's draft.
    with psycopg.connect(get_settings().database_url.get_secret_value()) as conn:
        conn.execute(
            "update auto_preparation_guardrail set max_order_value_amount = 2050 "
            "where tenant_id = %s",
            (tenant_id,),
        )
    assert next(iter(_snapshot(tenant_id, rfq_id).decisions.values())).fired
    if duplicate:
        # Evaluation aggregates duplicate RFQ quantities. Request creation separately rejects
        # duplicate products today; changing that preparation contract is outside PPS-192.
        return
    settings = get_settings()
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)
    with psycopg.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            cur.execute("select status from purchase_request where tenant_id = %s", (tenant_id,))
            assert cur.fetchall() == [("draft",)]


@pytest.mark.parametrize("coverage", ["wrong_product", "extra_product", "duplicate_rfq"])
def test_guardrail_completeness_uses_product_identity(
    draft_basis_fixture: DraftBasisFixture, coverage: str
) -> None:
    tenant_id, rfq_id, response_id, products = draft_basis_fixture
    with psycopg.connect(get_settings().database_url.get_secret_value()) as conn:
        with conn.cursor() as cur:
            if coverage == "duplicate_rfq":
                cur.execute(
                    "insert into rfq_line (id,tenant_id,rfq_id,workspace_product_id,quantity) "
                    "values (%s,%s,%s,%s,1)",
                    (uuid4(), tenant_id, rfq_id, products[0]),
                )
            else:
                extra = uuid4()
                canonical_id = uuid4()
                cur.execute(
                    "insert into canonical_product (id,name,base_unit) values (%s,%s,'each')",
                    (canonical_id, f"Extra-{canonical_id}"),
                )
                cur.execute(
                    "insert into workspace_product (id,tenant_id,canonical_product_id,tenant_name) "
                    "values (%s,%s,%s,'Extra')",
                    (extra, tenant_id, canonical_id),
                )
                if coverage == "wrong_product":
                    # RFQ A+B, response A+C: equal counts must not imply completeness.
                    cur.execute(
                        "update match_decision set matched_workspace_product_id = %s "
                        "where quotation_line_id in (select ql.id from quotation_line ql "
                        "join rfq_response r on r.quotation_id = ql.quotation_id "
                        "where r.id = %s and ql.line_number = 2)",
                        (extra, response_id),
                    )
                else:
                    line_id = uuid4()
                    cur.execute(
                        "insert into quotation_line (id,tenant_id,quotation_id,line_number,"
                        "original_text,quantity,unit_price_amount,unit_price_currency) "
                        "select %s,tenant_id,quotation_id,3,'extra',100,9999,'GBP' "
                        "from rfq_response where id = %s",
                        (line_id, response_id),
                    )
                    cur.execute(
                        "insert into match_decision (id,tenant_id,quotation_line_id,"
                        "matched_workspace_product_id,outcome,is_automatic,confidence) "
                        "values (%s,%s,%s,%s,'no_match_new_product',true,1)",
                        (uuid4(), tenant_id, line_id, extra),
                    )
    snapshot = _snapshot(tenant_id, rfq_id)
    candidate = next(c for c in snapshot.candidates if c.rfq_response_id == response_id)
    assert candidate.all_lines_matched is (coverage != "wrong_product")
    if coverage == "wrong_product":
        assert next(iter(snapshot.decisions.values())).reason == "partial_line_response"
        _run_and_assert_blocked(tenant_id, rfq_id)
    elif coverage == "extra_product":
        assert candidate.total_amount == Decimal("655")  # Extra quote products aren't prepared.
