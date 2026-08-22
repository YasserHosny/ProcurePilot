from __future__ import annotations

from decimal import Decimal

import pytest

from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.catalogue.normalisation import (
    decimal_to_string,
    normalised_base_quantity,
    normalised_base_quantity_from_string,
    parse_decimal_string,
    require_positive_decimal,
    require_positive_pack_count,
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


def test_require_positive_decimal_passes_through_positive_value() -> None:
    assert require_positive_decimal(Decimal("1.5"), field="unit_size") == Decimal("1.5")


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-0.01")])
def test_require_positive_decimal_rejects_zero_and_negative_values(value: Decimal) -> None:
    with pytest.raises(UnprocessableEntityError):
        require_positive_decimal(value, field="unit_size")


def test_require_positive_pack_count_passes_through_positive_integer() -> None:
    assert require_positive_pack_count(6) == 6


@pytest.mark.parametrize("pack_count", [True, False, 1.5, "6"])
def test_require_positive_pack_count_rejects_bool_float_and_string(pack_count: object) -> None:
    with pytest.raises(UnprocessableEntityError):
        require_positive_pack_count(pack_count)


@pytest.mark.parametrize("value", ["abc", "NaN", "Infinity"])
def test_parse_decimal_string_rejects_malformed_and_non_finite_values(value: str) -> None:
    with pytest.raises(UnprocessableEntityError):
        parse_decimal_string(value, field="unit_size")


def test_parse_decimal_string_rejects_more_than_default_max_scale() -> None:
    with pytest.raises(UnprocessableEntityError) as exc_info:
        parse_decimal_string("1.1234567", field="unit_size")
    assert exc_info.value.details == {"unit_size": "max_6_decimal_places"}


def test_normalised_base_quantity_rejects_unit_size_with_more_than_six_decimal_places() -> None:
    with pytest.raises(UnprocessableEntityError):
        normalised_base_quantity(1, Decimal("1.1234567"))


def test_decimal_to_string_returns_none_for_none_input() -> None:
    assert decimal_to_string(None) is None


def test_decimal_to_string_formats_decimal_input() -> None:
    assert decimal_to_string(Decimal("1.5")) == "1.5"


def test_decimal_to_string_formats_numeric_string_input() -> None:
    assert decimal_to_string("1.5") == "1.5"


def test_decimal_to_string_quantizes_to_requested_places() -> None:
    assert decimal_to_string(Decimal("1.5"), places=3) == "1.500"
