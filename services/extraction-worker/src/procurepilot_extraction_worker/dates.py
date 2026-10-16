from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from procurepilot_extraction_worker.currency import _ARABIC_DIGITS

_RTL_MARKS = str.maketrans("", "", "\u200e\u200f\u061c")
_SEPARATORS = "[/.-]"
_NUMERIC = re.compile(rf"^(\d{{1,4}}){_SEPARATORS}(\d{{1,2}}){_SEPARATORS}(\d{{2,4}})$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:T.*)?$")
_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
    "يناير": 1,
    "كانون الثاني": 1,
    "فبراير": 2,
    "شباط": 2,
    "مارس": 3,
    "آذار": 3,
    "ابريل": 4,
    "أبريل": 4,
    "نيسان": 4,
    "مايو": 5,
    "أيار": 5,
    "حزيران": 6,
    "يونيو": 6,
    "تموز": 7,
    "يوليو": 7,
    "آب": 8,
    "اغسطس": 8,
    "أغسطس": 8,
    "أيلول": 9,
    "سبتمبر": 9,
    "أكتوبر": 10,
    "اكتوبر": 10,
    "تشرين الأول": 10,
    "تشرين الثاني": 11,
    "تشرين اﻷول": 10,
    "كانون الأول": 12,
    "كانون الاول": 12,
}
_MONTH_PATTERN = "|".join(re.escape(name) for name in sorted(_MONTHS, key=len, reverse=True))
_WEEKDAYS = (
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|"
    r"الاثنين|الثلاثاء|الأربعاء|الخميس|الجمعة|السبت|الأحد)"
)
_MONTH_DATE = re.compile(
    rf"^(?:{_WEEKDAYS}[,،]?\s+)?(?:(\d{{1,2}})\s+({_MONTH_PATTERN})\s+(\d{{4}})|({_MONTH_PATTERN})\s+(\d{{1,2}}),?\s+(\d{{4}})|"
    rf"(\d{{1,2}})-({_MONTH_PATTERN})-(\d{{4}}))\s*(?:م)?$",
    re.IGNORECASE,
)
_LABEL = re.compile(r"^(?:التاريخ|date)\s*[:：-]\s*", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedDate:
    value: date | None
    ambiguous: bool
    unparsed: bool


def parse_extracted_date(raw: object, *, region: str | None) -> ParsedDate:
    """Parse extracted dates; ambiguous numeric dates follow market conventions.

    Unknown regions default to day-first because ProcurePilot's target markets primarily
    use day-first dates. Ambiguity remains explicit so humans review these values.
    """
    if isinstance(raw, datetime):
        return ParsedDate(raw.date(), False, False)
    if isinstance(raw, date):
        return ParsedDate(raw, False, False)
    if not isinstance(raw, str):
        return ParsedDate(None, False, True)
    text = raw.translate(_ARABIC_DIGITS).translate(_RTL_MARKS).strip().strip("«»\"'“”")
    text = text.translate(str.maketrans({"⁄": "/", "∕": "/", "／": "/", "٫": "/", "ـ": ""}))
    text = _LABEL.sub("", text).strip()
    text = re.sub(r"^[\w\u0600-\u06ff]+\s+", "", text) if not _MONTH_DATE.match(text) else text
    iso = _ISO.fullmatch(text)
    if iso:
        return _make_date(int(iso[1]), int(iso[2]), int(iso[3]), False)
    month_match = _MONTH_DATE.fullmatch(text)
    if month_match:
        groups = month_match.groups()
        if groups[0]:
            day, month, year = int(groups[0]), _MONTHS[groups[1].lower()], int(groups[2])
        elif groups[3]:
            month, day, year = _MONTHS[groups[3].lower()], int(groups[4]), int(groups[5])
        else:
            day, month, year = int(groups[6]), _MONTHS[groups[7].lower()], int(groups[8])
        return _make_date(year, month, day, False)
    numeric = _NUMERIC.fullmatch(text)
    if not numeric:
        return ParsedDate(None, False, True)
    a, b, year = (int(value) for value in numeric.groups())
    if a >= 1000:
        return _make_date(a, b, year, False)
    if len(numeric[3]) == 2:
        year += 2000
    ambiguous = a <= 12 and b <= 12 and a != b
    if a > 12:
        day, month = a, b
    elif b > 12:
        month, day = a, b
    elif a == b:
        day, month = a, b
    elif (region or "").upper() == "US":
        month, day = a, b
    else:
        day, month = a, b
    return _make_date(year, month, day, ambiguous)


def _make_date(year: int, month: int, day: int, ambiguous: bool) -> ParsedDate:
    try:
        return ParsedDate(date(year, month, day), ambiguous, False)
    except ValueError:
        return ParsedDate(None, False, True)
