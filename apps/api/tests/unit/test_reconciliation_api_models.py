from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from procurepilot_api.modules.accounting.reconciliation_service import _format_discrepancy_row
from procurepilot_api.modules.accounting.schemas import ReconciliationDiscrepancy


def _legacy_row() -> dict[str, object]:
    return {
        "id": uuid4(),
        "discrepancy_type": "amount_mismatch",
        "synced_bill_id": None,
        "purchase_record_id": None,
        "status": "open",
        "detected_at": datetime(2026, 9, 20, tzinfo=UTC),
        "resolved_by": None,
        "resolved_at": None,
        "resolution_note": None,
    }


def test_legacy_discrepancy_row_remains_valid_without_r33_fields() -> None:
    discrepancy = ReconciliationDiscrepancy.model_validate(_legacy_row())

    assert discrepancy.discrepancy_type == "amount_mismatch"
    assert discrepancy.three_way_match is None
    assert discrepancy.evidence is None


def test_r33_discrepancy_validates_and_serializes_decimal_summary_values_as_strings() -> None:
    match_id = uuid4()
    order_id = uuid4()
    evaluated_at = datetime(2026, 9, 20, 10, 30, tzinfo=UTC)
    row = {
        **_legacy_row(),
        "discrepancy_type": "over_billed_quantity",
        "three_way_match_id": match_id,
        "purchase_order_id": order_id,
        "evidence": {"ordered": {"quantity": "10.000000"}, "source_ids": [str(order_id)]},
        "source_hash": "sha256:example",
        "source_updated_at": evaluated_at,
        "reopened_at": None,
        "three_way_match": {
            "result": "needs_review",
            "tolerance_ruleset_version": "r3.3-v1",
            "source_hash": "sha256:example",
            "evaluated_at": evaluated_at,
            "ordered_quantity": Decimal("10.000000"),
            "confirmed_quantity": None,
            "received_quantity": Decimal("8.500000"),
            "invoiced_quantity": Decimal("9.000000"),
            "ordered_unit_price_amount": Decimal("12.3400"),
            "ordered_unit_price_currency": "USD",
            "invoiced_unit_price_amount": None,
            "invoiced_unit_price_currency": None,
            "ordered_total_amount": Decimal("123.4000"),
            "ordered_total_currency": "USD",
            "invoiced_total_amount": None,
            "invoiced_total_currency": None,
        },
        "purchase_order_detail": {
            "order_number": "PO-1001",
            "status": "submitted",
            "order_date": date(2026, 9, 19),
        },
    }

    discrepancy = ReconciliationDiscrepancy.model_validate(row)
    serialized = discrepancy.model_dump(mode="json")

    assert serialized["three_way_match"]["ordered_quantity"] == "10.000000"
    assert serialized["three_way_match"]["ordered_unit_price_amount"] == "12.3400"
    assert serialized["three_way_match"]["ordered_total_amount"] == "123.4000"
    assert serialized["three_way_match"]["confirmed_quantity"] is None


def test_format_preserves_r33_source_evidence() -> None:
    evaluated_at = datetime(2026, 9, 20, 10, 30, tzinfo=UTC)
    evidence = {"ordered_quantity": "4", "receipt": {"source_id": "receipt-1"}}
    row = {
        **_legacy_row(),
        "discrepancy_type": "missing_receipt",
        "three_way_match_id": uuid4(),
        "purchase_order_id": uuid4(),
        "evidence": evidence,
        "source_hash": "hash-1",
        "source_updated_at": evaluated_at,
        "reopened_at": evaluated_at,
        "twm_id": uuid4(),
        "twm_result": "partial",
        "twm_ruleset_version": "r3.3-v1",
        "twm_source_hash": "hash-1",
        "twm_evaluated_at": evaluated_at,
        "twm_ordered_quantity": Decimal("4.000000"),
        "twm_confirmed_quantity": None,
        "twm_received_quantity": None,
        "twm_invoiced_quantity": Decimal("4.000000"),
        "twm_ordered_unit_price_amount": None,
        "twm_ordered_unit_price_currency": None,
        "twm_invoiced_unit_price_amount": None,
        "twm_invoiced_unit_price_currency": None,
        "twm_ordered_total_amount": None,
        "twm_ordered_total_currency": None,
        "twm_invoiced_total_amount": None,
        "twm_invoiced_total_currency": None,
        "po_id": uuid4(),
        "po_order_number": "PO-1002",
        "po_status": "confirmed",
        "po_order_date": date(2026, 9, 18),
    }

    formatted = _format_discrepancy_row(row)

    assert formatted["evidence"] is evidence
    assert formatted["evidence"]["receipt"] == {"source_id": "receipt-1"}
    assert formatted["three_way_match"]["source_hash"] == "hash-1"
