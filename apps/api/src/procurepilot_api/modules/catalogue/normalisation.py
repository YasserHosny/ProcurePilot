from __future__ import annotations

from decimal import Decimal, InvalidOperation

from procurepilot_api.errors import UnprocessableEntityError

MAX_UNIT_SCALE = 6


def parse_decimal_string(value: object, *, field: str, max_scale: int = MAX_UNIT_SCALE) -> Decimal:
    """Parse an API decimal string without accepting binary numeric coercion."""
    if not isinstance(value, str):
        raise UnprocessableEntityError(details={field: "must_be_decimal_string"})
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise UnprocessableEntityError(details={field: "invalid_decimal"}) from exc
    if not parsed.is_finite():
        raise UnprocessableEntityError(details={field: "invalid_decimal"})
    if _scale(parsed) > max_scale:
        raise UnprocessableEntityError(details={field: f"max_{max_scale}_decimal_places"})
    return parsed


def require_positive_decimal(value: Decimal, *, field: str) -> Decimal:
    if value <= 0:
        raise UnprocessableEntityError(details={field: "must_be_positive"})
    return value


def require_positive_pack_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UnprocessableEntityError(details={"pack_count": "must_be_integer"})
    if value <= 0:
        raise UnprocessableEntityError(details={"pack_count": "must_be_positive"})
    return value


def normalised_base_quantity(pack_count: int, unit_size: Decimal) -> Decimal:
    """Return the database-equivalent generated value: pack_count * unit_size."""
    count = require_positive_pack_count(pack_count)
    size = require_positive_decimal(unit_size, field="unit_size")
    if _scale(size) > MAX_UNIT_SCALE:
        raise UnprocessableEntityError(details={"unit_size": "max_6_decimal_places"})
    return Decimal(count) * size


def normalised_base_quantity_from_string(pack_count: int, unit_size: object) -> Decimal:
    return normalised_base_quantity(
        pack_count,
        parse_decimal_string(unit_size, field="unit_size"),
    )


def decimal_to_string(value: object, *, places: int | None = None) -> str | None:
    if value is None:
        return None
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    if places is not None:
        parsed = parsed.quantize(Decimal(1).scaleb(-places))
    return format(parsed, "f")


def _scale(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return max(0, -exponent)
