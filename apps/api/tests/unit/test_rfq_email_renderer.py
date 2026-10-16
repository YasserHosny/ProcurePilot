import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from procurepilot_api.modules.rfq.email import RfqEmailLine, render_rfq_email


def _line(name: str = "عدس بجبة") -> RfqEmailLine:
    return RfqEmailLine(
        product_name=name,
        quantity=Decimal("50.000000"),
        unit_code="kilogram",
        pack_count=Decimal("20"),
        unit_size=Decimal("25"),
    )


def test_arabic_email_localises_dates_units_and_rtl() -> None:
    mail = render_rfq_email(
        tenant_name="مطاعم سند",
        locale="ar",
        needed_by=date(2026, 10, 20),
        lines=[_line()],
        tenant_terms="تسليم صباحاً",
        reply_to="reply@example.test",
    )
    assert "مطاعم سند" in mail.subject and "مطاعم سند" in mail.from_name
    assert "٢٠ أكتوبر ٢٠٢٦" in mail.text and "٥٠ كجم" in mail.text
    assert "عبوة ٢٠ × ٢٥ كجم" in mail.text and "تسليم صباحاً" in mail.text
    assert 'lang="ar" dir="rtl"' in mail.html and "This is a request" in mail.text


def test_english_email_and_terms_escaping() -> None:
    mail = render_rfq_email(
        tenant_name="Acme",
        locale="en",
        needed_by=date(2026, 10, 20),
        lines=[
            RfqEmailLine(
                product_name="<script>alert(1)</script>",
                quantity=Decimal("12.500"),
                unit_code="kilogram",
            )
        ],
        tenant_terms="<script>terms</script>\nline two",
        reply_to="a@b.test",
    )
    assert "Acme" in mail.subject and "Acme" in mail.from_name
    assert "12.5 kg" in mail.text and "<script>alert(1)</script>" in mail.text
    assert "&lt;script&gt;" in mail.html and "<script>" not in mail.html
    assert 'lang="en" dir="ltr"' in mail.html
    assert "terms" in mail.text and "terms" in mail.html
    without = render_rfq_email(
        tenant_name="Acme",
        locale="en",
        needed_by=date(2026, 10, 20),
        lines=[],
        tenant_terms=None,
        reply_to=None,
    )
    assert "Buyer terms" not in without.text and "Buyer terms" not in without.html


def test_email_translation_key_parity() -> None:
    root = Path(__file__).resolve().parents[4] / "packages/i18n"
    en, ar = (
        json.loads((root / f"{lang}.json").read_text())["rfq"]["email"] for lang in ("en", "ar")
    )
    assert en.keys() == ar.keys()

    def paths(value: dict, prefix: str = "") -> set[str]:
        result: set[str] = set()
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            result.add(path)
            if isinstance(child, dict):
                result |= paths(child, path)
        return result

    assert paths(en) == paths(ar)
