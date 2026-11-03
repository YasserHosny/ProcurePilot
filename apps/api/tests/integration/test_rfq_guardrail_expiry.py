"""Derived expiry must gate automatic preparation of otherwise qualifying replies."""

from datetime import date, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from integration.test_rfq_guardrail_explanations import (
    _member,
    _reasons,
    _seed_explanation_fixture,
)
from integration.test_rfq_service_e2e import _patch_requests_service_for_test
from procurepilot_api.config import get_settings
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.ingestion.orchestrator import _evaluate_guardrails_for_rfq
from procurepilot_api.modules.rfq.guardrail_evaluation import compute_guardrail_evaluation
from procurepilot_api.modules.rfq.service import RfqService


@pytest.mark.parametrize("days", [-1, 1], ids=["expired-sent", "open-sent"])
def test_stored_sent_guardrail_uses_effective_expiry(
    monkeypatch: pytest.MonkeyPatch, days: int
) -> None:
    (
        tenant_id,
        user_id,
        membership_id,
        rfq_id,
        response_a,
        _response_b,
        guardrail_id,
        _product_id,
    ) = _seed_explanation_fixture()
    settings = get_settings()
    test_db = settings.database_url.get_secret_value()
    owner = _member(tenant_id, user_id, membership_id, MemberRole.owner)
    service = RfqService(settings)
    _patch_requests_service_for_test(
        monkeypatch, tenant_id=tenant_id, user_id=user_id, membership_id=membership_id
    )

    # The replies are fully reviewed/matched and otherwise qualify for this enabled guardrail.
    # Retain the stored sent state, as happens when a reply arrives after the deadline.
    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        conn.execute(
            "update rfq set status = 'sent', needed_by_date = %s "
            "where id = %s and tenant_id = %s",
            (date.today() + timedelta(days=days), rfq_id, tenant_id),
        )

    # Exercise the worker before checking the owner's read-only evaluation explanation.
    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        _evaluate_guardrails_for_rfq(settings, conn, tenant_id=tenant_id, rfq_id=rfq_id)

    expected_reason = "rfq_not_open" if days < 0 else "fired"
    assert _reasons(service, owner, rfq_id)[response_a] == expected_reason
    with psycopg.connect(test_db, prepare_threshold=None) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select count(*) as count from purchase_request where tenant_id = %s",
                (tenant_id,),
            )
            assert cur.fetchone()["count"] == (0 if days < 0 else 1)
            cur.execute(
                "select purchase_request_id from auto_preparation_event "
                "where tenant_id = %s and guardrail_id = %s and rfq_response_id = %s",
                (tenant_id, guardrail_id, response_a),
            )
            event = cur.fetchone()
            if days < 0:
                assert event is None
                snapshot = compute_guardrail_evaluation(cur, tenant_id=tenant_id, rfq_id=rfq_id)
                assert snapshot is not None
                assert snapshot.rfq_status == "expired"
                assert not snapshot.decisions[guardrail_id].fired
                cur.execute("select status from rfq where id = %s", (rfq_id,))
                assert cur.fetchone()["status"] == "sent"
            else:
                assert event is not None
                assert event["purchase_request_id"] is not None
