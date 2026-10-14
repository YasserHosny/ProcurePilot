from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

_EGP_MARKER = re.compile(
    r"(?<![^\W\d_])(?:جنيه\s+مصري|جنيه|ج\.م\.?|L\.E\.|LE|EGP)(?![^\W\d_])",
    re.IGNORECASE,
)
_OTHER_MARKER = re.compile(
    r"(?<![^\W\d_])(?:USD|GBP|EUR|SAR|AED|KWD|BHD|OMR|JPY|CAD|AUD|\$|£|€)(?![^\W\d_])",
    re.IGNORECASE,
)
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def detect_currency(text: str) -> str | None:
    """Return EGP only when its marker touches an amount; conflicting markers are unknown."""
    egp_spans = [
        match.span()
        for match in _EGP_MARKER.finditer(text)
        if _adjacent_to_number(text, *match.span())
    ]
    if not egp_spans:
        return None
    other_spans = [
        match.span()
        for match in _OTHER_MARKER.finditer(text)
        if _adjacent_to_number(text, *match.span())
    ]
    if other_spans:
        return None
    return "EGP"


def parse_localised_decimal(value: str | int | Decimal) -> Decimal:
    """Parse Western or Arabic-Indic digits and Arabic separators without float conversion."""
    if isinstance(value, Decimal):
        return value
    text = str(value).translate(_ARABIC_DIGITS).replace("٫", ".").replace("٬", "")
    text = text.replace("−", "-").replace("﹣", "-").strip()
    text = _EGP_MARKER.sub("", text).replace(",", "").strip()
    if not text or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
        raise ValueError(f"invalid decimal amount: {value!r}")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal amount: {value!r}") from exc


def _adjacent_to_number(text: str, start: int, end: int) -> bool:
    before = text[:start].rstrip()
    after = text[end:].lstrip()
    return bool((before and _is_digit(before[-1])) or (after and _is_digit(after[0])))


def _is_digit(char: str) -> bool:
    return char.isdigit() or unicodedata.category(char) == "Nd"
