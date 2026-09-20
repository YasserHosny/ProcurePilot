from __future__ import annotations

from procurepilot_api.modules.quotations.service import _enrich_audit_target


def test_enrich_audit_target_adds_line_and_product_labels() -> None:
    enriched = _enrich_audit_target(
        {
            "quotation_line_id": "line-1",
            "matched_product_id": "product-1",
            "score": "0.9650",
            "outcome": "same_product",
        },
        lines_by_id={
            "line-1": {
                "id": "line-1",
                "line_number": 1,
                "original_text": "A4 Copy Paper 80gsm (5-ream box)",
            }
        },
        products_by_id={"product-1": "Office Plus / A4 Copy Paper 80gsm / White"},
    )

    assert enriched is not None
    assert enriched["line_number"] == 1
    assert enriched["line_text"] == "A4 Copy Paper 80gsm (5-ream box)"
    assert enriched["matched_product_name"] == "Office Plus / A4 Copy Paper 80gsm / White"
    assert enriched["score"] == "0.9650"


def test_enrich_audit_target_returns_none_for_missing_target() -> None:
    assert _enrich_audit_target(None, lines_by_id={}, products_by_id={}) is None
