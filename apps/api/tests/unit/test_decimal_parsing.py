from __future__ import annotations

from decimal import Decimal

import pytest

from procurepilot_api.modules.catalogue.csv_import import parse_decimal


def test_decimal_with_comma_as_last_separator() -> None:
    assert parse_decimal("1.234,56") == Decimal("1234.56")


def test_decimal_with_dot_as_last_separator() -> None:
    assert parse_decimal("1,234.56") == Decimal("1234.56")


def test_bare_comma_decimal_is_refused_with_reason() -> None:
    with pytest.raises(ValueError, match="ambiguous decimal separator"):
        parse_decimal("1,234")
