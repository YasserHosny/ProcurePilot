"""Canonical base-unit aliases shared by API write boundaries."""

_ALIASES = {
    "kg": "kilogram",
    "kgs": "kilogram",
    "kilo": "kilogram",
    "kilos": "kilogram",
    "kilogram": "kilogram",
    "kilograms": "kilogram",
    "g": "gram",
    "gm": "gram",
    "gram": "gram",
    "grams": "gram",
    "l": "litre",
    "lt": "litre",
    "ltr": "litre",
    "litre": "litre",
    "litres": "litre",
    "liter": "litre",
    "liters": "litre",
    "ml": "millilitre",
    "millilitre": "millilitre",
    "millilitres": "millilitre",
    "milliliter": "millilitre",
    "milliliters": "millilitre",
    "each": "each",
    "ea": "each",
    "pc": "each",
    "pcs": "each",
    "piece": "each",
    "pieces": "each",
    "unit": "each",
    "units": "each",
}


def canonical_base_unit(raw: str) -> str:
    """Strip and lowercase a unit, mapping known aliases to supported codes."""
    value = raw.strip().lower()
    return _ALIASES.get(value, value)
