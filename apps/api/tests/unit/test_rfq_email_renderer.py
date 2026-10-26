import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from procurepilot_api.modules.rfq.email import RfqEmailLine, render_rfq_email
from procurepilot_api.shared.i18n import t


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
    assert "٢٠ أكتوبر ٢٠٢٦" in mail.text
    assert "٥٠ عبوة (٥٠٠ كجم للعبوة) — ٢٥٠٠٠ كجم" in mail.text and "تسليم صباحاً" in mail.text
    assert 'lang="ar" dir="rtl"' in mail.html and "This is a request" in mail.text


def test_arabic_courtesy_line_interpolates_tenant_and_all_fields_have_no_placeholders() -> None:
    mail = render_rfq_email(
        tenant_name="مطاعم سند",
        locale="ar",
        needed_by=date(2026, 10, 20),
        lines=[_line()],
        tenant_terms=None,
        reply_to=None,
    )
    expected = "This is a request for quotation from مطاعم سند."
    assert expected in mail.text
    assert expected in mail.html

    for locale in ("ar", "en"):
        rendered = render_rfq_email(
            tenant_name="مطاعم سند" if locale == "ar" else "Acme",
            locale=locale,
            needed_by=date(2026, 10, 20),
            lines=[_line()],
            tenant_terms=None,
            reply_to=None,
        )
        for field in (rendered.subject, rendered.text, rendered.html, rendered.from_name):
            assert "{{" not in field


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
    assert "12.5 packs" in mail.text and "<script>alert(1)</script>" in mail.text
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


# Finding 39: rfq_line.quantity is in packs (ADR-020). The email states the pack count, the
# size of one pack, and the base-unit total; a one-base-unit pack reads as the base unit alone.
_RICE = RfqEmailLine(
    product_name="أرز مصري (شيكارة 25 كجم)",
    quantity=Decimal("12.000000"),
    unit_code="kilogram",
    pack_count=Decimal("1"),
    unit_size=Decimal("25.000000"),
)
_CARTON = RfqEmailLine(
    product_name="Foil koshary boxes (carton 500)",
    quantity=Decimal("4.000000"),
    unit_code="each",
    pack_count=Decimal("500"),
    unit_size=Decimal("1.000000"),
)
_ONION = RfqEmailLine(
    product_name="بصل أبيض",
    quantity=Decimal("80.000000"),
    unit_code="kilogram",
    pack_count=Decimal("1"),
    unit_size=Decimal("1.000000"),
)


def _render(locale: str, lines: list[RfqEmailLine]) -> str:
    return render_rfq_email(
        tenant_name="مطاعم سند",
        locale=locale,
        needed_by=date(2026, 10, 20),
        lines=lines,
        tenant_terms=None,
        reply_to=None,
    ).text


def test_arabic_email_states_packs_size_and_base_total() -> None:
    text = _render("ar", [_RICE, _ONION])
    assert "- أرز مصري (شيكارة 25 كجم): ١٢ عبوة (٢٥ كجم للعبوة) — ٣٠٠ كجم" in text
    assert "- بصل أبيض: ٨٠ كجم\n" in text
    assert "١٢ كجم" not in text and "عبوة ١ ×" not in text


def test_english_email_states_packs_size_and_base_total() -> None:
    text = _render("en", [_CARTON, _ONION])
    assert "- Foil koshary boxes (carton 500): 4 packs (500 pcs each) — 2000 pcs" in text
    assert "- بصل أبيض: 80 kg\n" in text
    assert "4 pcs" not in text and "pack 500 × 1" not in text


def test_single_pack_and_unknown_pack_size() -> None:
    one = _RICE.model_copy(update={"quantity": Decimal("1")})
    assert "1 pack (25 kg)" in _render("en", [one])
    assert "عبوة واحدة (٢٥ كجم)" in _render("ar", [one])
    unknown = _RICE.model_copy(update={"pack_count": None, "unit_size": None})
    assert ": 12 packs\n" in _render("en", [unknown])
    assert ": ١٢ عبوة\n" in _render("ar", [unknown])


@pytest.mark.parametrize("locale", ["en", "ar"])
def test_supplier_email_has_no_brand_footer(locale: str) -> None:
    result = render_rfq_email(
        tenant_name="Workspace",
        locale=locale,
        needed_by=date(2026, 10, 20),
        lines=[_line()],
        tenant_terms=None,
        reply_to=None,
    )
    for part in (result.text, result.html):
        assert t("emails.footer.sentWith", locale) not in part
        assert t("emails.footer.website", locale) not in part
        assert "https://www.iron-sys.com/" not in part
