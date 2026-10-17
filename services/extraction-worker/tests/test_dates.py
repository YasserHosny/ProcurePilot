from datetime import date

import pytest

from procurepilot_extraction_worker.dates import parse_extracted_date


@pytest.mark.parametrize(
    ("raw", "region", "expected", "ambiguous"),
    [
        ("16/10/2026", "EG", date(2026, 10, 16), False),
        ("05/10/2026", "EG", date(2026, 10, 5), True),
        ("05/10/2026", "US", date(2026, 5, 10), True),
        ("10/16/2026", "US", date(2026, 10, 16), False),
        ("10/16/2026", "EG", date(2026, 10, 16), False),
        ("١٦/١٠/٢٠٢٦", "EG", date(2026, 10, 16), False),
        ("«16 أكتوبر 2026»", "EG", date(2026, 10, 16), False),
        ("١٦ أكتوبر ٢٠٢٦م", "EG", date(2026, 10, 16), False),
        ("16 تشرين الأول 2026", "EG", date(2026, 10, 16), False),
        ("16 تشرين الاول 2026", "EG", date(2026, 10, 16), False),
        ("16 اكتوبر 2026", "EG", date(2026, 10, 16), False),
        ("16 إبريل 2026", "EG", date(2026, 4, 16), False),
        ("16 إِبْرِيل 2026", "EG", date(2026, 4, 16), False),
        ("16 ابريل 2026", "EG", date(2026, 4, 16), False),
        ("October 16, 2026", "EG", date(2026, 10, 16), False),
        ("Oct 16، 2026", "EG", date(2026, 10, 16), False),
        ("16 / 10 / 2026", "EG", date(2026, 10, 16), False),
        ("تاريخ العرض: 16/10/2026", "EG", date(2026, 10, 16), False),
        ("Quotation date: 16/10/2026", "EG", date(2026, 10, 16), False),
        ("16-Oct-2026", "EG", date(2026, 10, 16), False),
        ("2026-10-16", "EG", date(2026, 10, 16), False),
        ("2026-10-16T00:00:00Z", "EG", date(2026, 10, 16), False),
        ("2026-10-16 00:00:00", "EG", date(2026, 10, 16), False),
        ("2026-10-16 00:00:00.123456+02:00", "EG", date(2026, 10, 16), False),
        ("التاريخ: 16/10/2026", "EG", date(2026, 10, 16), False),
    ],
)
def test_parse_supported_dates(raw: str, region: str, expected: date, ambiguous: bool) -> None:
    parsed = parse_extracted_date(raw, region=region)
    assert parsed.value == expected
    assert parsed.ambiguous is ambiguous
    assert not parsed.unparsed


@pytest.mark.parametrize("raw", ["soon", "", None, "31/02/2026", "99/99/2026", "Ref 16/10/2026"])
def test_parse_invalid_dates_without_raising(raw: object) -> None:
    parsed = parse_extracted_date(raw, region="EG")
    assert parsed.value is None
    assert parsed.unparsed


def test_equal_components_are_not_ambiguous() -> None:
    parsed = parse_extracted_date("10/10/2026", region="US")
    assert parsed.value == date(2026, 10, 10)
    assert not parsed.ambiguous


@pytest.mark.parametrize(
    ("raw", "region", "rule"),
    [
        (date(2026, 5, 10), "EG", "typed"),
        ("2026-05-10", "EG", "iso"),
        ("10 May 2026", "EG", "month_name"),
        ("05/10/2026", "EG", "numeric_day_first:region=EG"),
        ("05/10/2026", "US", "numeric_month_first:region=US"),
        ("05/10/2026", "SA", "numeric_day_first:region=SA"),
        ("05/10/2026", None, "numeric_day_first:region=default"),
        ("2026/05/10", "EG", "yyyy_mm_dd"),
        ("soon", "EG", "unparsed"),
    ],
)
def test_parse_rule_is_recorded(raw: object, region: str, rule: str) -> None:
    assert parse_extracted_date(raw, region=region).rule == rule
