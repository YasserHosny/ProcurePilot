from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from procurepilot_api.modules.quotations.review_service import _apply_correction_to_canonical_row


@pytest.mark.parametrize(
    ("name", "value", "payload"),
    [
        ("pack_count", 2, {"pack_count": 2}),
        ("unit_size", "5", {"unit_size": "5"}),
        ("pack_unit", "gram", {"pack_unit": "gram"}),
        ("description", "Tea", {"original_text": "Tea"}),
        ("original_text", "Tea", {"original_text": "Tea"}),
        ("vat_rate", "0.2", {"vat_rate": "0.2"}),
        (
            "delivery_fee",
            {"amount": "3", "currency": "GBP"},
            {"delivery_fee_amount": "3", "delivery_fee_currency": "GBP"},
        ),
        (
            "discount",
            {"amount": "1", "currency": "USD"},
            {"discount_amount": "1", "discount_currency": "USD"},
        ),
    ],
)
def test_line_correction_mapping(name: str, value: object, payload: dict[str, object]) -> None:
    client = MagicMock()
    line_id = str(uuid4())
    _apply_correction_to_canonical_row(
        client, {"entity_type": "quotation_line", "entity_id": line_id, "field_name": name}, value
    )
    client.table.assert_called_once_with("quotation_line")
    client.table().update.assert_called_once_with(payload)
    client.table().update().eq.assert_called_once_with("id", line_id)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("stated_total", {"amount": "12,5", "currency": "GBP"}),
        ("stated_total", {"amount": "12.5"}),
        ("stated_total", {"amount": "12.5", "currency": "ZZZ"}),
        ("currency", "ZZZ"),
        ("currency", None),
    ],
)
def test_invalid_header_correction_prevents_all_writes(
    monkeypatch: pytest.MonkeyPatch, name: str, value: object
) -> None:
    from procurepilot_api.errors import ConflictError
    from procurepilot_api.modules.quotations import review_service
    from procurepilot_api.modules.quotations.schemas import FieldCorrection, QuotationReviewPatch

    client = MagicMock()
    quotation = client.table.return_value
    quotation.select.return_value = quotation
    quotation.eq.return_value = quotation
    quotation.limit.return_value = quotation
    field_id = uuid4()
    quotation.execute.side_effect = [
        MagicMock(data=[{"id": str(uuid4()), "status": "extracted"}]),
        MagicMock(data=[]),
        MagicMock(
            data=[
                {
                    "id": str(field_id),
                    "entity_type": "quotation",
                    "field_name": name,
                    "corrected_by": None,
                }
            ]
        ),
        MagicMock(data=[]),  # Unsupported currency lookup.
    ]
    monkeypatch.setattr(review_service, "authenticated_client", lambda *_: client)
    with pytest.raises(ConflictError) as error:
        review_service.QuotationReviewService().apply_review_patch(
            bearer_token="test",
            member=MagicMock(),
            quotation_id=uuid4(),
            patch=QuotationReviewPatch(
                reviewer_notes="must not persist",
                corrections=[FieldCorrection(field_extraction_id=field_id, corrected_value=value)],
            ),
        )
    assert error.value.details == {"reason": f"invalid_{name}_correction"}
    quotation.update.assert_not_called()
    quotation.insert.assert_not_called()
    quotation.delete.assert_not_called()
