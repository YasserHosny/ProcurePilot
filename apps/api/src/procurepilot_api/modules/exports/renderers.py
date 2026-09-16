from __future__ import annotations

import codecs
import csv
import io
from collections.abc import Sequence
from datetime import datetime
from io import BytesIO
from pathlib import Path

from procurepilot_api.shared.i18n import get_export_column_headers, t

_FONT_REGISTERED = False


def register_fonts() -> tuple[str, str]:
    """Register Noto Naskh Arabic fonts if available, returning (regular_font, bold_font)."""
    global _FONT_REGISTERED
    font_dir = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
    regular_path = font_dir / "NotoNaskhArabic-Regular.ttf"
    bold_path = font_dir / "NotoNaskhArabic-Bold.ttf"

    if regular_path.is_file() and not _FONT_REGISTERED:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        pdfmetrics.registerFont(TTFont("NotoNaskhArabic", str(regular_path)))
        if bold_path.is_file():
            pdfmetrics.registerFont(TTFont("NotoNaskhArabic-Bold", str(bold_path)))
        else:
            pdfmetrics.registerFont(TTFont("NotoNaskhArabic-Bold", str(regular_path)))
        _FONT_REGISTERED = True

    if _FONT_REGISTERED:
        return "NotoNaskhArabic", "NotoNaskhArabic-Bold"
    return "Helvetica", "Helvetica-Bold"


def shape_arabic_text(text: str) -> str:
    """Shape connected Arabic glyphs and apply BiDi algorithm for PDF canvas."""
    if not text:
        return ""
    # Check if string contains Arabic Unicode blocks
    if any(
        "\u0600" <= c <= "\u06ff"
        or "\u0750" <= c <= "\u077f"
        or "\u08a0" <= c <= "\u08ff"
        or "\ufb50" <= c <= "\ufdff"
        or "\ufe70" <= c <= "\ufeff"
        for c in text
    ):
        import arabic_reshaper
        from bidi.algorithm import get_display

        reshaped = arabic_reshaper.reshape(text)
        return str(get_display(reshaped))
    return text


def render_csv(
    rows: Sequence[dict[str, object]],
    *,
    kind: str = "savings_ledger",
    locale: str = "en",
) -> bytes:
    """Render rows as CSV with UTF-8 BOM prefix (FR-015)."""
    output = io.StringIO()
    writer = csv.writer(output)
    headers = get_export_column_headers(kind, locale=locale)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(_extract_row_values(kind, row))
    # UTF-8 BOM prefix ensures correct character encoding recognition in Excel & other viewers
    return codecs.BOM_UTF8 + output.getvalue().encode("utf-8")


def render_xlsx(
    rows: Sequence[dict[str, object]],
    *,
    kind: str = "savings_ledger",
    locale: str = "en",
) -> bytes:
    """Render rows as Excel spreadsheet (.xlsx) with localized headers and optional RTL."""
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = t(f"reports.kinds.{kind}", locale=locale)[:31]

    if str(locale).lower().startswith("ar"):
        sheet.sheet_view.rightToLeft = True

    title = f"ProcurePilot — {t(f'reports.kinds.{kind}', locale=locale)}"
    sheet.append([title])
    sheet.append([t("reports.pdf.verifiedRows", locale=locale, count=len(rows))])
    sheet.append([])

    headers = get_export_column_headers(kind, locale=locale)
    sheet.append(headers)

    for row in rows:
        sheet.append(_extract_row_values(kind, row, for_excel=True))

    if not rows:
        sheet.append([t("reports.pdf.emptyResult", locale=locale)])

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def render_pdf(
    rows: Sequence[dict[str, object]],
    *,
    kind: str = "savings_ledger",
    locale: str = "en",
) -> bytes:
    """Render rows as PDF document with structured layouts, headers, and Arabic shaping."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    is_ar = str(locale).lower().startswith("ar")
    reg_font, bold_font = register_fonts() if is_ar else ("Helvetica", "Helvetica-Bold")

    output = BytesIO()
    # pageCompression=0 keeps the stream inspectable
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=0)
    width, height = A4
    y = height - 48

    title_text = shape_arabic_text(f"ProcurePilot — {t(f'reports.kinds.{kind}', locale=locale)}")
    count_text = shape_arabic_text(t("reports.pdf.verifiedRows", locale=locale, count=len(rows)))

    pdf.setFont(bold_font, 14)
    if is_ar:
        pdf.drawRightString(width - 48, y, title_text)
    else:
        pdf.drawString(48, y, title_text)
    y -= 24

    pdf.setFont(reg_font, 10)
    if is_ar:
        pdf.drawRightString(width - 48, y, count_text)
    else:
        pdf.drawString(48, y, count_text)
    y -= 24

    if not rows:
        empty_text = shape_arabic_text(t("reports.pdf.emptyResult", locale=locale))
        if is_ar:
            pdf.drawRightString(width - 48, y, empty_text)
        else:
            pdf.drawString(48, y, empty_text)
    else:
        for row in rows:
            if y < 72:
                pdf.showPage()
                y = height - 48
                pdf.setFont(reg_font, 10)

            line_summary = _format_pdf_row_summary(kind, row, locale=locale)
            shaped_summary = shape_arabic_text(line_summary)
            if is_ar:
                pdf.drawRightString(width - 48, y, shaped_summary[:115])
            else:
                pdf.drawString(48, y, shaped_summary[:115])
            y -= 14

            evidence_line = _format_pdf_evidence(kind, row, locale=locale)
            if evidence_line:
                shaped_evidence = shape_arabic_text(evidence_line)
                if is_ar:
                    pdf.drawRightString(width - 64, y, shaped_evidence[:115])
                else:
                    pdf.drawString(64, y, shaped_evidence[:115])
                y -= 14
            y -= 6

    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _extract_row_values(
    kind: str,
    row: dict[str, object],
    *,
    for_excel: bool = False,
) -> list[object]:
    """Format row values for tabular serialization (CSV and XLSX)."""
    if kind == "spend_by_supplier":
        return [
            str(row.get("supplier_name") or "—"),
            str(row.get("tax_number") or row.get("tax_registration_number") or "—"),
            str(row.get("currency") or row.get("total_paid_currency") or "—"),
            row.get("total_spend") or row.get("total_paid_amount") or 0,
            row.get("order_count") or 1,
            row.get("realised_savings") or row.get("saving_delta_amount") or 0,
            str(row.get("primary_branch") or row.get("attributed_branch_name") or "—"),
        ]

    if kind == "alerts_summary":
        triggered = row.get("triggered_at") or row.get("recorded_at")
        if for_excel and isinstance(triggered, datetime) and triggered.tzinfo is not None:
            triggered = triggered.replace(tzinfo=None)
        return [
            str(row.get("id") or row.get("alert_id") or "—"),
            triggered,
            str(row.get("alert_type") or row.get("kind") or "—"),
            str(row.get("severity") or "medium"),
            str(row.get("supplier_name") or "—"),
            str(row.get("product_name") or "—"),
            str(row.get("branch_name") or "—"),
            row.get("exposure_amount") or 0,
            str(row.get("currency") or row.get("total_currency") or "—"),
            str(row.get("status") or "active"),
            str(row.get("dismissed_by") or "—"),
            str(row.get("dismissal_reason") or "—"),
        ]

    # Default: savings_ledger
    recorded_at = row.get("recorded_at")
    if for_excel and isinstance(recorded_at, datetime) and recorded_at.tzinfo is not None:
        recorded_at = recorded_at.replace(tzinfo=None)

    saving_id = str(row.get("saving_id") or row.get("id") or "")
    evidence_url = f"/savings/{saving_id}/evidence" if saving_id else "—"

    baseline_total = row.get("baseline_value_amount")
    actual_total = row.get("actual_total_paid_amount") or row.get("actual_value_amount")
    delta_amount = row.get("verified_saving_amount") or row.get("delta_amount")
    currency = (
        row.get("verified_saving_currency")
        or row.get("delta_currency")
        or row.get("actual_total_paid_currency")
        or row.get("actual_value_currency")
        or ""
    )

    return [
        saving_id,
        recorded_at,
        str(row.get("attributed_branch_name") or row.get("branch_name") or "—"),
        str(row.get("supplier_name") or row.get("supplier_id") or "—"),
        str(row.get("product_name") or row.get("canonical_name") or "—"),
        str(row.get("base_unit") or "—"),
        row.get("quantity") or "—",
        baseline_total,
        actual_total,
        delta_amount,
        currency,
        evidence_url,
    ]


def _format_pdf_row_summary(kind: str, row: dict[str, object], locale: str = "en") -> str:
    if kind == "spend_by_supplier":
        supp = row.get("supplier_name") or "—"
        curr = row.get("currency") or row.get("total_paid_currency") or ""
        if not curr:
            # N-7: never render a bare monetary amount; log and use a visible sentinel
            import logging as _logging

            _logging.getLogger(__name__).error(
                "spend_by_supplier row missing currency — row id: %s", row.get("id", "unknown")
            )
            curr = "MISSING_CURRENCY"
        spend = row.get("total_spend") or row.get("total_paid_amount") or 0
        orders = row.get("order_count") or 1
        return f"{supp} | {spend} {curr} ({orders} orders)"

    if kind == "alerts_summary":
        alert_id = str(row.get("id") or row.get("alert_id") or "")[:8]
        alert_type = row.get("alert_type") or row.get("kind") or "alert"
        severity = row.get("severity") or "info"
        prod = row.get("product_name") or "—"
        return f"[{severity.upper()}] {alert_type}: {prod} (#{alert_id})"

    # savings_ledger
    saving_id = str(row.get("saving_id") or row.get("id") or "")[:8]
    actual_amt = row.get("actual_total_paid_amount") or row.get("actual_value_amount") or "—"
    actual_curr = row.get("actual_total_paid_currency") or row.get("actual_value_currency") or ""
    delta_amt = row.get("verified_saving_amount") or row.get("delta_amount") or "—"
    delta_curr = row.get("verified_saving_currency") or row.get("delta_currency") or ""
    prod = row.get("product_name") or row.get("canonical_name") or "Item"
    return (
        f"#{saving_id} {prod} | Paid: {actual_amt} {actual_curr} | Saved: {delta_amt} {delta_curr}"
    )


def _format_pdf_evidence(kind: str, row: dict[str, object], locale: str = "en") -> str | None:
    if kind == "savings_ledger":
        saving_id = str(row.get("saving_id") or row.get("id") or "")
        return f"Evidence Link: /savings/{saving_id}/evidence"
    if kind == "spend_by_supplier":
        branch = row.get("primary_branch") or row.get("attributed_branch_name")
        return f"Branch: {branch}" if branch else None
    if kind == "alerts_summary":
        exposure = row.get("exposure_amount")
        curr = row.get("currency") or ""
        return f"Exposure: {exposure} {curr}" if exposure else None
    return None
