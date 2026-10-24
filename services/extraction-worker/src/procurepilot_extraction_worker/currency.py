from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from procurepilot_extraction_worker.validation import decimal_from_extracted

_EGP_MARKER = re.compile(
    r"(?<![^\W\d_])(?:جنيه\s+مصري|جنيه|ج\.م\.?|L\.E\.|LE|EGP)(?![^\W\d_])",
    re.IGNORECASE,
)
_SAR_MARKER = re.compile(
    # SR is case-sensitive and must touch an amount on the same line: "Sr." is a
    # common serial-number header, not evidence of Saudi riyals.
    r"(?<![^\W\d_])(?:ر\.\s*س\.?|ريال\s+سعودي|SAR|"
    r"(?-i:SR)(?=[ \t]*\d)|(?<=\d)[ \t]*(?-i:SR))(?![^\W\d_])",
    re.IGNORECASE,
)
_OTHER_MARKER = re.compile(
    r"(?<![^\W\d_])(?:ريال\s+قطري|ريال\s+عُ?ماني|"
    r"USD|GBP|EUR|AED|QAR|KWD|BHD|OMR|JPY|CAD|AUD|\$|£|€)(?![^\W\d_])",
    re.IGNORECASE,
)
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def detect_currency(text: str) -> str | None:
    """Return EGP or SAR only with amount-adjacent evidence; conflicts are unknown."""
    currencies = {
        code
        for code, pattern in (("EGP", _EGP_MARKER), ("SAR", _SAR_MARKER))
        if any(_adjacent_to_number(text, *match.span()) for match in pattern.finditer(text))
    }
    if len(currencies) != 1:
        return None
    if any(_adjacent_to_number(text, *match.span()) for match in _OTHER_MARKER.finditer(text)):
        return None
    return currencies.pop()


def parse_localised_decimal(value: str | int | Decimal) -> Decimal:
    """Parse Western or Arabic-Indic digits and Arabic separators without float conversion."""
    if isinstance(value, Decimal):
        return value
    text = str(value).translate(_ARABIC_DIGITS).replace("٫", ".").replace("٬", "")
    text = text.replace("−", "-").replace("﹣", "-").strip()
    text = _SAR_MARKER.sub("", _EGP_MARKER.sub("", text)).strip()
    # Leave ASCII separators intact so the established import parser can reject
    # ambiguous comma-only values (for example, "1,234") consistently.
    return decimal_from_extracted(text)


def _adjacent_to_number(text: str, start: int, end: int) -> bool:
    before = text[:start].rstrip()
    after = text[end:].lstrip()
    return bool((before and _is_digit(before[-1])) or (after and _is_digit(after[0])))


def _is_digit(char: str) -> bool:
    return char.isdigit() or unicodedata.category(char) == "Nd"
