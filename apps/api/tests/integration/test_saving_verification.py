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
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.savings.service import SavingsService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_self_verification_changes_only_status_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("saving-verify") as context:
        add_costed_offer(context, supplier_id=context.supplier_ids[0], amount=Decimal("300.0000"))
        service = SavingsService(settings)
        pending = record_purchase(service, context)

        verified = service.verify_saving(member=context.member, saving_id=pending.id)

        assert verified.status == "verified"
        assert verified.verified_at is not None
        assert verified.verified_by == context.member.membership_id
        assert verified.baseline_policy == pending.baseline_policy
        assert verified.baseline_value == pending.baseline_value
        assert verified.actual_value == pending.actual_value
        assert verified.delta == pending.delta
        assert verified.calculation_inputs == pending.calculation_inputs


def test_verifying_already_verified_saving_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("saving-verify-conflict") as context:
        add_costed_offer(context, supplier_id=context.supplier_ids[0], amount=Decimal("300.0000"))
        service = SavingsService(settings)
        pending = record_purchase(service, context)
        service.verify_saving(member=context.member, saving_id=pending.id)

        with pytest.raises(ConflictError):
            service.verify_saving(member=context.member, saving_id=pending.id)
