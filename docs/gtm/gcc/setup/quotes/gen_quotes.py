"""Saudi supplier quotes (SAR, 15% VAT included) for the «مطاعم رواق» demo rounds, from the round-5 templates.

usage: python gen_quotes.py <round D|A|E> <out dir> <DD/MM/YYYY>
  D = dry round (sets the last PO prices), A = recorded round, Arabic UI, E = recorded round, English UI.
Then: NODE_PATH=... node render_quotes.cjs <out dir>   (prints dhahabi.png + the two PDFs)
      python ../../../demo-tenant/round-5/quotes/photo.py <out>/dhahabi.png <out>/IMG-<date>-WA00NN.jpg

Prices sit just under the previous round's (الذهبي wins every round), so each round saves against the last PO
price. All names, numbers and VAT registration numbers are fictional.
"""

import datetime as dt
import pathlib
import sys

QTY = {"oil": 10, "rice": 30, "tomato": 20}
ITEMS = {  # (name on the quote, pack on the quote)
    "oil": ("زيت دوار الشمس", "تنكة 18 لتر"),
    "rice": ("أرز بسمتي", "كيس 10 كجم"),
    "tomato": ("طماطم", "كرتون 6 كجم"),
}
ROUNDS = {
    "D": {"dhahabi": {"oil": 158, "rice": 92, "tomato": 38}, "wafra": {"oil": 162, "rice": 94},
          "qassim": {"tomato": 39}, "nos": ("DH-26-1184", "WF/2026/0712", "QS-5521")},
    "A": {"dhahabi": {"oil": 152, "rice": 89, "tomato": 36}, "wafra": {"oil": 156, "rice": 91},
          "qassim": {"tomato": 37}, "nos": ("DH-26-1203", "WF/2026/0731", "QS-5540")},
    "E": {"dhahabi": {"oil": 148, "rice": 87, "tomato": 35}, "wafra": {"oil": 152, "rice": 89},
          "qassim": {"tomato": 36}, "nos": ("DH-26-1219", "WF/2026/0748", "QS-5557")},
}
SUPPLIERS = {
    "dhahabi": ("الذهبي للتموين", "مواد غذائية بالجملة — حي السلي، الرياض", "ت: 0112 467 3390", "300512748600003", 10),
    "wafra": ("الوفرة للمواد الغذائية", "حي الصناعية الجديدة، الرياض", "ت: 0114 921 0076", "310284567900003", 11),
    "qassim": ("خضار القصيم الطازجة", "سوق الخضار المركزي — عتيقة، الرياض", "جوال: 055 318 4402", "302947851200003", 5),
}
PHOTO_CSS = """html,body{margin:0;background:#fff}
body{width:1240px;height:1754px;box-sizing:border-box;padding:90px 95px;font-family:'Noto Naskh Arabic';font-size:27px;color:#151515;position:relative}
.hdr{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:4px double #6b4a12;padding-bottom:18px;margin-bottom:26px}
.hdr h1{font-size:46px;margin:0;color:#6b4a12}.hdr .sub{font-size:23px;color:#333}
.title{font-family:'Noto Kufi Arabic';font-size:40px;color:#6b4a12;text-align:left}
.meta{width:100%;margin:6px 0 18px}.meta td{padding:4px 2px;font-size:25px}
table.items{width:100%;border-collapse:collapse}
.items th,.items td{border:2px solid #444;padding:12px 10px;text-align:center;font-size:26px}
.items th{background:#f3ead8}.items td.n{text-align:right}
.tot td{font-weight:bold;font-size:28px}
.notes{margin-top:30px;font-size:24px;line-height:1.7}
.stamp{position:absolute;left:150px;bottom:250px;width:230px;height:230px;border:6px solid rgba(120,80,20,.55);border-radius:50%;transform:rotate(-14deg);display:flex;align-items:center;justify-content:center;text-align:center;color:rgba(120,80,20,.6);font-family:'Noto Kufi Arabic';font-size:26px;line-height:1.4}
.stamp:before{content:"";position:absolute;inset:14px;border:2px solid rgba(120,80,20,.5);border-radius:50%}
.sig{position:absolute;right:120px;bottom:265px;font-size:26px}
.sig .ink{font-family:'Noto Kufi Arabic';font-weight:300;font-size:44px;color:#5a3a10;transform:rotate(-6deg);display:inline-block;margin-top:6px}
.foot{position:absolute;bottom:70px;left:95px;right:95px;border-top:2px solid #6b4a12;padding-top:10px;font-size:20px;color:#444;text-align:center}"""
PDF_CSS = """@page{size:A4;margin:18mm} body{font-family:'Noto Naskh Arabic','Noto Sans Arabic';font-size:13pt;color:#111}
h1{font-size:20pt;margin:0} .hdr{display:flex;justify-content:space-between;border-bottom:2px solid #333;padding-bottom:8px;margin-bottom:12px}
table{width:100%;border-collapse:collapse;margin-top:12px} th,td{border:1px solid #555;padding:6px 8px;text-align:center} th{background:#eee} td.n{text-align:right}
.tot td{font-weight:bold} .meta td{border:none;text-align:right;padding:2px 6px}"""


def money(x: float) -> str:
    return f"{x:,.2f}"


def rows(prices: dict[str, float]) -> tuple[str, float]:
    out, total = [], 0.0
    for i, (item, price) in enumerate(prices.items(), 1):
        name, pack = ITEMS[item]
        line = price * QTY[item]
        total += line
        out.append(f"<tr><td>{i}</td><td class='n'>{name}</td><td>{pack}</td><td>{QTY[item]}</td>"
                   f"<td>{money(price)}</td><td>{money(line)}</td></tr>")
    return "\n".join(out), total


def build(rnd: str, out: pathlib.Path, date: dt.date) -> None:
    cfg = ROUNDS[rnd]
    out.mkdir(parents=True, exist_ok=True)
    for sup, no in zip(("dhahabi", "wafra", "qassim"), cfg["nos"]):
        name, addr, phone, vat, valid_days = SUPPLIERS[sup]
        body_rows, total = rows(cfg[sup])
        d = date.strftime("%d/%m/%Y")
        valid = (date + dt.timedelta(days=valid_days)).strftime("%d/%m/%Y")
        head = ("<tr><th>م</th><th>الصنف</th><th>العبوة</th><th>الكمية</th>"
                "<th>سعر العبوة (ر.س)</th><th>الإجمالي (ر.س)</th></tr>")
        if sup == "dhahabi":
            html = f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{PHOTO_CSS}</style></head><body>
<div class="hdr"><div><h1>{name}</h1><div class="sub">{addr}</div><div class="sub">{phone} — الرقم الضريبي: {vat}</div></div><div class="title">عرض سعر<div style="font-size:24px;font-family:'Noto Naskh Arabic';color:#222">رقم: {no}</div></div></div>
<table class="meta"><tr><td>التاريخ: {d}</td><td>صالح حتى: {valid}</td></tr><tr><td>السادة: مطاعم رواق — فرع العليا</td><td>العملة: ريال سعودي (ر.س)</td></tr></table>
<table class="items"><thead>{head}</thead><tbody>
{body_rows}
<tr class="tot"><td colspan="5">الإجمالي شامل ضريبة القيمة المضافة 15%</td><td>{money(total)} ر.س</td></tr></tbody></table>
<div class="notes">التوريد خلال 48 ساعة من التأكيد إلى فرع العليا، والتوصيل مجاني.<br>الدفع: خلال 30 يومًا من الاستلام. جميع الأسعار شاملة ضريبة القيمة المضافة 15%.</div>
<div class="sig">مدير المبيعات<br><span class="ink">فهد العتيبي</span></div>
<div class="stamp">الذهبي<br>للتموين<br><span style="font-size:18px">الرياض</span></div>
<div class="foot">للطلبات والاستفسار: {phone.split(': ')[1]} (واتساب) — نشكر ثقتكم</div>
</body></html>"""
        else:
            note = ("الطماطم غير متوفرة لدينا حاليًا. " if sup == "wafra" else "")
            html = f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{PDF_CSS}</style></head><body>
<div class="hdr"><div><h1>{name}</h1><div>{addr}</div><div>{phone} — الرقم الضريبي: {vat}</div></div><div style="text-align:left"><h1>عرض سعر</h1><div>رقم: {no}</div></div></div>
<table class="meta"><tr><td>التاريخ: {d}</td><td>صالح حتى: {valid}</td></tr>
<tr><td>إلى: مطاعم رواق — فرع العليا</td><td>العملة: ريال سعودي (ر.س)</td></tr></table>
<table><thead>{head}</thead><tbody>
{body_rows}
<tr class="tot"><td colspan="5">الإجمالي شامل ضريبة القيمة المضافة 15%</td><td>{money(total)} ر.س</td></tr></tbody></table>
<p>{note}التوريد خلال {2 if sup == "wafra" else 1} يوم عمل إلى فرع العليا. الأسعار شاملة ضريبة القيمة المضافة 15%.</p><p>مع التحية،<br>{name}</p></body></html>"""
        (out / f"{sup}.html").write_text(html, encoding="utf-8")
        print(f"round {rnd} {sup}: {no} total {money(total)} SAR")


if __name__ == "__main__":
    build(sys.argv[1], pathlib.Path(sys.argv[2]), dt.datetime.strptime(sys.argv[3], "%d/%m/%Y").date())
