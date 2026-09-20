from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from procurepilot_api.modules.catalogue.connector import (
    CataloguePage,
    CsvCatalogueConnector,
    NormalizedCatalogueRow,
    StubCatalogueConnector,
)


def _row(*, observed_at: datetime) -> NormalizedCatalogueRow:
    return NormalizedCatalogueRow(
        provider_record_id="provider-row-1",
        product_name="A4 paper",
        unit_price_amount=Decimal("12.5000"),
        unit_price_currency="gbp",
        base_unit="each",
        observed_at=observed_at,
        valid_from=observed_at,
    )


def test_catalogue_connector_normalizes_currency_and_filters_since() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    connector = StubCatalogueConnector(rows=(_row(observed_at=now - timedelta(days=1)),))

    page = connector.list_catalogue(since=now - timedelta(days=2))

    assert isinstance(page, CataloguePage)
    assert page.rows[0].unit_price_currency == "GBP"


def test_catalogue_connector_rejects_invalid_money_and_validity() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    with pytest.raises(ValueError, match="unit_price_amount"):
        NormalizedCatalogueRow(
            provider_record_id="row",
            product_name="Paper",
            unit_price_amount=Decimal("-1"),
            unit_price_currency="GBP",
            base_unit="each",
            observed_at=now,
            valid_from=now,
        )

    with pytest.raises(ValueError, match="valid_to"):
        NormalizedCatalogueRow(
            provider_record_id="row",
            product_name="Paper",
            unit_price_amount=Decimal("1"),
            unit_price_currency="GBP",
            base_unit="each",
            observed_at=now,
            valid_from=now,
            valid_to=now - timedelta(seconds=1),
        )


def test_csv_catalogue_connector_reuses_parser_and_normalizes_rows() -> None:
    now = datetime(2026, 9, 20, tzinfo=UTC)
    connector = CsvCatalogueConnector(
        b"product_name,unit_price,currency,unit\nPaper,12.50,GBP,box\nBad,nope,GBP,box\n",
        filename="prices.csv",
        observed_at=now,
        default_base_unit="each",
    )

    page = connector.list_catalogue()

    assert [row.provider_record_id for row in page.rows] == ["prices.csv:2"]
    assert page.rows[0].base_unit == "box"
    assert page.errors == ("row 3: unparseable_unit_price",)
