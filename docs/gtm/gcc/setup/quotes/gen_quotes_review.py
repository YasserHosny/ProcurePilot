"""Two Arabic PDF quotes (SAR, 15% VAT included) for the 2026-10-28 flow review on «مطاعم رواق».

usage: python gen_quotes_review.py <out dir> <DD/MM/YYYY>
Then: NODE_PATH=<web node_modules> node render_quotes_review.cjs <out dir>   (prints the two PDFs)

The round-1 shape on Saudi data: four dry-goods lines to الذهبي and الوفرة, both replying with a PDF. الوفرة is
cheaper on oil and sugar, الذهبي on rice and flour, so basket split has something to split. Names, numbers
and VAT registration numbers are fictional; the template is gen_quotes.py's PDF one.
"""

import pathlib
import sys

import datetime as dt

from gen_quotes import PDF_CSS, SUPPLIERS, money

QTY = {"rice": 20, "oil": 10, "sugar": 10, "flour": 15}  # RFQ d8f7fb0c, in packs
ITEMS = {
    "rice": ("أرز بسمتي", "كيس 10 كجم"),
    "oil": ("زيت دوار الشمس", "تنكة 18 لتر"),
    "sugar": ("سكر أبيض", "كيس 10 كجم"),
    "flour": ("دقيق", "كيس 45 كجم"),
}
QUOTES = {  # supplier: (quote no, per-pack prices incl. VAT)
    "dhahabi": ("DH-26-1241", {"rice": 86, "oil": 150, "sugar": 38, "flour": 82}),
    "wafra": ("WF/2026/0765", {"rice": 88, "oil": 146, "sugar": 36, "flour": 85}),
}


def build(out: pathlib.Path, date: dt.date) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for sup, (no, prices) in QUOTES.items():
        name, addr, phone, vat, valid_days = SUPPLIERS[sup]
        rows, total = [], 0.0
        for i, (item, price) in enumerate(prices.items(), 1):
            item_name, pack = ITEMS[item]
            line = price * QTY[item]
            total += line
            rows.append(f"<tr><td>{i}</td><td class='n'>{item_name}</td><td>{pack}</td><td>{QTY[item]}</td>"
                        f"<td>{money(price)}</td><td>{money(line)}</td></tr>")
        d = date.strftime("%d/%m/%Y")
        valid = (date + dt.timedelta(days=valid_days)).strftime("%d/%m/%Y")
        head = ("<tr><th>م</th><th>الصنف</th><th>العبوة</th><th>الكمية</th>"
                "<th>سعر العبوة (ر.س)</th><th>الإجمالي (ر.س)</th></tr>")
        body = "\n".join(rows)
        html = f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{PDF_CSS}</style></head><body>
<div class="hdr"><div><h1>{name}</h1><div>{addr}</div><div>{phone} — الرقم الضريبي: {vat}</div></div><div style="text-align:left"><h1>عرض سعر</h1><div>رقم: {no}</div></div></div>
<table class="meta"><tr><td>التاريخ: {d}</td><td>صالح حتى: {valid}</td></tr>
<tr><td>إلى: مطاعم رواق — فرع العليا</td><td>العملة: ريال سعودي (ر.س)</td></tr></table>
<table><thead>{head}</thead><tbody>
{body}
<tr class="tot"><td colspan="5">الإجمالي شامل ضريبة القيمة المضافة 15%</td><td>{money(total)} ر.س</td></tr></tbody></table>
<p>التوريد خلال {"يومَي عمل" if sup == "dhahabi" else "3 أيام عمل"} إلى الفرع، والتوصيل مجاني. الأسعار شاملة ضريبة القيمة المضافة 15%.</p><p>مع التحية،<br>{name}</p></body></html>"""
        (out / f"{sup}.html").write_text(html, encoding="utf-8")
        print(f"{sup}: {no} total {money(total)} SAR")


if __name__ == "__main__":
    build(pathlib.Path(sys.argv[1]), dt.datetime.strptime(sys.argv[2], "%d/%m/%Y").date())
