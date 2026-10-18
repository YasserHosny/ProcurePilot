from __future__ import annotations

import html
from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from procurepilot_api.shared.i18n import t


class RfqEmailLine(BaseModel):
    product_name: str
    quantity: Decimal
    unit_code: str
    pack_count: Decimal | None = None
    unit_size: Decimal | None = None


class RenderedRfqEmail(BaseModel):
    subject: str
    text: str
    html: str
    from_name: str
    locale: str


def _digits(value: str, locale: str) -> str:
    if locale != "ar":
        return value
    return value.translate(str.maketrans("0123456789.", "٠١٢٣٤٥٦٧٨٩٫"))


def _decimal(value: Decimal, locale: str) -> str:
    normalized = format(value.normalize(), "f")
    return _digits(normalized, locale)


def _date(value: date, locale: str) -> str:
    month = t(f"rfq.email.months.{value.month}", locale)
    return f"{_digits(str(value.day), locale)} {month} {_digits(str(value.year), locale)}"


def _line_amount(item: RfqEmailLine, locale: str) -> str:
    """The requested amount: rfq_line.quantity is in packs (ADR-020), so state the pack count,
    the size of one pack and the base-unit total. A one-base-unit pack (loose goods sold per kg)
    reads as the base unit alone."""
    quantity = _decimal(item.quantity, locale)
    if item.pack_count is None or item.unit_size is None:
        return t("rfq.email.packsOnly", locale, count=quantity)
    unit = t(f"rfq.email.units.{item.unit_code}", locale)
    per_pack = item.pack_count * item.unit_size
    if per_pack == 1:
        return f"{quantity} {unit}"
    size = _decimal(per_pack, locale)
    if item.quantity == 1:
        return t("rfq.email.packQuantityOne", locale, size=size, unit=unit)
    total = _decimal(item.quantity * per_pack, locale)
    return t("rfq.email.packQuantity", locale, count=quantity, size=size, unit=unit, total=total)


def render_rfq_email(
    *,
    tenant_name: str,
    locale: str,
    needed_by: date,
    lines: list[RfqEmailLine],
    tenant_terms: str | None,
    reply_to: str | None,
) -> RenderedRfqEmail:
    lang = "ar" if locale == "ar" else "en"
    direction = "rtl" if lang == "ar" else "ltr"
    date_label = _date(needed_by, lang)
    subject = t("rfq.email.subject", lang, tenant=tenant_name, date=date_label)
    from_name = t("rfq.email.fromName", lang, tenant=tenant_name)
    intro = t("rfq.email.intro", lang, tenant=tenant_name)
    greeting = t("rfq.email.greeting", lang)
    needed_label = t("rfq.email.neededBy", lang)
    terms_title = t("rfq.email.termsHeading", lang)
    reply_text = t("rfq.email.replyInstructions", lang)
    item_title = t("rfq.email.itemsHeading", lang)
    courtesy = t("rfq.email.englishSummary", "en", tenant=tenant_name) if lang == "ar" else ""
    quantity_lines: list[str] = []
    item_html: list[str] = []
    for item in lines:
        amount = _line_amount(item, lang)
        quantity_lines.append(f"- {item.product_name}: {amount}")
        item_html.append(f"<li>{html.escape(item.product_name)}: {html.escape(amount)}</li>")
    text_lines = [
        greeting,
        intro,
        "",
        item_title,
        *quantity_lines,
        "",
        f"{needed_label}: {date_label}",
    ]
    if tenant_terms:
        text_lines.extend(["", terms_title, tenant_terms])
    if reply_to:
        text_lines.extend(["", reply_text, reply_to])
    if courtesy:
        text_lines.extend(["", courtesy])
    text_body = "\n".join(text_lines)
    terms_text_html = html.escape(tenant_terms).replace("\n", "<br>") if tenant_terms else ""
    terms_html = (
        f"<section><h2>{html.escape(terms_title)}</h2><p>{terms_text_html}</p></section>"
        if tenant_terms
        else ""
    )
    reply_html = f"<p>{html.escape(reply_text)}<br>{html.escape(reply_to)}</p>" if reply_to else ""
    courtesy_html = f'<p lang="en" dir="ltr">{html.escape(courtesy)}</p>' if courtesy else ""
    html_body = (
        f'<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">'
        f"<title>{html.escape(subject)}</title></head><body><p>{html.escape(greeting)}</p>"
        f"<p>{html.escape(intro)}</p><h2>{html.escape(item_title)}</h2><ul>{''.join(item_html)}</ul>"
        f"<p>{html.escape(needed_label)}: {html.escape(date_label)}</p>"
        f"{terms_html}{reply_html}{courtesy_html}</body></html>"
    )
    return RenderedRfqEmail(
        subject=subject, text=text_body, html=html_body, from_name=from_name, locale=lang
    )
