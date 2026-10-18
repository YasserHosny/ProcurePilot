"""Finding 42: a photographed quote's «صالح حتى» date must not be silently dropped.

Hand-built from the hosted reproduction (quotation abd38926, IMG-20261019-WA0007.jpg): Azure's
prebuilt-invoice returned InvoiceDate, VendorName and InvoiceTotal but no DueDate, so the
validity date only exists in the OCR text. Photo OCR splits the two-column meta block into
separate lines, sometimes puts the value on its own line, and may emit Arabic-Indic digits.
"""

from datetime import date
from types import SimpleNamespace as NS

import pytest

from procurepilot_extraction_worker.azure_di import _parse_invoice_result
from procurepilot_extraction_worker.worker import _with_normalised_dates

_HEADER = [
    "الأمانة للتجارة",
    "مواد غذائية بالجملة — 27 ش الجمهورية، عابدين، القاهرة",
    "عرض سعر رقم: AM-2026-0733",
]
_FOOTER = [
    "التوريد خلال 48 ساعة من التأكيد إلى فرع المعادي، والنقل مجانًا.",
    "الدفع: خلال 30 يومًا من الاستلام.",
    "الإجمالي 24,220.00 ج.م",
]

PHOTO_LAYOUTS = {
    # Each meta cell becomes its own OCR line.
    "split_cells": ["التاريخ: 19/10/2026", "صالح حتى: 29/10/2026", "العملة: جنيه مصري (ج.م)"],
    # The label and the value are far apart on the photo, so OCR emits them as two lines.
    "value_on_next_line": ["التاريخ: 19/10/2026", "صالح حتى:", "29/10/2026"],
    # Both cells on one OCR line in visual (left-to-right) order: value precedes its label.
    "visual_order_one_line": ["29/10/2026 :صالح حتى 19/10/2026 :التاريخ"],
    # Arabic-Indic digits from the photo's OCR.
    "arabic_indic_digits": ["التاريخ: ١٩/١٠/٢٠٢٦", "صالح حتى: ٢٩/١٠/٢٠٢٦"],
}


def _photo_result(meta_lines: list[str]) -> NS:
    lines = [*_HEADER, *meta_lines, *_FOOTER]
    fields = {
        "VendorName": NS(content="الأمانة", confidence=0.939),
        "InvoiceDate": NS(value_date=date(2026, 10, 19), content="19/10/2026", confidence=0.968),
        "InvoiceTotal": NS(content="24,220.00 ج.م", confidence=0.457),
    }
    return NS(
        content="\n".join(lines),
        pages=[NS(lines=[NS(content=line) for line in lines])],
        paragraphs=[],
        tables=[],
        documents=[NS(fields=fields)],
    )


@pytest.mark.parametrize("layout", PHOTO_LAYOUTS)
def test_photo_validity_date_is_extracted_and_flagged(layout: str) -> None:
    result = _parse_invoice_result(_photo_result(PHOTO_LAYOUTS[layout]), "test")

    expiry = result.header.get("expiry_date")
    assert expiry is not None, "validity date silently dropped"
    assert expiry.confidence < 0.85  # below the default threshold: goes to review

    normalised, parsed_dates, unparsed = _with_normalised_dates(result, "EG")
    assert parsed_dates["expiry_date"] == "2026-10-29"
    assert parsed_dates["issue_date"] == "2026-10-19"
    assert not unparsed


def test_azure_due_date_still_wins_over_text_fallback() -> None:
    raw = _photo_result(PHOTO_LAYOUTS["split_cells"])
    raw.documents[0].fields["DueDate"] = NS(value_date=None, content="30/10/2026", confidence=0.575)
    result = _parse_invoice_result(raw, "test")
    assert result.header["expiry_date"].value == "30/10/2026"
    assert result.header["expiry_date"].confidence == 0.575


def test_no_validity_label_means_no_expiry() -> None:
    result = _parse_invoice_result(_photo_result(["التاريخ: 19/10/2026"]), "test")
    assert "expiry_date" not in result.header


@pytest.mark.parametrize(
    "meta_line",
    [
        "Date: 19/10/2026 Validity: 30 days",
        "التاريخ: 19/10/2026 الصلاحية: 30 يوم",
    ],
)
def test_issue_date_before_duration_validity_is_not_the_expiry(meta_line: str) -> None:
    result = _parse_invoice_result(_photo_result([meta_line]), "test")
    assert "expiry_date" not in result.header


def test_bare_salahiya_label_with_date_is_extracted() -> None:
    result = _parse_invoice_result(_photo_result(["الصلاحية: 29/10/2026"]), "test")
    assert result.header["expiry_date"].value == "29/10/2026"


def test_pre_label_date_owned_by_another_label_is_not_the_expiry() -> None:
    result = _parse_invoice_result(_photo_result(["التاريخ: 19/10/2026 :الصلاحية 30 يوم"]), "test")
    assert "expiry_date" not in result.header


def test_visual_order_without_colon_does_not_truncate_next_labels_date() -> None:
    result = _parse_invoice_result(_photo_result(["صالح حتى 19/10/2026 :التاريخ"]), "test")
    assert "expiry_date" not in result.header
