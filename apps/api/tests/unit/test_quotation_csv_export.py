from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from uuid import uuid4

import pytest

from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.quotations import service as service_module
from procurepilot_api.modules.quotations.schemas import decimal_string
from procurepilot_api.modules.quotations.service import QuotationService


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_csv_text_prefixes_special_initial_characters(prefix: str) -> None:
    assert service_module._csv_text(prefix + "text") == "'" + prefix + "text"


@pytest.mark.parametrize("value", ["Supplier Ltd", "", "item@text"])
def test_csv_text_preserves_other_text(value: str) -> None:
    assert service_module._csv_text(value) == value


def test_decimal_string_preserves_negative_number() -> None:
    assert decimal_string(Decimal("-5")) == "-5"


@pytest.mark.parametrize("special_text", [False, True])
def test_csv_export_includes_review_and_currency_data(
    monkeypatch: pytest.MonkeyPatch, special_text: bool
) -> None:
    quote = {
        "supplier_id": uuid4(),
        "issue_date": "2026-11-02",
        "status": "extracted",
        "stated_total_amount": Decimal("-5"),
        "stated_total_currency": "GBP",
        "currency": "GBP",
    }
    line = {
        "line_number": 1,
        "original_text": "@cmd",
        "quantity": Decimal("2"),
        "unit_price_amount": Decimal("-5"),
        "unit_price_currency": "GBP",
        "vat_rate": Decimal("0.2"),
        "delivery_fee_amount": Decimal("-5"),
        "delivery_fee_currency": "USD",
        "discount_amount": Decimal("-5"),
        "discount_currency": "GBP",
    }
    if special_text:
        quote.update(issue_date="\tdate", status="\rstatus", stated_total_currency="+GBP")
        line.update(
            unit_price_currency="-GBP", delivery_fee_currency="=USD", discount_currency="@GBP"
        )

    class Query:
        def __init__(self, rows: list[dict[str, object]]) -> None:
            self.rows = rows

        def select(self, columns: str) -> Query:
            return self

        def eq(self, column: str, value: str) -> Query:
            return self

        def limit(self, count: int) -> Query:
            return self

        def order(self, column: str) -> Query:
            return self

        def execute(self) -> SimpleNamespace:
            return SimpleNamespace(data=self.rows)

    class Client:
        def table(self, name: str) -> Query:
            return Query(
                {"quotation": [quote], "quotation_line": [line], "supplier": [{"name": "=2+2"}]}[
                    name
                ]
            )

    monkeypatch.setattr(service_module, "authenticated_client", lambda *_args: Client())
    monkeypatch.setattr(QuotationService, "_record", lambda *_args, **_kwargs: None)
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="buyer@example.test",
        role=MemberRole.buyer,
    )
    rows = list(
        csv.reader(
            StringIO(
                QuotationService().export_quotation_csv(
                    bearer_token="test-token",
                    member=member,
                    quotation_id=uuid4(),
                )
            )
        )
    )
    assert rows[0] == ["supplier_name", "'=2+2"]
    assert rows[1] == ["issue_date", "'\tdate" if special_text else "2026-11-02"]
    assert rows[2] == ["status", "'\rstatus" if special_text else "extracted"]
    assert rows[3] == ["stated_total", "-5"]
    assert rows[4] == ["currency", "'+GBP" if special_text else "GBP"]
    assert rows[5] == []
    assert rows[6] == [
        "line_number",
        "original_text",
        "quantity",
        "unit_price_amount",
        "unit_price_currency",
        "vat_rate",
        "delivery_fee_amount",
        "delivery_fee_currency",
        "discount_amount",
        "discount_currency",
    ]
    assert rows[7] == [
        "1",
        "'@cmd",
        "2",
        "-5",
        "'-GBP" if special_text else "GBP",
        "0.2",
        "-5",
        "'=USD" if special_text else "USD",
        "-5",
        "'@GBP" if special_text else "GBP",
    ]
