from datetime import date
from decimal import Decimal

import pytest

from procurepilot_api.modules.rfq import email


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_reminder_subject_reference_and_courtesy(locale: str) -> None:
    rendered = email.render_reminder_email(
        tenant_name="Example Workspace",
        locale=locale,
        reference_number=123,
        sent_date=date(2026, 11, 1),
        needed_by=date(2026, 11, 10),
        lines=[email.RfqEmailLine(product_name="Rice", quantity=Decimal(2), unit_code="each")],
        reply_to="reply@example.test",
    )
    assert rendered.locale == locale
    assert "RFQ-000123" in rendered.text
    assert "Rice" in rendered.text
    assert "reply@example.test" in rendered.text
    if locale == "en":
        assert rendered.subject == (
            "Reminder: request for quotation — Example Workspace — needed by 10 November 2026"
        )
        assert "If you have already replied, please ignore this reminder." in rendered.text
    else:
        assert rendered.subject == (
            "تذكير: طلب عرض سعر — Example Workspace — مطلوب قبل ١٠ نوفمبر ٢٠٢٦"
        )
        assert (
            "This is a reminder of a request for quotation from Example Workspace." in rendered.text
        )
        assert 'dir="rtl"' in rendered.html
