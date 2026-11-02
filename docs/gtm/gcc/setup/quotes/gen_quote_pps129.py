"""One Arabic PDF quote (SAR, 15% VAT included) for the PPS-129 live check on «مطاعم رواق».

usage: python gen_quote_pps129.py <out dir> <DD/MM/YYYY>
Then: NODE_PATH=<web node_modules> node render_quotes_review.cjs <out dir>   (prints عرض سعر الذهبي <no>.pdf)

Two products with no PO and no quote history yet, priced so the per-base-unit price does not divide evenly:
eggs 172 per carton of 30 (5.7333… per egg) and yogurt 50 per carton of 12 kg (4.1666… per kg). Before the fix
the quoted baseline for 3 cartons of eggs was 5.7333 × 90 = 515.9970 and for 4 cartons of yogurt
4.1667 × 48 = 200.0016; both must now be exact (516, 200). Names and numbers are fictional.
"""

import datetime as dt
import pathlib
import sys

from gen_quotes import PDF_CSS, SUPPLIERS, money

LINES = [  # (item, pack, packs, price per pack incl. VAT)
    ("بيض", "كرتون 30 حبة", 3, 172),
    ("زبادي", "كرتون 12 × 1 كجم", 4, 50),
]
QUOTE_NO = "DH-26-1263"


def build(out: pathlib.Path, date: dt.date) -> None:
    out.mkdir(parents=True, exist_ok=True)
    name, addr, phone, vat, valid_days = SUPPLIERS["dhahabi"]
    rows, total = [], 0.0
    for i, (item, pack, qty, price) in enumerate(LINES, 1):
        line = price * qty
        total += line
        rows.append(f"<tr><td>{i}</td><td class='n'>{item}</td><td>{pack}</td><td>{qty}</td>"
                    f"<td>{money(price)}</td><td>{money(line)}</td></tr>")
    d = date.strftime("%d/%m/%Y")
    valid = (date + dt.timedelta(days=valid_days)).strftime("%d/%m/%Y")
    head = ("<tr><th>م</th><th>الصنف</th><th>العبوة</th><th>الكمية</th>"
            "<th>سعر العبوة (ر.س)</th><th>الإجمالي (ر.س)</th></tr>")
    body = "\n".join(rows)
    html = f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{PDF_CSS}</style></head><body>
<div class="hdr"><div><h1>{name}</h1><div>{addr}</div><div>{phone} — الرقم الضريبي: {vat}</div></div><div style="text-align:left"><h1>عرض سعر</h1><div>رقم: {QUOTE_NO}</div></div></div>
<table class="meta"><tr><td>التاريخ: {d}</td><td>صالح حتى: {valid}</td></tr>
<tr><td>إلى: مطاعم رواق — فرع العليا</td><td>العملة: ريال سعودي (ر.س)</td></tr></table>
<table><thead>{head}</thead><tbody>
{body}
<tr class="tot"><td colspan="5">الإجمالي شامل ضريبة القيمة المضافة 15%</td><td>{money(total)} ر.س</td></tr></tbody></table>
<p>التوريد خلال يومَي عمل إلى الفرع، والتوصيل مجاني. الأسعار شاملة ضريبة القيمة المضافة 15%.</p><p>مع التحية،<br>{name}</p></body></html>"""
    (out / "dhahabi.html").write_text(html, encoding="utf-8")
    print(f"dhahabi: {QUOTE_NO} total {money(total)} SAR")


if __name__ == "__main__":
    build(pathlib.Path(sys.argv[1]), dt.datetime.strptime(sys.argv[2], "%d/%m/%Y").date())
