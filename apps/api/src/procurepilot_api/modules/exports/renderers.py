from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO

HEADERS = (
    "Saving ID",
    "Recorded At",
    "Supplier ID",
    "Baseline Amount",
    "Baseline Currency",
    "Actual Amount",
    "Actual Currency",
    "Delta Amount",
    "Delta Currency",
    "Evidence Reference",
)


def render_xlsx(rows: Sequence[dict[str, object]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Savings Ledger"
    sheet.append(["ProcurePilot Savings Ledger"])
    sheet.append(["Verified rows", len(rows)])
    sheet.append([])
    sheet.append(list(HEADERS))
    for row in rows:
        sheet.append(_row_values(row))
    if not rows:
        sheet.append(["No verified savings matched the requested period."])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def render_pdf(rows: Sequence[dict[str, object]]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    output = BytesIO()
    # pageCompression=0: this is a short summary document, not a large report — an uncompressed
    # content stream keeps the drawn text directly inspectable (and grep-able) in the raw bytes.
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=0)
    width, height = A4
    y = height - 48
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(48, y, "ProcurePilot Savings Ledger")
    y -= 24
    pdf.setFont("Helvetica", 10)
    pdf.drawString(48, y, f"Verified rows: {len(rows)}")
    y -= 24
    if not rows:
        pdf.drawString(48, y, "No verified savings matched the requested period.")
    else:
        for row in rows:
            if y < 72:
                pdf.showPage()
                y = height - 48
                pdf.setFont("Helvetica", 10)
            line = (
                f"{row['id']} | baseline {row.get('baseline_value_amount') or 'n/a'} "
                f"{row.get('baseline_value_currency') or ''} | actual "
                f"{row['actual_value_amount']} {row['actual_value_currency']} | delta "
                f"{row.get('delta_amount') or 'n/a'} {row.get('delta_currency') or ''}"
            )
            pdf.drawString(48, y, line[:115])
            y -= 14
            pdf.drawString(64, y, f"Evidence: /api/v1/savings/{row['id']}/evidence"[:115])
            y -= 18
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _row_values(row: dict[str, object]) -> list[object]:
    recorded_at = row["recorded_at"]
    return [
        str(row["id"]),
        # Excel has no timezone concept; every recorded_at in this project is stored and read
        # back as UTC, so dropping tzinfo here preserves the correct wall-clock instant.
        recorded_at.replace(tzinfo=None) if recorded_at.tzinfo is not None else recorded_at,
        None if row.get("supplier_id") is None else str(row["supplier_id"]),
        row.get("baseline_value_amount"),
        row.get("baseline_value_currency"),
        row["actual_value_amount"],
        row["actual_value_currency"],
        row.get("delta_amount"),
        row.get("delta_currency"),
        f"/api/v1/savings/{row['id']}/evidence",
    ]
