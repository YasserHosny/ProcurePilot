from __future__ import annotations

from decimal import Decimal

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from integration.value_proof_helpers import record_purchase
from procurepilot_api.modules.savings.evidence import EvidenceService
from procurepilot_api.modules.savings.schemas import Money, PurchaseOutcomeCreate
from procurepilot_api.modules.savings.service import SavingsService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_saving_evidence_includes_purchase_competing_offers_and_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("saving-evidence") as context:
        add_costed_offer(context, supplier_id=context.supplier_ids[0], amount=Decimal("300.0000"))
        add_costed_offer(context, supplier_id=context.supplier_ids[1], amount=Decimal("330.0000"))
        saving = record_purchase(SavingsService(settings), context)

        evidence = EvidenceService(settings).get_evidence(
            member=context.member,
            saving_id=saving.id,
        )

        assert evidence.purchase_record.id == saving.purchase_record_id
        assert evidence.calculation["baseline_policy"] == "last_paid"
        assert evidence.calculation["actual_value"]["currency"] == "GBP"
        assert len(evidence.competing_offers) >= 2


def test_saving_evidence_with_a_real_match_decision_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A purchase recorded from Smart Compare (the real product path) always carries
    quotation_line_id/match_decision_id/landed_cost_id — evidence.py's match_decision query
    referenced a column ("reasons") that match_decision does not have, so this exact, ordinary
    path 503'd every time. The other test in this file never sets these fields, so it never
    exercised the buggy query."""
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("saving-evidence-linked") as context:
        offer = add_costed_offer(
            context, supplier_id=context.supplier_ids[0], amount=Decimal("300.0000")
        )
        service = SavingsService(settings)
        created = service.record_purchase(
            member=context.member,
            payload=PurchaseOutcomeCreate(
                workspace_product_id=context.product_id,
                supplier_id=context.supplier_ids[0],
                quotation_line_id=offer.line_id,
                match_decision_id=offer.match_decision_id,
                landed_cost_id=offer.landed_cost_id,
                quantity=Decimal("10.000000"),
                base_unit="litre",
                unit_price=Money(amount=Decimal("30.0000"), currency="GBP"),
                total_paid=Money(amount=Decimal("300.0000"), currency="GBP"),
                delivery_result="delivered",
            ),
        )

        evidence = EvidenceService(settings).get_evidence(
            member=context.member,
            saving_id=created.saving_record.id,
        )

        assert evidence.match_decision is not None
        assert evidence.match_decision["id"] == offer.match_decision_id
        assert evidence.quotation is not None
        assert evidence.quotation["quotation_line_id"] == offer.line_id
