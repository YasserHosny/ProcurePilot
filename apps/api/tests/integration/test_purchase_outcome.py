from __future__ import annotations

from decimal import Decimal

import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL
from integration.smart_compare_helpers import (
    add_costed_offer,
    committed_smart_context,
    settings_for_test_db,
)
from integration.value_proof_helpers import fetch_savings, purchase_payload
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.savings.service import SavingsService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_record_purchase_creates_purchase_and_pending_saving_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("purchase-outcome") as context:
        add_costed_offer(context, supplier_id=context.supplier_ids[0], amount=Decimal("300.0000"))

        created = SavingsService(settings).record_purchase(
            member=context.member,
            payload=purchase_payload(context, actual="8.0000"),
        )

        assert created.purchase_record.total_paid.currency == "GBP"
        assert created.saving_record.status == "pending"
        assert created.saving_record.actual_value.amount == Decimal("8.0000")
        assert created.saving_record.delta is not None
        persisted = fetch_savings(context.workspace.tenant_id)
        assert len(persisted) == 1
        assert persisted[0]["purchase_record_id"] == created.purchase_record.id


def test_record_purchase_supports_zero_and_negative_deltas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("purchase-negative") as context:
        add_costed_offer(context, supplier_id=context.supplier_ids[0], amount=Decimal("300.0000"))
        # add_costed_offer's normalised unit price is 300/30 = 10.0000 per base unit;
        # purchase_payload always buys quantity=10, so baseline_value = 10.0000 * 10 = 100.0000.
        zero = SavingsService(settings).record_purchase(
            member=context.member,
            payload=purchase_payload(context, actual="100.0000"),
        ).saving_record
        negative = SavingsService(settings).record_purchase(
            member=context.member,
            payload=purchase_payload(context, actual="102.0000"),
        ).saving_record

        assert zero.delta is not None and zero.delta.amount == Decimal("0.0000")
        assert negative.delta is not None and negative.delta.amount == Decimal("-2.0000")


def test_cross_tenant_product_reference_returns_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("purchase-alpha") as alpha:
        with committed_smart_context("purchase-beta") as beta:
            add_costed_offer(beta, supplier_id=beta.supplier_ids[0], amount=Decimal("300.0000"))
            payload = purchase_payload(beta, actual="8.0000").model_copy(
                update={"workspace_product_id": alpha.product_id}
            )

            with pytest.raises(NotFoundError):
                SavingsService(settings).record_purchase(member=beta.member, payload=payload)
