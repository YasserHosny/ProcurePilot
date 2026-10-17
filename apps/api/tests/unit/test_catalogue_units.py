import pytest

from procurepilot_api.modules.catalogue.units import canonical_base_unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("kg", "kilogram"),
        (" kGs ", "kilogram"),
        ("kilo", "kilogram"),
        ("kilos", "kilogram"),
        ("kilogram", "kilogram"),
        ("kilograms", "kilogram"),
        ("g", "gram"),
        ("GM", "gram"),
        ("gram", "gram"),
        ("grams", "gram"),
        ("l", "litre"),
        ("LT", "litre"),
        ("ltr", "litre"),
        ("litre", "litre"),
        ("litres", "litre"),
        ("liter", "litre"),
        ("liters", "litre"),
        ("ml", "millilitre"),
        ("millilitre", "millilitre"),
        ("millilitres", "millilitre"),
        ("milliliter", "millilitre"),
        ("milliliters", "millilitre"),
        ("each", "each"),
        ("EA", "each"),
        ("pc", "each"),
        ("pcs", "each"),
        ("piece", "each"),
        ("pieces", "each"),
        ("unit", "each"),
        ("units", "each"),
        (" Widget ", "widget"),
    ],
)
def test_canonical_base_unit(raw: str, expected: str) -> None:
    assert canonical_base_unit(raw) == expected
