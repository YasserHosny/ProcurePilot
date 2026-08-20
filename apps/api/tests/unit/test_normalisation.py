from __future__ import annotations

from decimal import Decimal

import pytest

from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.catalogue.normalisation import (
    normalised_base_quantity,
    normalised_base_quantity_from_string,
    parse_decimal_string,
)


def test_six_packs_of_five_litres_normalise_to_thirty_litres() -> None:
    assert normalised_base_quantity(6, Decimal("5")) == Decimal("30")


def test_three_packs_of_point_thirty_three_are_exactly_point_ninety_nine() -> None:
    assert normalised_base_quantity(3, Decimal("0.33")) == Decimal("0.99")


@pytest.mark.parametrize("pack_count", [0, -1])
def test_zero_and_negative_pack_counts_are_rejected(pack_count: int) -> None:
    with pytest.raises(UnprocessableEntityError):
        normalised_base_quantity(pack_count, Decimal("1"))


@pytest.mark.parametrize("unit_size", [Decimal("0"), Decimal("-0.01")])
def test_zero_and_negative_unit_sizes_are_rejected(unit_size: Decimal) -> None:
    with pytest.raises(UnprocessableEntityError):
        normalised_base_quantity(1, unit_size)


def test_decimal_strings_are_required_for_api_quantity_parsing() -> None:
    with pytest.raises(UnprocessableEntityError):
        parse_decimal_string(0.33, field="unit_size")


def test_string_path_keeps_decimal_exactness() -> None:
    assert normalised_base_quantity_from_string(3, "0.33") == Decimal("0.99")
