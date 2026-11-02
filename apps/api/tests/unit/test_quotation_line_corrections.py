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
