from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from procurepilot_api.modules.savings.schemas import (
    Money,
    PurchaseOutcomeCreate,
    PurchaseOutcomeCreated,
    PurchaseRecord,
    SavingEvidence,
    SavingList,
    SavingRecord,
)


def _purchase() -> PurchaseRecord:
    return PurchaseRecord(
        id=uuid4(),
        workspace_product_id=uuid4(),
        supplier_id=uuid4(),
        quotation_line_id=uuid4(),
        match_decision_id=uuid4(),
        landed_cost_id=uuid4(),
        quantity=Decimal("10.000000"),
        base_unit="each",
        unit_price=Money(amount=Decimal("8.8000"), currency="GBP"),
        total_paid=Money(amount=Decimal("88.0000"), currency="GBP"),
        delivery_result="delivered",
        recorded_by=uuid4(),
        recorded_at=datetime.now(UTC),
    )


def _saving(purchase: PurchaseRecord | None = None) -> SavingRecord:
    purchase = purchase or _purchase()
    return SavingRecord(
        id=uuid4(),
        purchase_record_id=purchase.id,
        workspace_product_id=purchase.workspace_product_id,
        supplier_id=purchase.supplier_id,
        status="pending",
        baseline_policy="last_paid",
        baseline_source_landed_cost_ids=[uuid4()],
        baseline_unit_price=Money(amount=Decimal("10.0000"), currency="GBP"),
        baseline_value=Money(amount=Decimal("100.0000"), currency="GBP"),
        actual_value=purchase.total_paid,
        delta=Money(amount=Decimal("12.0000"), currency="GBP"),
        calculation_version="saving-baseline-v1",
        calculation_inputs={"quantity": "10.000000"},
        recorded_by=purchase.recorded_by,
        recorded_at=purchase.recorded_at,
    )


def test_purchase_outcome_create_rejects_tenant_id_and_requires_money_pairs() -> None:
    payload = {
        "workspace_product_id": str(uuid4()),
        "quantity": "10.000000",
        "base_unit": "each",
        "unit_price": {"amount": "8.8000", "currency": "GBP"},
        "total_paid": {"amount": "88.0000", "currency": "GBP"},
        "delivery_result": "delivered",
        "tenant_id": str(uuid4()),
    }

    with pytest.raises(ValidationError):
        PurchaseOutcomeCreate.model_validate(payload)

    del payload["tenant_id"]
    created = PurchaseOutcomeCreate.model_validate(payload)
    assert created.unit_price.currency == "GBP"
    assert created.total_paid.amount == Decimal("88.0000")


def test_purchase_created_and_saving_list_shapes_have_explicit_money() -> None:
    purchase = _purchase()
    saving = _saving(purchase)
    response = PurchaseOutcomeCreated(purchase_record=purchase, saving_record=saving)
    page = SavingList(items=[saving], next_cursor=None)

    body = response.model_dump(mode="json")
    assert body["purchase_record"]["total_paid"] == {"amount": "88.0000", "currency": "GBP"}
    assert body["saving_record"]["delta"] == {"amount": "12.0000", "currency": "GBP"}
    assert page.next_cursor is None


def test_saving_evidence_shape_contains_calculation_and_links() -> None:
    purchase = _purchase()
    saving = _saving(purchase)
    evidence = SavingEvidence(
        saving_record=saving,
        purchase_record=purchase,
        quotation={
            "quotation_id": str(uuid4()),
            "quotation_line_id": str(purchase.quotation_line_id),
        },
        match_decision={"id": str(purchase.match_decision_id), "confidence": "0.9500"},
        competing_offers=[{"landed_cost_id": str(purchase.landed_cost_id)}],
        calculation={
            "baseline_policy": saving.baseline_policy,
            "baseline_value": saving.baseline_value.model_dump(mode="json"),
            "actual_value": saving.actual_value.model_dump(mode="json"),
            "delta": saving.delta.model_dump(mode="json"),
            "source_landed_cost_ids": [str(saving.baseline_source_landed_cost_ids[0])],
        },
    )

    body = evidence.model_dump(mode="json")
    assert body["calculation"]["actual_value"]["currency"] == "GBP"
    assert body["competing_offers"][0]["landed_cost_id"]
