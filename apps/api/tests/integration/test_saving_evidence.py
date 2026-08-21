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
