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
        ("October 16, 2026", "EG", date(2026, 10, 16), False),
        ("16-Oct-2026", "EG", date(2026, 10, 16), False),
        ("2026-10-16", "EG", date(2026, 10, 16), False),
        ("2026-10-16T00:00:00Z", "EG", date(2026, 10, 16), False),
        ("التاريخ: 16/10/2026", "EG", date(2026, 10, 16), False),
    ],
)
def test_parse_supported_dates(raw: str, region: str, expected: date, ambiguous: bool) -> None:
    parsed = parse_extracted_date(raw, region=region)
    assert parsed.value == expected
    assert parsed.ambiguous is ambiguous
    assert not parsed.unparsed


@pytest.mark.parametrize("raw", ["soon", "", None, "31/02/2026", "99/99/2026"])
def test_parse_invalid_dates_without_raising(raw: object) -> None:
    parsed = parse_extracted_date(raw, region="EG")
    assert parsed.value is None
    assert parsed.unparsed


def test_equal_components_are_not_ambiguous() -> None:
    parsed = parse_extracted_date("10/10/2026", region="US")
    assert parsed.value == date(2026, 10, 10)
    assert not parsed.ambiguous
